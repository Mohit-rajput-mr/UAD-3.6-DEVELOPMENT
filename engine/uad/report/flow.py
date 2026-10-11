"""Pour the form's blocks onto Legal pages by measuring them.

The blocks from ``form.build`` are laid out once as a galley at the report's
45-pica measure, every block's real height (and every row inside a two-column
block or table) is read back from the browser, and page breaks are placed where
the content runs out -- following Appendix E's rules:

* a section tab, bar or subheading never ends a page; it moves with what
  follows it;
* a section carried onto a new page reopens with its tab and "(continued)"
  (TAB-C);
* Assignment Information, Sales Comparison Approach and the Scope of Work
  begin a new page (Part 2);
* a table breaks only where it has to, and repeats its column heads.
"""
from __future__ import annotations

import asyncio
import json
import re
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable

from lxml import etree
from uad.report.browser import sync_playwright  # optional: BrowserUnavailable without Chromium

from .. import bind
from . import form, page


def _allow_subprocesses() -> None:
    """Let Playwright start Chromium from inside the server.

    Measuring the page needs a real browser, and starting one needs an event
    loop that can spawn a child process.  On Windows uvicorn installs the
    selector loop, which cannot, so every route that renders -- the preview,
    the PDF, the package -- failed inside the running application while
    working perfectly from a test or the command line, because both of those
    get the default loop instead.  The policy only governs loops created after
    it, so the server's own running loop is untouched.
    """
    if sys.platform != "win32":
        return
    proactor = getattr(asyncio, "WindowsProactorEventLoopPolicy", None)
    if proactor is not None and not isinstance(
            asyncio.get_event_loop_policy(), proactor):
        asyncio.set_event_loop_policy(proactor())


BODY_TOP = 62.4
BODY_TOP_FIRST = 55.9
BODY_BOTTOM = 926.0
PX = 72 / 96

MEASURE_JS = """
() => {
  const px = 72 / 96;
  const out = [];
  const galley = document.getElementById('galley');
  // A block's border box is not what it costs a page.  The gap in front of it
  // -- its own margin, collapsed with the previous block's -- is real vertical
  // space that getBoundingClientRect().height does not report, and leaving it
  // out is what put content off the bottom of the page.  Measure it as the
  // distance from the previous block's bottom: that is what the browser did
  // after collapsing, so the planner and the page agree by construction.
  let prevBottom = galley.getBoundingClientRect().top;
  for (const blk of document.querySelectorAll('#galley > .blk')) {
    const r = blk.getBoundingClientRect();
    const lead = Math.max(0, r.top - prevBottom) * px;
    prevBottom = r.bottom;
    const e = {n: +blk.dataset.n, kind: blk.dataset.kind, group: +blk.dataset.group,
               section: blk.dataset.section || '', newpage: !!blk.dataset.newpage,
               height: r.height * px, lead: lead, cols: [], rows: [], head: '',
               html: blk.innerHTML, outer: blk.outerHTML.slice(0, 80)};
    if (blk.classList.contains('cols')) {
      for (const col of blk.querySelectorAll(':scope > .col')) {
        const kids = Array.from(col.children);
        const top = col.getBoundingClientRect().top;
        const items = [];
        // An item costs its own box plus the gap in front of it.  Measuring
        // top-to-top instead charges that gap to the item above, which is
        // wrong the moment the column is split: the slice below starts with a
        // gap nobody paid for, and the page runs long by exactly that much.
        // A .col is a flex item, so it is a block formatting context and the
        // gap is inside it -- it renders at the top of a slice too.
        let prevBottom = top;
        for (let i = 0; i < kids.length; i++) {
          const k = kids[i];
          const kr = k.getBoundingClientRect();
          const lead = Math.max(0, kr.top - prevBottom);
          let bottom = kr.bottom;
          let html = k.outerHTML;
          const next = kids[i + 1];
          // a Yes/No header travels with the checkbox under it
          if (k.classList.contains('yn') && next) {
            bottom = next.getBoundingClientRect().bottom;
            html += next.outerHTML;
            i++;
          }
          items.push({html: html, top: (kr.top - top) * px,
                      height: (lead + bottom - kr.top) * px});
          prevBottom = bottom;
        }
        e.cols.push(items);
      }
    }
    const table = blk.querySelector(':scope > table');
    if (table) {
      const head = table.querySelector('thead');
      const cg = table.querySelector('colgroup');
      e.head = (cg ? cg.outerHTML : '') + (head ? head.outerHTML : '');
      e.tableOpen = table.outerHTML.slice(0, table.outerHTML.indexOf('>') + 1);
      e.headHeight = head ? head.getBoundingClientRect().height * px : 0;
      // A grid's head gains its Property Address row on a continued page;
      // measure that head too, so the continued slice is charged for it.
      e.contHeadHeight = e.headHeight;
      if (table.querySelector('thead tr.tca')) {
        table.classList.add('cont');
        e.contHeadHeight = head.getBoundingClientRect().height * px;
        table.classList.remove('cont');
      }
      for (const tr of table.querySelectorAll('tbody > tr')) {
        e.rows.push({html: tr.outerHTML, height: tr.getBoundingClientRect().height * px,
                     sub: tr.classList.contains('sub')});
      }
    }
    out.push(e);
  }
  return out;
}
"""


@dataclass
class Piece:
    html: str
    section: str
    # What the planner charged this piece, in points.  Kept so the rendered
    # page can be compared against the plan piece by piece: a block whose real
    # height exceeds its charge is the thing that pushes content off the page.
    charged: float = 0.0


@dataclass
class Page:
    pieces: list[Piece] = field(default_factory=list)
    first: bool = False
    # What the planner believed the content bottom would be.  ``verify`` reads
    # the real one back; the two disagreeing is the bug that puts content off
    # the page, so the number is kept rather than thrown away.
    planned: float = 0.0


def _galley(blocks: list[form.Block], *, embed_fonts: bool,
            edit: bool = False) -> str:
    return (f"<!doctype html><html><head><meta charset='utf-8'><style>"
            f"{form.stylesheet(embed_fonts=embed_fonts, edit=edit)}"
            f"#galley{{width:540pt;margin-left:36pt}}"
            f"#galley > .blk:not(.cols){{display:flow-root}}</style></head><body>"
            f"<div class='hi'><div class='hz'>"
            f"<div id='galley'>{form.galley_html(blocks, edit)}</div></div></div></body></html>")


def measure(html: str) -> list[dict]:
    _allow_subprocesses()
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--font-render-hinting=none"])
        try:
            pg = browser.new_page(viewport={"width": 900, "height": 1400},
                                  device_scale_factor=1)
            pg.set_content(html, wait_until="load", timeout=90_000)
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(150)
            return pg.evaluate(MEASURE_JS)
        finally:
            browser.close()


def _tab(section: str, continued: bool) -> str:
    cont = "<span class='cont'>(continued)</span>" if continued else ""
    return (f"<div class='blk tabblk'><div class='tabwrap'><span class='tab'>"
            f"{form.esc(section)}{cont}</span></div></div>")


TAB_H = 15.0 + form.TAB_BELOW         # a carried section's "(continued)" tab


def plan(blocks: list[dict], caps: dict[int, float] | None = None, *,
         header_on_first: bool = False) -> list[Page]:
    caps = caps or {}
    pages: list[Page] = [Page(first=True)]
    y = BODY_TOP if header_on_first else BODY_TOP_FIRST
    current_section = ""

    def room() -> float:
        return caps.get(len(pages), BODY_BOTTOM) - y

    def new_page(section: str | None = None, *, continued: bool = True) -> None:
        nonlocal y
        pages.append(Page())
        y = BODY_TOP
        if section and continued:
            pages[-1].pieces.append(Piece(_tab(section, True), section, TAB_H))
            y += TAB_H
        pages[-1].planned = y

    def at_top() -> bool:
        """Is this the start of the page's content?  Used to decide breaks --
        starting yet another page would put nothing on this one.  A section's
        own tab counts as nothing too: a grid moved off a page that holds only
        the "Sales Comparison Approach" tab left the tab alone on it (D-1
        Co-op1 p12 sets the grid straight under the tab and splits it)."""
        return all("tabblk" in p.html for p in pages[-1].pieces)

    def empty() -> bool:
        """Is there really nothing above this block?

        Only then is its leading margin not rendered.  A carried section's
        "(continued)" tab is content: the block under it still spaces itself
        away from the tab, and charging it as though it were flush with the
        top of the page loses that gap on every carried section."""
        return not pages[-1].pieces

    def place(html: str, height: float, lead: float, section: str) -> None:
        nonlocal y
        if empty():
            # Nothing above it to space away from, and `.top` zeroes the margin
            # in the stylesheet, so the page must not be charged for it either.
            lead = 0.0
            html = html.replace("class='blk", "class='blk top", 1)
        pages[-1].pieces.append(Piece(html, section, lead + height))
        y += lead + height
        pages[-1].planned = y

    opens = full_page_leads(blocks)
    i = 0
    while i < len(blocks):
        b = blocks[i]
        section = b["section"]
        wrap_open = (f"<div class='blk {'cols' if b['kind'] == 'cols' else 'solid ' + b['kind']}'>")

        if i in opens and not at_top():
            # a full-page image opens a page, and what leads to it goes with it
            if b["kind"] == "tab":
                new_page(None, continued=False)
            else:
                new_page(current_section)

        if (b.get("newpage") and b["kind"] not in ("tab", "grid") and b["group"] not in (1, 2)):
            # A section that opens a page with its own text rather than a tab
            # (Appendix E p79/p85: the Scope of Work "starts new page"; "TAB
            # sets elsewhere").  Its tab is not on this page, so a page it
            # runs on to has no section to call "(continued)".
            if pages[-1].pieces and not at_top():
                new_page(None, continued=False)
            elif pages[-1].pieces:
                pages[-1].pieces.clear()       # only a "(continued)" tab
                y = BODY_TOP
                pages[-1].planned = y
            current_section = ""

        if b["kind"] == "tab":
            current_section = section
            need = b["lead"] + b["height"] + _keep(blocks, i + 1)
            if b["newpage"] and pages[-1].pieces:
                new_page(None, continued=False)
            elif need > room() and pages[-1].pieces:
                new_page(None, continued=False)
            place(_tab(section, False), b["height"], b["lead"], section)
            i += 1
            continue

        if b["group"] in (1, 2):           # h1 / h2 keep with next
            need = b["lead"] + b["height"] + _keep(blocks, i + 1)
            # a forced break first: it opens a fresh page, and the section it
            # opens is not a continuation of the one before
            if b.get("newpage") and not at_top():
                new_page(None, continued=False)
            if need > room() and not at_top():
                new_page(current_section)
            place(f"<div class='blk solid'>{b['html']}</div>", b["height"], b["lead"], section)
            i += 1
            continue

        if b["kind"] == "cols":
            left, right = (b["cols"] + [[], []])[:2]
            li = ri = 0
            first = True
            while li < len(left) or ri < len(right):
                lead = 0.0 if (empty() or not first) else b["lead"]
                avail = room() - lead
                nl, hl = _fill(left, li, avail)
                nr, hr = _fill(right, ri, avail)
                if nl == li and nr == ri:
                    if not at_top():
                        new_page(current_section)
                        continue
                    if li < len(left):
                        nl, hl = li + 1, left[li]["height"]
                    else:
                        nr, hr = ri + 1, right[ri]["height"]
                gapcls = " gap" if (first and "blk cols gap" in b["outer"]) else ""
                topcls = " top" if empty() else ""
                html = (f"<div class='blk cols{gapcls}{topcls}'><div class='col left'>"
                        + "".join(it["html"] for it in left[li:nl])
                        + "</div><div class='col right'>"
                        + "".join(it["html"] for it in right[ri:nr]) + "</div></div>")
                pages[-1].pieces.append(Piece(html, section, lead + max(hl, hr)))
                y += lead + max(hl, hr)
                pages[-1].planned = y
                li, ri = nl, nr
                first = False
                if li < len(left) or ri < len(right):
                    new_page(current_section)
            i += 1
            continue

        if b.get("newpage") and b["kind"] == "grid" and not at_top():
            new_page(current_section)
            continue

        if b["rows"] and b["lead"] + b["height"] > room() and b["kind"] in ("table", "grid"):
            # a table that does not fit: move it whole if it fits a page,
            # otherwise break it between rows and repeat its heads
            body_h = BODY_BOTTOM - BODY_TOP - TAB_H
            if b["height"] <= body_h and not at_top():
                new_page(current_section)
                continue
            rows = b["rows"]
            ri = 0
            first = True
            while ri < len(rows):
                lead = 0.0 if (empty() or not first) else b["lead"]
                head_h = b.get("headHeight", 0) if first else b.get("contHeadHeight", b.get("headHeight", 0))
                avail = room() - lead - head_h - 8
                nr, hr = _fill(rows, ri, avail)
                if nr == ri:
                    if not at_top():
                        new_page(current_section)
                        continue
                    nr, hr = ri + 1, rows[ri]["height"]
                topcls = " top" if empty() else ""
                opener = b['tableOpen'] if first else b['tableOpen'].replace("class=\"grid\"", "class=\"grid cont\"").replace("class='grid'", "class='grid cont'")
                html = (f"<div class='blk solid {b['kind']}{topcls}'>{opener}{b['head']}<tbody>"
                        + "".join(r["html"] for r in rows[ri:nr]) + "</tbody></table></div>")
                pages[-1].pieces.append(
                    Piece(html, section, lead + hr + head_h + 8))
                y += lead + hr + head_h + 8
                pages[-1].planned = y
                ri = nr
                first = False
                if ri < len(rows):
                    new_page(current_section)
            i += 1
            continue

        if b["lead"] + b["height"] > room() and not at_top():
            new_page(current_section)
            continue
        place(f"<div class='blk solid {b['kind']}'>{b['html']}</div>", b["height"], b["lead"], section)
        i += 1
    return [p for p in pages if p.pieces]


def _keep(blocks: list[dict], j: int) -> float:
    """What a heading needs below it on its page: any headings straight after
    it, then the first line of what they head.  Keeping a tab with only the H1
    under it left "Certifications" alone at a page foot, the H1 and its text
    carried over (D-1: the tab heads page 20 of SF1, 17 of Co-op1)."""
    need = 0.0
    while j < len(blocks) and blocks[j]["group"] in (1, 2) and blocks[j]["kind"] != "tab":
        need += blocks[j]["lead"] + blocks[j]["height"]
        j += 1
    return need + _first_line(blocks[j] if j < len(blocks) else None)


def _first_line(b: dict | None) -> float:
    if b is None:
        return 0.0
    lead = b.get("lead", 0.0)
    if b["kind"] == "cols":
        firsts = [c[0]["height"] for c in b["cols"] if c]
        return lead + (max(firsts) if firsts else 13.0)
    if b["rows"]:
        return lead + b.get("headHeight", 0) + b["rows"][0]["height"] + 6
    if b["kind"] == "exhibits":
        # an image row cannot be split, so a heading keeps with all of it --
        # otherwise a full-page map leaves its H1 alone at a page foot
        return lead + b["height"]
    return lead + min(b["height"], 60.0)


FULL_EXHIBIT = re.compile(r"""class=["']ex full\b""")


def full_page_leads(blocks: list[dict]) -> set[int]:
    """The blocks that open a page because a full-page image follows.

    Appendix E p31: photos "can start on same page as section"; maps and
    sketches are full page, in a 45 x 48 pica frame.  Every full-page image in
    the twelve D-1 samples heads its page, even with room above it (MH1 p6
    and p22 follow pages ending at 211 pt and 242 pt), and what leads to it
    goes with it: its H1 ("Sales Comparison Map", "Site Exhibits"), and in
    the Sketch section the tab and "Measurement Standard" (SF1 p5, SF4 p5).

    So the page opens at the run of headings in front of the image; an image
    with no heading of its own (the sketch) takes its section's tab with it
    when nothing but the section's few opening rows stands between them
    (``LEAD_IN`` at most: Measurement Standard, the 7.002 caption row)."""
    opens: set[int] = set()
    for i, b in enumerate(blocks):
        if b["kind"] != "exhibits" or not FULL_EXHIBIT.search(b.get("html", "")):
            continue
        same = lambda k: blocks[k]["section"] == b["section"]  # noqa: E731
        start, j = i, i - 1
        while j >= 0 and same(j) and blocks[j]["group"] in (1, 2):
            start, j = j, j - 1
        if start != i:
            opens.add(start)                 # its own heading leads to it
            continue
        k, rows = j, 0.0
        while (k >= 0 and same(k) and blocks[k]["group"] not in (1, 2)
               and blocks[k]["kind"] not in ("tab", "exhibits", "grid")):
            rows += blocks[k].get("lead", 0.0) + blocks[k].get("height", 0.0)
            k -= 1
        if k >= 0 and same(k) and blocks[k]["kind"] == "tab" and rows <= LEAD_IN:
            start = k
        opens.add(start)
    return opens


#: How much of a section's opening may travel with a full-page image: the
#: Sketch section's rows above its frame measure 20-45 pt in the samples.
LEAD_IN = 120.0


def _fill(items: list[dict], start: int, avail: float) -> tuple[int, float]:
    used, i = 0.0, start
    while i < len(items) and used + items[i]["height"] <= avail + 0.3:
        used += items[i]["height"]
        i += 1
    return i, used


# ---------------------------------------------------------------------------
# Page furniture
# ---------------------------------------------------------------------------
@dataclass
class Meta:
    version: str = "Appraisal Version #1"
    issuer: str = "Fannie Mae | Freddie Mac"
    form_date: str = "September 2024"
    references: list[tuple[str, str]] = field(default_factory=list)
    title: str = "Uniform Residential Appraisal Report"
    # The URAR opens with its lead block and no running header; an update or
    # completion report carries "<title>  Page 1 of N" from its first page
    # (D-2 AU1, D-3 CR1/CR2, A-2/A-3 HF.001).
    header_on_first: bool = False
    kind: str = "urar"
    # the footer's reference IDs as the editor offers them: each that applies,
    # filled or not (uad/references.py, T-919)
    editable: list[dict] = field(default_factory=list)

    @classmethod
    def from_case(cls, tree) -> "Meta":
        from . import urar
        from .. import references, report_types
        m = urar.Meta.from_case(tree)
        kind = report_types.kind_of(tree)
        root = tree.getroot() if hasattr(tree, "getroot") else tree
        offered = references.editable(root)
        if kind == report_types.URAR:
            return cls(m.version, m.issuer, m.form_date, m.references, editable=offered)
        number = m.version.rsplit("#", 1)[-1] or "1"
        return cls(f"{report_types.version_label(kind)}{number}", m.issuer, m.form_date,
                   m.references, report_types.title(kind), True, kind, editable=offered)


from functools import lru_cache


@lru_cache(maxsize=4)
def _metrics(face: str):
    from fontTools.ttLib import TTFont
    font = TTFont(str(form.fonts.source(face)))
    return font.getBestCmap(), font["hmtx"], font["head"].unitsPerEm


def text_width(text: str, face: str, size: float) -> float:
    cmap, hmtx, upm = _metrics(face)
    return sum(hmtx[cmap[ord(c)]][0] for c in text if ord(c) in cmap) / upm * size


def _furniture(meta: Meta, n: int, total: int, edit: bool = False) -> str:
    head = "" if n == 1 and not meta.header_on_first else (
        f"<div class='hdr-l'>{form.esc(meta.title)}</div>"
        f"<div class='hdr-r'>Page {n} of {total}</div><div class='hdr-rule'></div>")
    refs = []
    y = 947.1
    # the editor offers every reference that applies, to be typed where it
    # prints; the report prints those that hold a value
    rows = ([(r["label"], r["value"], r["field"]) for r in meta.editable] if edit
            else [(label, value, "") for label, value in meta.references])
    # Appendix E FTR-R: identifiers align left, the longest ending on the
    # measure; labels align right one em (measured 11.9 pt) before them.
    value_x = 576.0 - max((max(text_width(v, "MyriadPro-Regular", 8.0), 40.0 if edit else 0)
                           for _l, v, _f in rows), default=30.3)
    label_right = 612.0 - (value_x - 9.7)
    for label, value, fid in rows:
        shown = form.esc(value)
        if edit:
            shown = (f"<span class='v' contenteditable='true' spellcheck='false'"
                     f" data-route='references/{fid}' data-k='text'>{shown}</span>")
        refs.append(f"<div class='refl' style='top:{y:.1f}pt;right:{label_right:.2f}pt'>{form.esc(label)}</div>"
                    f"<div class='refv' style='top:{y:.1f}pt;left:{value_x:.2f}pt'>{shown}</div>")
        y += 9.0
    foot = ("<div class='ftr-rule'></div><div class='ftr'>"
            f"<div class='f1'>{form.esc(meta.version)}</div>"
            f"<div class='f2'>{form.esc(meta.issuer)}</div>"
            f"<div class='f3'>{form.esc(meta.form_date)}</div>" + "".join(refs) + "</div>")
    return head + foot


# The page fits the frame's width, never above actual size -- unless the
# editor says otherwise (T-1210, owner 2026-10-11 "report looks too small"):
# {uad:'zoom', z:'width'} fits the width and grows into the room the other
# windows give up (to 160 %), a number is a fixed size (0.5 - 2).  The frame
# says what it drew at ({uad:'zoom-at'}) so the editor can show it.
FIT_JS = """<script>
(function(){function fit(){var w=document.documentElement.clientWidth-24;
w-=(window.UAD_SIDE||0);var f=w/816,q=window.UAD_ZOOM,z;
if(typeof q==='number'&&isFinite(q)) z=Math.max(0.5,Math.min(2,q)); else if(q==='width') z=Math.min(1.6,f); else z=Math.min(1,f);
document.querySelectorAll('.page').forEach(function(p){p.style.zoom=z;});
if(window.parent!==window&&z!==window.UAD_ZOOM_AT){window.UAD_ZOOM_AT=z;try{window.parent.postMessage({uad:'zoom-at',z:z},'*');}catch(_){}}}
window.addEventListener('resize',fit);
window.addEventListener('message',function(e){if(e.data&&e.data.uad==='zoom'){window.UAD_ZOOM=e.data.z;fit();}});
fit();})();
</script>"""


# Typing on the report writes through the same route the editor uses, so a
# value set here lands exactly where a value set anywhere else would.  The page
# is not re-rendered on every keystroke: it would move the caret and cost a
# layout pass, so the value is left as typed and the page reloads only when the
# document has been changed underneath it.
EDIT_JS = """
<script>
(function(){
  var qs=new URLSearchParams(location.search), id=qs.get('case');
  if(!id) return;

  // Show what is still unanswered from the moment the report opens, so the
  // whole of what is left is visible before a word is typed.
  document.body.classList.add('show-gaps');

  /* What an import brought in.  Reading a value back cannot say where it came
     from, so the import names the fields it answered and they are marked
     here -- including the Summary, which holds no values of its own but
     redisplays fields from the rest of the report, so a Summary line counts
     as imported when the field behind it was. */
  function markImported(){
    var fids=window.UAD_IMPORTED;
    if(!fids||!fids.length) return;
    document.body.classList.add('has-imported','show-imported');
    var want=Object.create(null);
    for(var i=0;i<fids.length;i++) want[fids[i]]=1;
    var all=document.querySelectorAll('[data-fid],[data-gf],[data-derived]');
    for(var j=0;j<all.length;j++){
      var el=all[j];
      var key=el.getAttribute('data-fid')||el.getAttribute('data-gf')||
              el.getAttribute('data-derived');
      if(key&&want[key]) el.classList.add('imported');
    }
  }
  markImported();
  var parentWin=(window.parent!==window)?window.parent:null;
  function tell(msg){ if(parentWin) parentWin.postMessage(msg,'*'); }
  /* The platform's own dialogs (app/ui/dialog.js, in the editor window), never
     the browser's "... says" box; the browser's only when this page is opened
     on its own. */
  function dlg(){ try{ return window.top!==window&&window.top.UADDialog; }catch(_){ return null; } }
  function say(msg,o){ var d=dlg(); if(d) return d.alert(msg,o||{title:'Something went wrong'}); window.alert(msg); return Promise.resolve(); }
  function ask(msg,o){ var d=dlg(); if(d) return d.confirm(msg,o||{}); return Promise.resolve(window.confirm((o&&o.title?o.title+'\\n\\n':'')+msg)); }
  // the pages leave room at their right for Save / Save & Next (110 px buttons
  // 14 px from the page: 136, not the 240 that cost the report its size, T-1210)
  window.UAD_SIDE=136; document.body.style.boxSizing='border-box';
  document.body.style.paddingRight='136px'; window.dispatchEvent(new Event('resize'));

  function flash(target){
    target.classList.add('found');
    setTimeout(function(){target.classList.remove('found');},1600);
  }
  // Every piece of the page names its section (data-secn), so the rail can
  // go to a section by number, whatever its tab prints ("Certifications",
  // "Dwelling Exterior - Building 1") and however many pages it runs to.
  function goSection(n){
    var t=document.querySelector('[data-secn="'+n+'"]');
    if(!t) return false;
    // straight there: a smooth scroll across twenty pages outlasts any lock
    // and the rail would follow the pages flying past
    var top=t.getBoundingClientRect().top+window.scrollY-8;
    spyLock=Date.now()+400; current=String(n);
    window.scrollTo({top:Math.max(0,top),behavior:'auto'});
    flash(t);
    tell({uad:'at',secn:Number(n)});
    return true;
  }
  function goField(fid){
    var t=document.querySelector('[data-fid="'+fid+'"]');
    if(!t) return false;
    spyLock=Date.now()+400;
    t.scrollIntoView({block:'center',behavior:'auto'});
    flash(t);
    var holder=t.closest('[data-secn]');
    if(holder){ current=holder.dataset.secn; tell({uad:'at',secn:Number(current)}); }
    return true;
  }
  // a map's own box ("Go to it" after the map is saved into the report)
  function goMap(kind){
    var t=document.querySelector('[data-map="'+kind+'"]');
    t=t&&(t.closest('figure')||t);
    if(!t) return false;
    spyLock=Date.now()+400;
    t.scrollIntoView({block:'start',behavior:'auto'});
    flash(t);
    var holder=t.closest('[data-secn]');
    if(holder){ current=holder.dataset.secn; tell({uad:'at',secn:Number(current)}); }
    return true;
  }
  window.addEventListener('message',function(e){
    var m=e.data||{};
    if(m.uad==='gaps'){
      document.body.classList.toggle('show-gaps',!!m.on);
    }
    if(m.uad==='imported'){
      document.body.classList.toggle('show-imported',!!m.on);
    }
    if(m.uad==='reload'){ reloadHere(); }
    // The rail and the Review Master both navigate the report rather than
    // opening a second page about it.
    if(m.uad==='autofill'){ fill(m.steps||[],m.pace); }
    if(m.uad==='autofill-stop'){ filling=false; }
    if(m.uad==='goto'){
      var ok=false;
      if(m.map) ok=goMap(m.map);
      if(!ok&&m.fid) ok=goField(m.fid);
      if(!ok&&m.secn) ok=goSection(m.secn);
      tell({uad:'goto-result',found:ok,secn:m.secn||0,fid:m.fid||''});
    }
  });

  /* --------------------------------------------------------- the filler
     A case arrives as an order sheet, an MLS export and a folder of
     photographs.  The server writes the whole document in one pass; this
     replays the same list of steps on the page so the appraiser watches the
     report being filled in rather than being handed it finished.  Nothing
     here writes: every value shown has already been saved by the step the
     server ran, and the form is reloaded from the server at the end, so what
     is left on the screen is the saved document and not this animation.
  */
  var TICK='\uF052', CLEAR='\uF0A3';
  var agentStyle=document.createElement('style');
  agentStyle.textContent=
    ".agent-on{outline:1.5pt solid #231f20;outline-offset:1pt;background:#fff3b0!important}"
    +".agent-typed{background:#fff9d6}"
    +"@keyframes agentpulse{from{box-shadow:0 0 0 0 rgba(35,31,32,.35)}"
    +"to{box-shadow:0 0 0 6pt rgba(35,31,32,0)}}"
    +".agent-on{animation:agentpulse .5s ease-out}"
    // shown at once, saved behind: a slim moving line until the layout lands
    +".uad-ghost{pointer-events:none;opacity:.85}"
    +".uad-done{color:#1f7a3a!important;border-color:#1f7a3a!important}"
    +".uad-pending{position:relative}"
    +".uad-pending:after{content:'';position:absolute;left:0;right:0;bottom:0;height:2pt;z-index:6;"
    +"background:linear-gradient(90deg,#9a9aa0,#f4f4f5,#9a9aa0);background-size:200% 100%;"
    +"animation:uadbar 1.1s linear infinite}"
    +"@keyframes uadbar{to{background-position:-200% 0}}"
    +".uad-removing{opacity:.28;transition:opacity .18s;pointer-events:none}"
    +"img.uad-local{width:100%;height:100%;object-fit:contain;display:block;flex:1;min-height:0}"
    // the stage behind the pages is the application's (light or dark), not the
    // page's -- painted here: a frame left transparent is drawn white by the
    // browser when its colour scheme differs from the editor's
    +"html,body{background:#e4e4e6!important}"
    +"[data-uitheme=dark],[data-uitheme=dark] body{background:#19191c!important}"
    // Save / Save & Next beside each page are the editor's controls, not the report's
    +".pageside button{font-family:'Geist','Inter','Segoe UI',-apple-system,Roboto,Arial,sans-serif;font-weight:500;"
    +"border-radius:0;border:1px solid rgba(0,0,0,.18);background:#fff;color:#0b0b0c;transition:opacity .12s,background .12s}"
    +".pageside button.pgsave{background:#0b0b0c;border-color:#0b0b0c;color:#fff}"
    +".pageside button:hover{background:#f2f2f2;color:#0b0b0c}"
    +".pageside button.pgsave:hover{background:#0b0b0c;color:#fff;opacity:.86}"
    +"[data-uitheme=dark] .pageside button{background:transparent;border-color:rgba(255,255,255,.22);color:#f4f4f5}"
    +"[data-uitheme=dark] .pageside button.pgsave{background:#f4f4f5;border-color:#f4f4f5;color:#0a0a0b}"
    +"[data-uitheme=dark] .pageside button:hover{background:rgba(255,255,255,.08);color:#f4f4f5}"
    +"[data-uitheme=dark] .pageside button.pgsave:hover{background:#f4f4f5;color:#0a0a0b;opacity:.86}"
    +".pageside.ok button.pgsave{background:#0f8a5f;border-color:#0f8a5f;color:#fff}";
  // the application's theme, now and when it is switched
  try{ document.documentElement.dataset.uitheme=(window.parent!==window&&window.parent.document.documentElement.dataset.theme)||'light'; }catch(_){}
  window.addEventListener('message',function(e){
    if(e.data&&e.data.uad==='theme') document.documentElement.dataset.uitheme=e.data.theme;
  });
  document.head.appendChild(agentStyle);

  var optionCache={};
  function optionsFor(fid){
    if(optionCache[fid]) return Promise.resolve(optionCache[fid]);
    return fetch('/api/fields/'+fid+'/options').then(function(r){return r.json();})
      .then(function(d){ optionCache[fid]=d.options||[]; return optionCache[fid]; })
      .catch(function(){ optionCache[fid]=[]; return []; });
  }
  function words(t){ return (t||'').replace(/\\s+/g,' ').trim().toLowerCase(); }
  /* A table cell is found by the field it writes and, where a table repeats a
     row per instance, by the row it prints on. */
  function cellFor(s){
    var all=[].slice.call(document.querySelectorAll('[data-tf="'+s.fid+'"]'));
    if(!all.length) return null;
    if(s.row_label){
      var named=all.filter(function(el){
        var tr=el.closest('tr'), first=tr&&tr.querySelector('td');
        return first&&words(first.textContent)===words(s.row_label);
      });
      if(named.length) all=named;
    }
    var free=all.filter(function(el){ return !words(el.textContent); });
    return (free.length?free:all)[0];
  }
  /* A grid cell is the row whose label matches, in the column of that
     comparable (0 is the subject). */
  function gridCell(s){
    var tables=document.querySelectorAll('table.grid');
    for(var t=0;t<tables.length;t++){
      var rows=tables[t].querySelectorAll('tbody tr');
      for(var r=0;r<rows.length;r++){
        var lab=rows[r].querySelector('td.lbl');
        if(!lab||words(lab.textContent)!==words(s.label)) continue;
        var vals=rows[r].querySelectorAll('td.v');
        var want=s.adjust?(s.column*2):(s.column*2-(s.column?1:0));
        var cell=vals[Math.min(Math.max(want,0),vals.length-1)];
        if(cell) return cell;
      }
    }
    return null;
  }
  function control(s){
    if(s.kind==='check')
      return document.querySelector('.bx[data-fid="'+s.fid+'"][data-pick="'+s.value+'"]');
    if(s.kind==='grid') return gridCell(s);
    if(s.kind==='cell') return cellFor(s);
    if(s.kind==='photo') return document.querySelector('.exadd,.exdrop,.photo,.exbox');
    if(!s.fid) return null;
    return document.querySelector('[data-fid="'+s.fid+'"]')||cellFor(s);
  }
  function wait(ms){ return new Promise(function(go){ setTimeout(go,ms); }); }

  function showList(el,options,chosen){
    var list=document.createElement('div');
    list.className='picklist';
    var hit=null;
    options.slice(0,12).forEach(function(o){
      var row=document.createElement('div');
      row.textContent=o.label;
      if(o.value===chosen||o.label===chosen){ row.className='on'; hit=row; }
      list.appendChild(row);
    });
    var host=el.closest('.hz')||document.body;
    host.appendChild(list);
    var a=el.getBoundingClientRect(), b=host.getBoundingClientRect();
    var scale=(b.width/host.offsetWidth)||1;
    list.style.left=((a.left-b.left)/scale)+'px';
    list.style.top=((a.bottom-b.top)/scale)+'px';
    if(hit) hit.scrollIntoView({block:'nearest'});
    return list;
  }
  function typeInto(el,text,pace){
    return new Promise(function(done){
      var i=0, size=Math.max(2,Math.ceil(text.length/6));
      el.classList.add('agent-typed');
      (function beat(){
        i=Math.min(text.length,i+size);
        el.textContent=text.slice(0,i);
        if(i>=text.length){ el.classList.remove('agent-typed'); return done(); }
        setTimeout(beat,pace);
      })();
    });
  }
  var filling=false;
  /* The order a value sits in the document is not the order it sits on the
     page: a section's own steps arrive in XML order, so the filling appeared
     to jump about within a section even though the sections themselves are in
     report order.  The page is the only thing that knows where a control
     actually is, so each section's steps are put into page order here, as the
     section is reached -- not before, because the report is laid out again
     part way through a run and the later controls do not exist yet. */
  function inPageOrder(list){
    var placed=[], loose=[];
    for(var k=0;k<list.length;k++){
      var el=null;
      try{ el=control(list[k]); }catch(_){ el=null; }
      if(el) placed.push({s:list[k],el:el}); else loose.push(list[k]);
    }
    placed.sort(function(a,b){
      var rel=a.el.compareDocumentPosition(b.el);
      if(rel&Node.DOCUMENT_POSITION_FOLLOWING) return -1;
      if(rel&Node.DOCUMENT_POSITION_PRECEDING) return 1;
      return 0;
    });
    var out=[];
    for(var j=0;j<placed.length;j++) out.push(placed[j].s);
    return out.concat(loose);       // what has no control yet keeps its place
  }

  function fill(steps,pace){
    if(filling) return;
    filling=true;
    pace=pace||70;
    var i=0, atSection=null, shown=0, missed=0;
    function finish(){
      filling=false;
      tell({uad:'autofill-done',shown:shown,missed:missed});
    }
    function next(){
      if(i>=steps.length) return finish();
      var s=steps[i++];
      // Values that have no control of their own -- what a block is linked to,
      // a measure's unit -- are written all the same; they are not acted out.
      if(s.kind==='data'||s.kind==='link'){
        if(s.n%12===0) tell({uad:'autofill-at',n:s.n,total:steps.length,secn:s.secn,
                             section:s.section,label:s.label,value:s.display||s.value});
        return setTimeout(next,0);
      }
      tell({uad:'autofill-at',n:s.n,total:steps.length,secn:s.secn,
            section:s.section,label:s.label,value:s.display||s.value});
      if(s.secn!==atSection){
        atSection=s.secn; goSection(s.secn);
        // put the rest of this section into the order it is printed in
        var from=i-1, to=from;
        while(to<steps.length&&steps[to].secn===s.secn) to++;
        if(to-from>1){
          var block=inPageOrder(steps.slice(from,to));
          for(var b=0;b<block.length;b++) steps[from+b]=block[b];
          s=steps[from]; i=from+1;
        }
      }
      var el=control(s);
      if(!el){
        // The value is written; this page has no control for it yet (a row
        // that only appears once the report is laid out again).  The section
        // is still opened, so the filling is seen to move through the report.
        missed++; return setTimeout(next,4);
      }
      el.scrollIntoView({block:'center',behavior:'auto'});
      el.classList.add('agent-on');
      var quiet=function(){
        el.classList.remove('agent-on');
        // Green the instant it is answered: the appraiser watching sees which
        // field just changed, rather than only that something moved.
        document.body.classList.add('has-imported','show-imported');
        el.classList.add('imported');
        var owner=el.closest?el.closest('td'):null;
        if(owner) owner.classList.add('imported');
        shown++; setTimeout(next,pace*0.4);
      };
      if(s.kind==='check'){
        var run=el.parentNode.querySelectorAll('.bx[data-pick]');
        [].forEach.call(run,function(b){ b.innerHTML=CLEAR; });
        return wait(pace).then(function(){ el.innerHTML=TICK; }).then(function(){
          return wait(pace*0.6); }).then(quiet);
      }
      if(s.kind==='pick'){
        return optionsFor(s.fid).then(function(options){
          el.classList.add('open');
          var list=showList(el,options,s.value);
          return wait(pace*1.6).then(function(){
            list.remove(); el.classList.remove('open');
            el.textContent=s.display||s.value;
            return wait(pace*0.4);
          });
        }).then(quiet);
      }
      // A cell or a grid cell the server has already written still reads as
      // filling: it is emptied for the moment it takes to enter it again.
      var into=el.querySelector('span')||el;
      if(s.kind==='cell'||s.kind==='grid'||s.kind==='data') into.textContent='';
      return typeInto(into,s.display||s.value,Math.max(8,pace/6)).then(function(){
        return wait(pace*0.4); }).then(quiet);
    }
    next();
  }

  /* Follow the reader: the section at the top quarter of the window is the
     one the rail marks. */
  var current=null, spyLock=0, ticking=false;
  function spy(){
    ticking=false;
    if(Date.now()<spyLock) return;
    var line=window.innerHeight*0.25, found=null;
    var marks=document.querySelectorAll('[data-secn]');
    for(var i=0;i<marks.length;i++){
      if(marks[i].getBoundingClientRect().top<=line) found=marks[i].dataset.secn;
      else break;
    }
    if(!found&&marks.length) found=marks[0].dataset.secn;
    if(found&&found!==current){ current=found; tell({uad:'at',secn:Number(found)}); }
  }
  window.addEventListener('scroll',function(){
    if(!ticking){ ticking=true; requestAnimationFrame(spy); }
  },{passive:true});

  /* After an image changes what fits, the report is laid out again; the
     reader stays where they were. */
  var KEY='uad-scroll-'+id;
  function reloadHere(fid){
    // Inside the editor the new layout is made in the background and swapped
    // in without a blank page (and the editor returns to ``fid``, the field
    // that changed the layout); on its own, the page reloads once it is ready.
    if(parentWin){ parentWin.postMessage({uad:'relayout',fid:typeof fid==='string'?fid:''},'*'); return; }
    try{ sessionStorage.setItem(KEY,String(window.scrollY)); }catch(_){}
    var R=window.UAD_RENDER||{};
    function poll(){
      fetch('/api/cases/'+id+'/render/form').then(function(r){return r.json();})
        .then(function(st){ if(st.ready) location.reload(); else setTimeout(poll,600); })
        .catch(function(){ location.reload(); });
    }
    if(R.kind) poll(); else location.reload();
  }
  function arrived(){
    var y=null;
    try{ y=sessionStorage.getItem(KEY); sessionStorage.removeItem(KEY); }catch(_){}
    if(y!==null) window.scrollTo(0,Number(y));
    spy();
    var have={};
    [].forEach.call(document.querySelectorAll('[data-secn]'),function(x){have[x.dataset.secn]=1;});
    tell({uad:'ready',sections:Object.keys(have).map(Number)});
  }
  if(document.readyState==='complete') setTimeout(arrived,0);
  else window.addEventListener('load',arrived);

  /* The Summary redisplays the rest of the report (B-1 chapter 01): a click
     goes to the field the value is entered in. */
  document.addEventListener('click',function(e){
    var d=e.target.closest && e.target.closest('[data-derived]');
    if(!d) return;
    e.preventDefault(); e.stopPropagation();
    if(!(d.dataset.derived && goField(d.dataset.derived))){
      if(d.dataset.derivedSection) goSection(d.dataset.derivedSection);
    }
  },true);
  /* A table cell writes into the row it prints in; everything else by field. */
  var inflight=[];
  /* The rent schedule's sums (B-1 23.01.14-25, uad/rent_math.py) follow a
     rent at once: every place that shows the same unit's rent shows the new
     one, and the totals are added up here as the server adds them. */
  var RENT_POINTS={UnitMonthlyActualRentAmount:1,UnitMonthlyMarketRentAmount:1,
                   MonthlyActualAdditionalIncomeAmount:1,MonthlyEstimatedAdditionalIncomeAmount:1};
  function money(n){ return '$'+n.toLocaleString('en-US',{minimumFractionDigits:n%1?2:0,maximumFractionDigits:2}); }
  function rentTotals(el,shown){
    var dp=el.dataset.tdp, key=el.dataset.tk||'';
    if(key&&shown) [].forEach.call(document.querySelectorAll('[data-tdp="'+dp+'"]'),function(o){
      if(o!==el&&(o.dataset.tk||'')===key&&document.activeElement!==o){ o.textContent=shown; o.dataset.was=shown; }
    });
    function sum(point){
      var seen={}, total=0, any=false;
      [].forEach.call(document.querySelectorAll('[data-tdp="'+point+'"]'),function(o){
        var k=o.dataset.tk||Math.random(); if(seen[k]) return; seen[k]=1;
        var v=parseFloat((o.textContent||'').replace(/[^0-9.-]/g,''));
        if(!isNaN(v)){ total+=v; any=true; }
      });
      return {total:total,any:any};
    }
    var a=sum('UnitMonthlyActualRentAmount'), m=sum('UnitMonthlyMarketRentAmount'),
        oa=sum('MonthlyActualAdditionalIncomeAmount'), om=sum('MonthlyEstimatedAdditionalIncomeAmount');
    var put=function(point,v){ [].forEach.call(document.querySelectorAll('td.calc[data-calc="'+point+'"] span'),function(s){ s.textContent=money(v); }); };
    if(a.any||oa.any){ put('TotalMonthlyActualRentAmount',a.total); put('TotalMonthlyActualAdditionalIncomeAmount',oa.total);
      put('TotalMonthlyActualIncomeAmount',a.total+oa.total); }
    if(m.any||om.any){ put('TotalMonthlyMarketRentAmount',m.total); put('TotalMonthlyEstimatedAdditionalIncomeAmount',om.total);
      put('TotalMonthlyEstimatedIncomeAmount',m.total+om.total); }
  }
  function send(el,body){
    var p=sendNow(el,body);
    inflight.push(p);
    var done=function(){ inflight=inflight.filter(function(x){return x!==p;}); };
    p.then(done,done);
    return p;
  }
  function sendNow(el,body){
    el.classList.remove('failed'); el.classList.add('saving');
    var url='/api/cases/'+id+'/fields/'+el.dataset.fid;
    if(el.dataset.ordinal && body.ordinal===undefined) body.ordinal=Number(el.dataset.ordinal);
    if(el.dataset.tf===undefined && el.dataset.tdp && body.data_point===undefined) body.data_point=el.dataset.tdp;
    // a copy of a section drawn for one dwelling or unit writes into that one
    if(el.dataset.tf===undefined && el.dataset.iscope && body.scope===undefined) body.scope=el.dataset.iscope;
    if(el.dataset.route) url='/api/cases/'+id+'/'+el.dataset.route;
    if(el.dataset.tf!==undefined){
      url='/api/cases/'+id+'/cells/'+el.dataset.tf;
      body.key=el.dataset.tk||''; body.data_point=body.data_point||el.dataset.tdp||'';
      body.sel=el.dataset.tsel||''; body.label=el.dataset.tlab||'';
      body.new=!!el.dataset.tnew; body.scope=el.dataset.tscope||''; body.cat=el.dataset.tcat||'';
    }
    return fetch(url,
      {method:'PATCH',headers:{'Content-Type':'application/json'},
       body:JSON.stringify(body)})
      .then(function(r){return r.json().then(function(d){return {ok:r.ok,d:d};});})
      .then(function(res){
        el.classList.remove('saving');
        if(!res.ok && res.d && res.d.confirm && res.d.lost){
          // a smaller count would remove units that hold answers: say which first
          var lines=['Making this count smaller removes these answers:'].concat(res.d.lost.slice(0,20));
          return ask(lines.join('\\n'),{title:'Remove the unit and what was entered for it?',ok:'Remove',danger:true})
            .then(function(ok){
              if(!ok){ el.textContent=el.dataset.was||''; return false; }
              body.confirm=true; return sendNow(el,body);
            });
        }
        if(!res.ok){
          el.classList.add('failed');
          el.title=(res.d && res.d.detail) || 'This value could not be saved.';
          return false;
        }
        el.title='';
        // a row just created: every cell on its line now writes into it
        if(el.dataset.tf!==undefined && res.d && res.d.key){
          var tr=el.closest('tr');
          [].forEach.call(tr?tr.querySelectorAll('[data-tf]'):[el],function(c){
            c.dataset.tk=res.d.key; delete c.dataset.tnew; delete c.dataset.tsel; delete c.dataset.tlab;
          });
          if(tr) tr.classList.remove('newrow');
        }
        // show it as the report prints it: "2352" typed, "2,352 Sq. Ft." shown
        if(res.d && typeof res.d.value==='string' && res.d.value && el.matches('.v[contenteditable]')
           && document.activeElement!==el){
          el.textContent=res.d.value; el.dataset.was=res.d.value;
        }
        if(el.dataset.tdp && RENT_POINTS[el.dataset.tdp]) rentTotals(el,res.d&&res.d.value);
        if(res.d && res.d.kind) el.dataset.kind=res.d.kind;
        if(res.d && res.d.case && el.dataset.fid==='2.003'){
          el.title=res.d.case==='A'?'Same party as the borrower (B-1 Case A)'
                  :res.d.case==='B'?'Same party as the seller (B-1 Case B)':'';
        }
        if(window.parent!==window) window.parent.postMessage({uad:'saved'},'*');
        // a line added to or taken from a numbered list (the additional
        // certifications): the numbering moves, so the page is laid out again
        if(res.d && res.d.relayout){ reloadHere(el.dataset.fid||''); return true; }
        // the answer changed what kind of property this is: the report has
        // been rebuilt on that shape (uad/shape.py) and the editor reloads it
        if(res.d && res.d.reshaped && window.parent!==window)
          window.parent.postMessage({uad:'reshaped',info:res.d.reshaped},'*');
        else if(res.d && res.d.structure && res.d.structure.length && window.parent!==window)
          window.parent.postMessage({uad:'structure',said:res.d.structure},'*');
        return true;
      })
      .catch(function(){el.classList.remove('saving');el.classList.add('failed');
        el.title='Connection lost. Your change was not saved.';return false;});
  }
  function commit(el){
    // commentary keeps its line breaks; a one-line value does not have any
    var now=(el.classList.contains('multiline')?el.innerText:el.textContent).trim();
    if(now===(el.dataset.was||'').trim()) return;
    el.dataset.was=now;
    send(el,{value:now});
  }
  /* A row the appraiser adds to a grid (DR §7).  Only the + under a group
     adds one: it puts one row on the page with its name box ready, and +
     again goes back to that row rather than adding a second.  The row is
     kept once it has a name -- against the subject and every comparable, so
     the grid reads as one row rather than four differently-named ones -- and
     one left without a name is taken away again.  A name is removed with
     its x, never by emptying the box. */
  function nameRow(el){
    if(el.classList.contains('saving')) return;
    var now=el.value.trim(), was=el.dataset.liwas||'', tr=el.closest('tr');
    if(now===was || !now){
      el.value=was;
      if(!was && tr && tr.classList.contains('linew')) tr.remove();
      return;
    }
    el.classList.remove('failed'); el.classList.add('saving');
    json(api+'/comparables/lineitems',
         {method:'PUT',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({kind:el.dataset.li,container:el.dataset.lic,
                               adjust_type:el.dataset.lit,was:was,name:now})})
      .then(function(){ el.classList.remove('saving'); el.dataset.liwas=now; reloadHere(); })
      .catch(function(err){ el.classList.remove('saving'); el.classList.add('failed');
                            el.title=err.message; say(err.message); });
  }
  function addRow(btn){
    var at=btn.closest('tr'), prev=at.previousElementSibling;
    if(prev && prev.classList.contains('linew')){ prev.querySelector('input.liin').focus(); return; }
    var tr=document.createElement('tr'); tr.className='linew';
    var td=document.createElement('td'); td.className='lbl liname';
    var input=document.createElement('input'); input.type='text'; input.className='liin';
    input.placeholder='Name this row'; input.spellcheck=false; input.setAttribute('aria-label','Row name');
    ['li','lic','lit'].forEach(function(k){ input.dataset[k]=btn.dataset[k]||''; });
    input.dataset.liwas='';
    td.appendChild(input); tr.appendChild(td);
    var rest=document.createElement('td'); rest.colSpan=Math.max(1,(at.cells[0].colSpan||2)-1);
    tr.appendChild(rest);
    at.parentNode.insertBefore(tr,at);
    input.focus();
  }
  /* a cell of a named row is written into that row: the group's rows share
     one field and one adjustment type, so the name says which */
  function lineOf(td,body){
    var tr=td.closest('tr'), li=tr&&tr.querySelector('input.liin');
    if(li&&li.dataset.liwas){ body.item_name=li.dataset.liwas; body.container=li.dataset.lic; body.line_type=li.dataset.lit; }
    return body;
  }
  document.addEventListener('focusout',function(e){
    var el=e.target;
    if(el.matches && el.matches('input.liin')) nameRow(el);
  });
  // pressing + leaves the focus in a row being named: taken away on the
  // blur, the row moved the + from under the pointer and nothing was added
  document.addEventListener('mousedown',function(e){
    if(e.target.closest && e.target.closest('.liaddbtn')) e.preventDefault();
  });
  document.addEventListener('keydown',function(e){
    var el=e.target;
    if(!el.matches || !el.matches('input.liin')) return;
    if(e.key==='Enter'){ e.preventDefault(); nameRow(el); el.blur(); }
    if(e.key==='Escape'){ e.preventDefault(); el.value=el.dataset.liwas||''; el.blur(); }
  });
  document.addEventListener('focusin',function(e){
    var el=e.target;
    if(el.matches && el.matches('.v[contenteditable]')) el.dataset.was=el.textContent;
  });
  document.addEventListener('focusout',function(e){
    var el=e.target;
    if(el.matches && el.matches('.v[contenteditable]')) commit(el);
  });
  document.addEventListener('keydown',function(e){
    var el=e.target;
    if(!el.matches || !el.matches('.v[contenteditable]')) return;
    // Enter commits here rather than leaning on the blur that follows it:
    // moving focus is the browser's business and does not always raise the
    // event first, and a value that looks accepted but was never sent is the
    // worst of the three outcomes.
    if(e.key==='Enter' && (!el.classList.contains('multiline') || e.ctrlKey || e.metaKey)){
      e.preventDefault();commit(el);el.blur();
    }
    if(e.key==='Escape'){e.preventDefault();el.textContent=el.dataset.was||'';el.blur();}
  });
  /* ------------------------------------------------------------ the lists
     Drawn inside the page rather than left to the browser: this page is laid
     out at three times size and scaled back down, and a native popup ignores
     that transform -- the list came up three times too big. */
  var openList=null, openOn=null;

  function shut(){
    pickSeq++;                     // a list still loading does not open after this
    if(openList) openList.remove();
    if(openOn) openOn.classList.remove('open');
    openList=openOn=null;
  }

  /* "Other" is never saved bare: A-1 requires its description (CR, IF the
     type is "Other"), and the description is what the report prints. */
  function describeOther(list,el,o){
    list.innerHTML='';
    var box=document.createElement('div'); box.className='otherbox';
    box.innerHTML='<label>Describe “Other”</label><input type="text"><div class="ob">'
      +'<button type="button" class="no">Cancel</button><button type="button" class="go">Save</button></div>';
    var input=box.querySelector('input');
    if(o.other.max) input.maxLength=o.other.max;
    list.appendChild(box);
    box.addEventListener('mousedown',function(ev){ ev.stopPropagation(); });
    var go=function(){
      var text=input.value.trim();
      if(!text){ input.focus(); input.classList.add('need'); return; }
      send(el,{value:'Other'}).then(function(ok){
        if(!ok) return;
        return send(el,{value:text,data_point:o.other.data_point}).then(function(ok2){
          if(ok2) el.textContent=text;
        });
      });
      shut();
    };
    box.querySelector('.go').onclick=go;
    box.querySelector('.no').onclick=function(){ shut(); };
    input.addEventListener('keydown',function(ev){
      if(ev.key==='Enter'){ ev.preventDefault(); go(); }
      if(ev.key==='Escape'){ ev.preventDefault(); shut(); }
    });
    setTimeout(function(){ input.focus(); },0);
  }
  // a field's choices are fetched once and kept: the second list opens at once
  var optCache={}, pickSeq=0;
  function optionsFor(el){
    var url='/api/fields/'+(el.dataset.fid||el.dataset.tf)+'/options'+(el.dataset.tdp?'?dp='+encodeURIComponent(el.dataset.tdp):'');
    if(!optCache[url]) optCache[url]=fetch(url).then(function(r){return r.json();})
      .catch(function(e){ delete optCache[url]; throw e; });
    return optCache[url];
  }
  function openPicker(el){
    if(openOn===el){ shut(); return; }
    shut(); shutEditor(); shutMenu();   // one list or editor open at a time
    var ticket=++pickSeq;          // only the last click's list opens
    optionsFor(el)
      .then(function(d){
        if(ticket!==pickSeq) return;
        if(openList) openList.remove();
        var list=document.createElement('div');
        list.className='picklist';
        var here=(el.textContent||'').trim();
        var rows=[{value:'',label:'\\u2014 not answered \\u2014',clear:true}]
          .concat(d.options||[]);
        // typed, not only picked: the list narrows as the appraiser types
        var find=document.createElement('input'); find.type='text'; find.className='pfind';
        find.placeholder='Type to find\u2026'; find.autocomplete='off';
        find.addEventListener('mousedown',function(ev){ ev.stopPropagation(); });
        find.addEventListener('input',function(){
          var t=find.value.trim().toLowerCase();
          [].forEach.call(list.querySelectorAll('div[data-pv]'),function(r){
            r.hidden=!!t&&r.textContent.toLowerCase().indexOf(t)<0; });
        });
        find.addEventListener('keydown',function(ev){
          if(ev.key==='Escape'){ ev.preventDefault(); shut(); return; }
          if(ev.key!=='Enter') return;
          ev.preventDefault();
          var hit=[].filter.call(list.querySelectorAll('div[data-pv]'),function(r){ return !r.hidden&&!r.classList.contains('clear'); })[0];
          if(hit) hit.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true}));
        });
        if((d.options||[]).length>6){ list.appendChild(find); setTimeout(function(){ find.focus(); },0); }
        rows.forEach(function(o){
          var row=document.createElement('div');
          row.textContent=o.label; row.dataset.pv=o.value;
          if(o.clear) row.className='clear';
          if(o.label===here||o.value===here) row.className='on';
          row.addEventListener('mousedown',function(ev){
            ev.preventDefault();
            if(o.other){ ev.stopPropagation(); describeOther(list,el,o); return; }
            send(el,{value:o.value}).then(function(ok){
              if(ok) el.textContent=o.value?o.label:'';
            });
            shut();
          });
          list.appendChild(row);
        });
        // Positioned within the scaled page, so it scales with it.
        var host=el.closest('.hz')||el.offsetParent||document.body;
        host.appendChild(list);
        var a=el.getBoundingClientRect(), b=host.getBoundingClientRect();
        var scale=(host.getBoundingClientRect().width/host.offsetWidth)||1;
        list.style.left=((a.left-b.left)/scale)+'px';
        list.style.top=((a.bottom-b.top)/scale)+'px';
        openList=list; openOn=el; el.classList.add('open');
      });
  }

  document.addEventListener('mousedown',function(e){
    var el=e.target.closest && e.target.closest('.v.pick');
    if(el){ e.preventDefault(); openPicker(el); return; }
    if(!e.target.closest || !e.target.closest('.picklist')) shut();
  });
  document.addEventListener('keydown',function(e){
    if(e.key==='Escape') shut();
    var el=e.target.closest && e.target.closest('.v.pick');
    if(el && (e.key==='Enter'||e.key===' ')){e.preventDefault();openPicker(el);}
  });
  window.addEventListener('scroll',shut,true);

  /* ---------------------------------------------------------------- images
     A photograph reaches a section three ways, because appraisers work all
     three: the file dialog, a drag from a folder, and a paste from whatever
     took the screenshot. */
  var lastZone=null;
  var api='/api/cases/'+id;

  function json(url,opts){
    return fetch(url,opts).then(function(r){
      return r.json().catch(function(){return {};}).then(function(d){
        if(!r.ok) throw new Error((d&&d.detail)||('HTTP '+r.status));
        return d;});
    });
  }
  /* The location map: drawn by the map tool in the background, while its own
     box on the page says so.  Nothing else on the page moves. */
  function loadMap(btn){
    var fig=btn.closest('figure')||btn.closest('.exaddrow'), note=fig.querySelector('.mapstate');
    var aerial=btn.dataset.map==='aerial';
    fig.classList.remove('mapfailed'); fig.classList.add('maploading');
    note.textContent=aerial?'Loading aerial map…':'Loading location map…';
    json(api+(aerial?'/maps/aerial':'/maps'),{method:'POST'}).then(function(st){
      if(st.state!=='browser') return st;
      // no map tool on this server (the live site): this browser draws it
      return drawHere(aerial).then(function(d){
        return d.ok?{state:'current',problems:[]}:{state:'failed',problems:[d.error].concat(st.problems||[])};
      });
    }).then(function(st){
      if(aerial && st.state==='current'){ tell({uad:'media'}); reloadHere(); return; }
      if(st.state==='current'){ note.textContent='Placing the map in the report…'; reloadHere(); return; }
      fig.classList.remove('maploading'); fig.classList.add('mapfailed');
      note.textContent=((st.problems||[]).join('; ')||'The map could not be made yet.')
        +(aerial?'':' Enter the subject and comparable addresses, then load the map again.');
    }).catch(function(err){
      fig.classList.remove('maploading'); fig.classList.add('mapfailed');
      note.textContent='The map could not be loaded: '+err.message;
    });
  }
  /* The Location Map tool, run out of sight in this browser, draws the map and
     saves it (app/ui/map/draw.js) -- the editor's copy when there is one. */
  function drawHere(aerial){
    var d=null; try{ d=window.top.UADDrawMap; }catch(_){}
    if(d) return d(id,{aerial:aerial});
    return new Promise(function(res){
      var s=document.createElement('script'); s.src='/ui/map/draw.js';
      s.onload=function(){ res(window.UADDrawMap(id,{aerial:aerial})); };
      s.onerror=function(){ res({ok:false,error:'the map tool could not be loaded'}); };
      document.head.appendChild(s);
    });
  }
  /* The map is edited inside its own box: the map tool opens there at the
     box's exact size, and what is saved is what prints. */
  var mapFrame=null;
  function editMap(btn){
    var fig=btn.closest('figure');
    if(mapFrame) return;
    fig.classList.add('mapediting');
    mapFrame=document.createElement('iframe');
    mapFrame.className='mapframe';
    mapFrame.title='Sales Comparison Map';
    mapFrame.src='/ui/map/index.html?case='+encodeURIComponent(id)+'&embed=1';
    fig.appendChild(mapFrame);
  }
  window.addEventListener('message',function(e){
    var m=e.data||{};
    if(!mapFrame || e.source!==mapFrame.contentWindow) return;
    var fig=mapFrame.closest('figure');
    if(m.uad==='map-cancel'){
      mapFrame.remove(); mapFrame=null; fig.classList.remove('mapediting');
    }
    if(m.uad==='map-saved'){
      mapFrame.remove(); mapFrame=null; fig.classList.remove('mapediting');
      fig.classList.add('maploading');
      var note=fig.querySelector('.mapstate'); if(note) note.textContent='Placing the map in the report…';
      tell({uad:'media'}); reloadHere();
    }
  });
  /* ------------------------------------------------ Save, beside each page
     Every value is already written the moment it is entered; Save confirms it
     -- it finishes any edit still open, waits for the writes on their way, and
     checks the sections on the page against the Review Master (H-1 compliance
     and the schema).  Anything fatal or a warning is listed, each item a link
     to its field, with "Save anyway" to accept the page as it stands.  The
     sections rail then shows each saved section green, orange or red. */
  function pageSections(pg){
    var have={};
    [].forEach.call(pg.querySelectorAll('[data-secn]'),function(x){ if(Number(x.dataset.secn)) have[x.dataset.secn]=1; });
    return Object.keys(have).map(Number);
  }
  function blanksOn(pg){
    return [].filter.call(pg.querySelectorAll('.v[contenteditable]:not(.multiline),.v.pick,.bxs.untouched'),function(x){
      return x.classList.contains('bxs') || !x.textContent.trim();
    });
  }
  function markSaved(secs){
    return json(api+'/prefs').then(function(p){
      var saved=p.savedSections||{}, now=new Date().toISOString();
      secs.forEach(function(n){ saved[n]=now; });
      return putJSON(api+'/prefs',{savedSections:saved});
    }).then(function(){ tell({uad:'saved-sections',sections:secs}); });
  }
  function closeChecks(){ [].forEach.call(document.querySelectorAll('.savecheck'),function(x){x.remove();}); }
  function savePage(pg,side,next){
    closeChecks();
    var a=document.activeElement;
    if(a&&a.matches&&a.matches('.v[contenteditable],.capedit')) a.blur();
    var btns=side.querySelectorAll('button');
    [].forEach.call(btns,function(b){b.disabled=true;});
    var main=side.querySelector('.pgsave'); main.textContent='Checking\u2026';
    var secs=pageSections(pg);
    var finish=function(){
      [].forEach.call(btns,function(b){b.disabled=false;});
      main.textContent='Save';
    };
    Promise.all(inflight.slice()).catch(function(){}).then(function(){
      var failed=pg.querySelectorAll('.failed').length;
      return json(api+'/review').then(function(rv){
        var items=(rv.items||[]).filter(function(i){
          return secs.indexOf(i.section_number)>=0 && (i.severity==='Fatal'||i.severity==='Warning');
        });
        var blanks=blanksOn(pg);
        finish();
        if(!items.length && !failed){
          markSaved(secs).then(function(){
            side.classList.add('ok'); main.textContent='Saved \u2713';
            setTimeout(function(){ side.classList.remove('ok'); main.textContent='Save'; },1800);
            if(next) goNext(pg);
          });
          return;
        }
        var box=document.createElement('div'); box.className='savecheck';
        var fatal=items.filter(function(i){return i.severity==='Fatal';});
        var warn=items.filter(function(i){return i.severity==='Warning';});
        var html='<div class="sch">'+(fatal.length||failed?'Not UAD compliant yet':'Warnings on this page')+'</div>';
        if(failed) html+='<div class="sci bad">'+failed+' value(s) on this page did not save \u2014 they are outlined in red.</div>';
        fatal.forEach(function(i,n){ html+='<a class="sci bad" data-i="f'+n+'">'+esc(i.message)+'</a>'; });
        warn.forEach(function(i,n){ html+='<a class="sci warn" data-i="w'+n+'">'+esc(i.message)+'</a>'; });
        if(blanks.length) html+='<a class="sci blank" data-i="b">'+blanks.length+' field(s) on this page are still blank.</a>';
        html+='<div class="scb"><button type="button" class="keep">Keep editing</button>'
          +'<button type="button" class="anyway">Save anyway</button></div>';
        box.innerHTML=html;
        side.appendChild(box);
        box.addEventListener('click',function(ev){
          var t=ev.target;
          if(t.classList.contains('keep')){ box.remove(); return; }
          if(t.classList.contains('anyway')){
            box.remove();
            markSaved(secs).then(function(){
              main.textContent='Saved as is';
              setTimeout(function(){ main.textContent='Save'; },1800);
              if(next) goNext(pg);
            });
            return;
          }
          var link=t.closest('.sci[data-i]'); if(!link) return;
          var k=link.dataset.i;
          if(k==='b'){ var b=blanks[0]; if(b){ b.scrollIntoView({block:'center'}); flash(b); if(b.focus) b.focus(); } return; }
          var it=(k[0]==='f'?fatal:warn)[Number(k.slice(1))];
          if(!(it.field_id && goField(it.field_id))) goSection(it.section_number);
        });
      });
    }).catch(function(err){ finish(); say('The page could not be checked: '+err.message); });
  }
  function goNext(pg){
    var n=pg.nextElementSibling;
    while(n && !(n.classList&&n.classList.contains('page'))) n=n.nextElementSibling;
    if(n) window.scrollTo({top:n.getBoundingClientRect().top+window.scrollY-8,behavior:'smooth'});
  }
  function esc(s){ return String(s||'').replace(/[&<>"]/g,function(c){return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c];}); }
  var sides=[];
  function placeSides(){
    sides.forEach(function(x){
      var r=x.pg.getBoundingClientRect();
      x.side.style.left=(r.right+window.scrollX+14)+'px';
      x.side.style.top=(r.top+window.scrollY+56)+'px';
    });
  }
  function buildSides(){
    [].forEach.call(document.querySelectorAll('.page'),function(pg){
      var side=document.createElement('div'); side.className='pageside';
      side.innerHTML='<button type="button" class="pgsave">Save</button>'
        +'<button type="button" class="pgnext">Save &amp; Next</button>';
      side.querySelector('.pgsave').onclick=function(){ savePage(pg,side,false); };
      side.querySelector('.pgnext').onclick=function(){ savePage(pg,side,true); };
      document.body.appendChild(side);
      sides.push({pg:pg,side:side});
    });
    placeSides();
  }
  window.addEventListener('resize',function(){ requestAnimationFrame(placeSides); });
  if(document.readyState==='complete') setTimeout(buildSides,0);
  else window.addEventListener('load',buildSides);

  /* A party's name: a person's, split into first/middle/last/suffix, or an
     organisation's full name -- the appraiser says which. */
  var kindChip=null;
  function nameKind(el){
    if(kindChip) kindChip.remove();
    kindChip=document.createElement('div'); kindChip.className='namekind';
    var kind=el.dataset.kind||'';
    kindChip.innerHTML='<span data-k="person">Person</span><span data-k="entity">Company</span>';
    [].forEach.call(kindChip.children,function(c){ c.classList.toggle('on',c.dataset.k===kind); });
    kindChip.addEventListener('mousedown',function(ev){
      ev.preventDefault(); ev.stopPropagation();
      var k=ev.target.dataset.k; if(!k) return;
      el.dataset.kind=k;
      [].forEach.call(kindChip.children,function(c){ c.classList.toggle('on',c.dataset.k===k); });
      send(el,{value:el.innerText.trim(),kind:k});
    });
    var host=el.closest('.hz')||document.body;
    host.appendChild(kindChip);
    var a=el.getBoundingClientRect(), b=host.getBoundingClientRect();
    var scale=(b.width/host.offsetWidth)||1;
    kindChip.style.left=((a.right-b.left)/scale+3)+'px';
    kindChip.style.top=((a.top-b.top)/scale)+'px';
  }
  document.addEventListener('focusin',function(e){
    var el=e.target.closest&&e.target.closest('[data-name]');
    if(el) nameKind(el);
  });
  document.addEventListener('focusout',function(e){
    var el=e.target.closest&&e.target.closest('[data-name]');
    if(el) setTimeout(function(){ if(kindChip&&!kindChip.matches(':hover')){ kindChip.remove(); kindChip=null; } },200);
  });
  function putJSON(url,body,method){
    return json(url,{method:method||'PUT',headers:{'Content-Type':'application/json'},
                     body:JSON.stringify(body)}).then(function(res){
      // an applied adjustment worksheet followed the change: show its new figures
      if(res&&res.recalculated&&res.recalculated.length) tell({uad:'relayout'});
      return res;
    });
  }

  /* ------------------------------------------------ exhibit boxes (slots)
     "+ Add Exhibit" puts an empty box into the section -- the report's own
     grey box with a camera and a name to type above it.  It is kept with the
     editor's state until a picture goes in, and the report is laid out again
     so everything below moves down to make room. */
  var slotChain=null;       // a new box's name waits until the box is saved
  /* ------------------------------------------------ the signature
     The signer signs where the signature prints: drawn with the mouse or a
     finger, typed and set in a hand, or a picture of it.  It is kept with the
     case as an image (category "signature") and drawn above the line. */
  function signaturePad(btn){
    var n=btn.dataset.signer||'1', old=btn.dataset.media||'';
    if(!document.getElementById('sgpad-style')){
      var st=document.createElement('style'); st.id='sgpad-style';
      st.textContent='.sgveil{position:fixed;inset:0;z-index:9999;background:rgba(0,0,0,.45);display:flex;align-items:center;justify-content:center;font-family:system-ui,sans-serif}'
        +'.sgpanel{background:#fff;color:#111;border-radius:12px;padding:16px 18px;width:min(640px,94vw);box-shadow:0 20px 60px rgba(0,0,0,.35)}'
        +'.sgpanel h4{margin:0 0 10px;font-size:16px}.sgtabs{display:flex;gap:6px;margin-bottom:10px}'
        +'.sgtabs button{border:1px solid #ccd;background:#f4f5f8;border-radius:8px;padding:6px 12px;cursor:pointer;font-size:13px}'
        +'.sgtabs button.on{background:#1d4f91;color:#fff;border-color:#1d4f91}'
        +'.sgcanvas{display:block;width:100%;height:180px;border:1px dashed #9aa;border-radius:8px;background:#fff;touch-action:none;cursor:crosshair}'
        +'.sgtype{width:100%;box-sizing:border-box;font-size:15px;padding:8px;border:1px solid #ccd;border-radius:8px;margin-bottom:8px}'
        +'.sgfoot{display:flex;justify-content:space-between;gap:8px;margin-top:12px;align-items:center}'
        +'.sgfoot .r{display:flex;gap:8px}.sgfoot button{border:1px solid #ccd;background:#fff;border-radius:8px;padding:7px 14px;cursor:pointer;font-size:13px}'
        +'.sgfoot button.go{background:#111;color:#fff;border-color:#111}.sgfoot button.rm{color:#b42318;border-color:#f2b8b5}'
        +'.sgnote{font-size:12px;color:#667}';
      document.head.appendChild(st);
    }
    var veil=document.createElement('div'); veil.className='sgveil';
    veil.innerHTML='<div class="sgpanel" role="dialog" aria-modal="true"><h4>Signature</h4>'
      +'<div class="sgtabs"><button type="button" data-t="draw" class="on">Draw</button><button type="button" data-t="type">Type</button><button type="button" data-t="file">Upload</button></div>'
      +'<input class="sgtype" type="text" placeholder="Type your full name" hidden>'
      +'<canvas class="sgcanvas" width="1200" height="360"></canvas>'
      +'<div class="sgfoot"><span class="sgnote">Sign in the box with your mouse or finger.</span><div class="r">'
      +(old?'<button type="button" class="rm">Remove</button>':'')
      +'<button type="button" class="clr">Clear</button><button type="button" class="no">Cancel</button><button type="button" class="go">Save signature</button></div></div></div>';
    document.body.appendChild(veil);
    var cv=veil.querySelector('canvas'), cx=cv.getContext('2d'), typed=veil.querySelector('.sgtype'), note=veil.querySelector('.sgnote');
    var inked=false, mode='draw', drawing=false;
    function blank(){ cx.clearRect(0,0,cv.width,cv.height); inked=false; }
    cx.lineCap='round'; cx.lineJoin='round'; cx.lineWidth=5; cx.strokeStyle='#0b1f4a';
    function pt(e){ var r=cv.getBoundingClientRect(); return [(e.clientX-r.left)*cv.width/r.width,(e.clientY-r.top)*cv.height/r.height]; }
    cv.addEventListener('pointerdown',function(e){ if(mode!=='draw') return; drawing=true; cv.setPointerCapture(e.pointerId); var p=pt(e); cx.beginPath(); cx.moveTo(p[0],p[1]); });
    cv.addEventListener('pointermove',function(e){ if(!drawing) return; var p=pt(e); cx.lineTo(p[0],p[1]); cx.stroke(); inked=true; });
    cv.addEventListener('pointerup',function(){ drawing=false; });
    function setType(){
      blank(); var t=typed.value.trim(); if(!t) return;
      cx.fillStyle='#0b1f4a'; var size=150;
      do{ cx.font='italic '+size+'px "Brush Script MT","Segoe Script","Lucida Handwriting",cursive'; size-=6; }
      while(cx.measureText(t).width>cv.width-60 && size>40);
      cx.textBaseline='middle'; cx.fillText(t,30,cv.height/2); inked=true;
    }
    typed.addEventListener('input',setType);
    function tab(t){
      mode=t; veil.querySelectorAll('.sgtabs button').forEach(function(b){ b.classList.toggle('on',b.dataset.t===t); });
      typed.hidden=t!=='type'; blank();
      note.textContent={draw:'Sign in the box with your mouse or finger.',type:'Your name, set in a handwritten style.',file:'A picture of your signature (PNG or JPEG).'}[t];
      if(t==='type'){ typed.focus(); setType(); }
      if(t==='file'){
        var inp=document.createElement('input'); inp.type='file'; inp.accept='image/*';
        inp.onchange=function(){ var f=inp.files[0]; if(!f) return; var img=new Image();
          img.onload=function(){ blank(); var k=Math.min(cv.width/img.width,cv.height/img.height);
            cx.drawImage(img,(cv.width-img.width*k)/2,(cv.height-img.height*k)/2,img.width*k,img.height*k); inked=true; };
          img.src=URL.createObjectURL(f); };
        inp.click();
      }
    }
    veil.querySelectorAll('.sgtabs button').forEach(function(b){ b.onclick=function(){ tab(b.dataset.t); }; });
    function close(){ veil.remove(); }
    veil.querySelector('.no').onclick=close;
    veil.querySelector('.clr').onclick=function(){ blank(); typed.value=''; };
    var rm=veil.querySelector('.rm');
    if(rm) rm.onclick=function(){
      json(api+'/media/'+old,{method:'DELETE'}).then(function(){ close(); tell({uad:'media'}); reloadHere(); });
    };
    veil.querySelector('.go').onclick=function(){
      if(!inked){ note.textContent='Sign first — draw, type or upload your signature.'; return; }
      // on the line at once; saved in the background
      var spot=btn.parentNode, shown=spot.querySelector('img.sgimg');
      if(!shown){ shown=document.createElement('img'); shown.className='sgimg'; shown.alt='Signature';
        [].slice.call(spot.childNodes).forEach(function(c){ if(c!==btn) c.remove(); });
        spot.insertBefore(shown,btn); }
      shown.src=cv.toDataURL('image/png');
      btn.textContent='Change signature'; btn.classList.add('has');
      veil.style.display='none';
      cv.toBlob(function(blob){
        var fd=new FormData(); fd.append('file',blob,'signature-'+n+'.png');
        json(api+'/media?category=signature&section=29&caption='+encodeURIComponent('Signature '+n),{method:'POST',body:fd})
          .then(function(){ return old?json(api+'/media/'+old,{method:'DELETE'}).catch(function(){}):null; })
          .then(function(){ close(); tell({uad:'media'}); reloadHere(); })
          .catch(function(err){ veil.style.display=''; note.textContent='The signature could not be saved: '+err.message; });
      },'image/png');
    };
  }
  document.addEventListener('click',function(e){
    var b=e.target.closest && e.target.closest('.sgsign');
    if(b){ e.preventDefault(); signaturePad(b); }
  });

  function slots(){ return json(api+'/prefs').then(function(p){ return p.exhibitSlots||[]; }); }
  function saveSlots(list){ return putJSON(api+'/prefs',{exhibitSlots:list}); }

  /* The new box is on the page the moment the button is pressed, with the
     caret in its name; the exact layout follows behind it. */
  function showSlot(button,sid,quiet){
    var holder=button.closest('.blk');
    if(!holder) return null;
    var fig=document.createElement('figure'); fig.className='ex';
    var sample=document.querySelector('figure.ex .ph');
    fig.innerHTML='<div class="cap"><b class="capedit" contenteditable="true" spellcheck="false"'
      +' data-ph="Exhibit Name" data-slot="'+sid+'"></b></div>'
      +(sample?'<div class="ph">'+sample.innerHTML+'</div>':'<div class="ph"><span></span></div>')
      +'<span class="exdrop" data-section="'+button.dataset.section+'" data-name="'
      +(button.dataset.name||'')+'" data-caption="" data-slot="'+sid+'"></span>'
      +'<span class="exremove" role="button" aria-label="Remove" data-slot="'+sid+'">&times;</span>';
    var span=fig.querySelector('.ph span'); if(span) span.textContent='This is where the exhibit photo would display.';
    var prev=holder.previousElementSibling;
    var row=prev&&prev.querySelector&&prev.querySelector('.exhibits');
    if(row&&row.children.length===1){ row.appendChild(fig); }
    else{
      var blk=document.createElement('div'); blk.className='blk solid exhibits';
      var wrap=document.createElement('div'); wrap.className='exhibits'; wrap.appendChild(fig);
      blk.appendChild(wrap); holder.parentNode.insertBefore(blk,holder);
    }
    // Shown at once only while the page still has room for it.  A box that
    // would cross the footer waits for the report to be laid out again -- the
    // page never shows content over its own footer, not even for a moment.
    var page=fig.closest('.page');
    if(page){
      var pr=page.getBoundingClientRect(), fr=fig.getBoundingClientRect();
      var limit=pr.top+pr.height*(__BODY_BOTTOM__/1008);
      var band=page.querySelector('.band'), low=fr.bottom;
      if(band) [].forEach.call(band.querySelectorAll(':scope > .blk'),function(b){
        var r=b.getBoundingClientRect(); if(r.height>0) low=Math.max(low,r.bottom);
      });
      if(low>limit){
        var solo=fig.parentNode.children.length===1;
        (solo?fig.closest('.blk'):fig).remove();
        button.classList.add('pending'); button.textContent='Adding exhibit…';
        return null;
      }
    }
    var cap=fig.querySelector('.capedit');
    if(quiet) return fig;
    cap.dataset.was=''; cap.focus();
    return fig;
  }

  /* A picture is on the page the moment it is chosen -- read from the
     appraiser's own disk, not waited for from the server -- and the box says
     it is on its way until the laid-out report, with the saved picture,
     replaces this one. */
  function showLocal(zone,file,i){
    var url;
    try{ url=URL.createObjectURL(file); }catch(_){ return; }
    var img=document.createElement('img'); img.src=url; img.alt=''; img.className='uad-local';
    if(zone.classList.contains('exadd')){
      if(!parentWin) return;
      var fig=showSlot(zone,'local'+Date.now().toString(36)+(i||0),true);
      if(!fig) return;
      var ph=fig.querySelector('.ph'); if(ph) ph.replaceWith(img);
      var cap=fig.querySelector('.capedit');
      if(cap){ cap.removeAttribute('contenteditable');
        cap.textContent=(file.name||'').replace(/\\.[^.]+$/,'').replace(/[_-]+/g,' '); }
      var rm=fig.querySelector('.exremove'); if(rm) rm.remove();
      fig.classList.add('uad-pending');
      return;
    }
    var box=zone.closest('figure');
    if(box){
      var old=box.querySelector('img'), ph2=box.querySelector('.ph');
      if(old) old.src=url; else if(ph2) ph2.replaceWith(img);
      box.classList.add('uad-pending');
      return;
    }
    var photo=zone.closest('.photo');
    if(photo){
      var im=photo.querySelector('img');
      if(im) im.src=url;
      else{
        [].slice.call(photo.children).forEach(function(c){ if(c!==zone) c.remove(); });
        [].slice.call(photo.childNodes).forEach(function(c){ if(c.nodeType===3) c.remove(); });
        photo.insertBefore(img,zone); photo.classList.remove('empty');
      }
      photo.classList.add('uad-pending');
    }
  }
  function going(el){ if(el) el.classList.add('uad-removing'); }

  function addSlot(section,button){
    var sid='x'+Date.now().toString(36)+Math.random().toString(36).slice(2,6);
    if(button&&parentWin) showSlot(button,sid);
    return slotChain=slots().then(function(list){
      list.push({id:sid,section:Number(section),caption:''});
      return saveSlots(list);
    }).then(function(){
      try{ sessionStorage.setItem('uad-focus-'+id,sid); }catch(_){}
      reloadHere();
    });
  }
  function dropSlot(sid){
    return slots().then(function(list){
      return saveSlots(list.filter(function(x){return x.id!==sid;}));
    });
  }
  function nameSlot(sid,caption){
    return slots().then(function(list){
      list.forEach(function(x){ if(x.id===sid) x.caption=caption; });
      return saveSlots(list);
    });
  }
  // the name of a box just added gets the caret, ready to type
  window.addEventListener('load',function(){
    var sid=null;
    try{ sid=sessionStorage.getItem('uad-focus-'+id); sessionStorage.removeItem('uad-focus-'+id); }catch(_){}
    if(!sid) return;
    var cap=document.querySelector('.capedit[data-slot="'+sid+'"]');
    if(cap){ cap.scrollIntoView({block:'center'}); cap.focus(); }
  });

  function captionOf(zone){
    var fig=zone.closest && zone.closest('figure');
    var cap=fig && fig.querySelector('.capedit');
    return cap ? cap.textContent.trim() : (zone.dataset.caption||'');
  }

  function upload(zone,files){
    var list=[].slice.call(files||[]).filter(function(f){
      return f && /^image\\//.test(f.type);});
    if(!list.length) return;
    if(zone.dataset.slot||zone.dataset.fill||zone.classList.contains('photodrop')) list=list.slice(0,1);
    list.forEach(function(file,i){ showLocal(zone,file,i); });
    zone.classList.remove('over');
    var section=zone.dataset.section||'0';
    var category=zone.dataset.category||'other';
    var jobs=list.map(function(file){
      var fd=new FormData();
      fd.append('file',file,file.name||'pasted.png');
      var name=zone.classList.contains('exadd')
        ? (file.name||'').replace(/\\.[^.]+$/,'').replace(/[_-]+/g,' ')
        : captionOf(zone);
      var q='?category='+encodeURIComponent(category)
           +'&section='+encodeURIComponent(section)
           +'&caption='+encodeURIComponent(name||'');
      if(zone.dataset.comparable) q+='&comparable='+encodeURIComponent(zone.dataset.comparable);
      return json(api+'/media'+q,{method:'POST',body:fd}).then(function(m){
        if(zone.dataset.slot) return dropSlot(zone.dataset.slot);
        if(zone.dataset.fill) return json(api+'/prefs').then(function(p){
          var fills=p.fills||{}; fills[zone.dataset.fill]=m.media_id;
          return putJSON(api+'/prefs',{fills:fills});
        });
      });
    });
    Promise.all(jobs)
      .catch(function(err){ zone.classList.add('failed'); say('The picture could not be added: '+err.message); })
      .then(function(){ tell({uad:'media'}); reloadHere(); });
  }

  function browse(zone){
    var input=document.createElement('input');
    input.type='file'; input.accept='image/*';
    input.multiple=zone.classList.contains('exadd');
    input.style.display='none';
    document.body.appendChild(input);
    input.addEventListener('change',function(){
      upload(zone,input.files); input.remove();});
    input.click();
  }

  /* An exhibit's name is typed where it prints, above the picture. */
  document.addEventListener('focusout',function(e){
    var cap=e.target.closest && e.target.closest('.capedit');
    if(!cap) return;
    var now=cap.textContent.trim();
    if(now===(cap.dataset.was||'')) return;
    cap.dataset.was=now;
    var job=cap.dataset.image
      ? putJSON(api+'/images',{key:cap.dataset.image,caption:now},'PATCH')
      : cap.dataset.slot
      ? (slotChain||Promise.resolve()).then(function(){ return nameSlot(cap.dataset.slot,now); })
      : putJSON(api+'/media/'+cap.dataset.media,{caption:now},'PATCH');
    job.then(function(){
      // the empty box says whose photo it is waiting for
      var ph=cap.closest('figure').querySelector('.ph span');
      if(ph) ph.textContent='This is where the '+(now.replace(/ *[(].*/,'')||'exhibit')+' photo would display.';
    }).catch(function(err){ cap.classList.add('failed'); cap.title=err.message; });
  });
  document.addEventListener('focusin',function(e){
    var cap=e.target.closest && e.target.closest('.capedit');
    if(cap) cap.dataset.was=cap.textContent.trim();
  });

  document.addEventListener('keydown',function(e){
    var z=e.target.closest && e.target.closest('.exadd,.compadd,.nuadd,.nudrop,.lidrop,.liaddbtn');
    if(z && (e.key==='Enter'||e.key===' ')){ e.preventDefault(); z.click(); return; }
    var cap=e.target.closest && e.target.closest('.capedit');
    if(cap && e.key==='Enter'){ e.preventDefault(); cap.blur(); }
  });

  /* ------------------------------------------------------- comparables
     Another comparable joins the last block of three or opens a new block on
     the next page, as the printed report lays it out (Appendix E p62). */
  var menu=null;
  function shutMenu(){ if(menu){ menu.remove(); menu=null; } }
  function openCompMenu(th){
    shutMenu();
    var n=Number(th.dataset.compmenu);
    var list=document.createElement('div'); list.className='picklist';
    // how many sales comparables the grid shows (one header cell each)
    var count=0;
    document.querySelectorAll('th[data-compmenu]').forEach(function(h){ count=Math.max(count,Number(h.dataset.compmenu)||0); });
    function item(text,run){
      var r=document.createElement('div'); r.textContent=text;
      r.addEventListener('mousedown',function(ev){ ev.preventDefault(); shutMenu(); run(); });
      list.appendChild(r);
    }
    // WinTOTAL moves a comparable left / right and copies it; the number is
    // what the whole report refers to it by, so a move renumbers the photos,
    // the transfer history and the map with it (api /comparables/order)
    function swap(to){
      var order=[]; for(var i=1;i<=count;i++) order.push(i);
      order[n-1]=to; order[to-1]=n;
      going(th);
      json(api+'/comparables/order',{method:'POST',headers:{'Content-Type':'application/json'},
        body:JSON.stringify({kind:'sales',order:order})})
        .then(function(){ tell({uad:'media'}); tell({uad:'saved'}); reloadHere(); })
        .catch(function(err){ say(err.message); });
    }
    if(n>1) item('\u2190 Move left (becomes #'+(n-1)+')',function(){ swap(n-1); });
    if(n<count) item('Move right (becomes #'+(n+1)+') \u2192',function(){ swap(n+1); });
    item('Copy as Comparable #'+(count+1),function(){
      going(th);
      json(api+'/comparables/'+n+'/copy?kind=sales',{method:'POST'})
        .then(function(){ tell({uad:'saved'}); reloadHere(); })
        .catch(function(err){ say(err.message); });
    });
    var row=document.createElement('div'); row.textContent='Remove Comparable #'+n;
    row.addEventListener('mousedown',function(ev){
      ev.preventDefault(); shutMenu();
      ask('The comparables after it move up a place.',{title:'Remove Comparable #'+n+'?',ok:'Remove',danger:true}).then(function(ok){
        if(!ok) return;
        going(th);
        json(api+'/comparables/'+n+'?kind=sales',{method:'DELETE'})
          .then(function(){ tell({uad:'media'}); reloadHere(); })
          .catch(function(err){ say(err.message); });
      });
    });
    list.appendChild(row);
    place(list,th);
    menu=list;
  }
  function place(el,anchor){
    var host=anchor.closest('.hz')||document.body;
    host.appendChild(el);
    var a=anchor.getBoundingClientRect(), b=host.getBoundingClientRect();
    var scale=(b.width/host.offsetWidth)||1;
    el.style.left=((a.left-b.left)/scale)+'px';
    el.style.top=((a.bottom-b.top)/scale)+'px';
  }

  /* ----------------------------------------------------------- rooms
     A level's rooms are counted where the report lists them: - and + on
     each line, "+ Add room" for another type, x to take a level out with its
     rooms.  Levels in Unit, Total Bedrooms and Bathrooms follow (rooms.py). */
  function roomsDone(){ tell({uad:'saved'}); reloadHere(); }
  function roomsFail(err){ say(err.message,{title:'The rooms were not changed'}); }
  function addRoom(el,type,other){
    going(el.closest('td'));
    json(api+'/rooms',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({level:el.dataset.level,type:type,other:other||''})})
      .then(roomsDone).catch(roomsFail);
  }
  function otherRoom(list,el){
    list.innerHTML='';
    var box=document.createElement('div'); box.className='otherbox';
    box.innerHTML='<label>Describe the room</label><input type="text" maxlength="50"><div class="ob">'
      +'<button type="button" class="no">Cancel</button><button type="button" class="go">Add</button></div>';
    var input=box.querySelector('input');
    list.appendChild(box);
    box.addEventListener('mousedown',function(ev){ ev.stopPropagation(); });
    var go=function(){
      var text=input.value.trim();
      if(!text){ input.focus(); input.classList.add('need'); return; }
      shutMenu(); addRoom(el,'Other',text);
    };
    box.querySelector('.go').onclick=go;
    box.querySelector('.no').onclick=function(){ shutMenu(); };
    input.addEventListener('keydown',function(ev){
      if(ev.key==='Enter'){ ev.preventDefault(); go(); }
      if(ev.key==='Escape'){ ev.preventDefault(); shutMenu(); }
    });
    setTimeout(function(){ input.focus(); },0);
  }
  function roomPick(el){
    shut(); shutMenu();
    fetch('/api/fields/10.033/options').then(function(r){return r.json();}).then(function(d){
      var list=document.createElement('div'); list.className='picklist';
      (d.options||[]).forEach(function(o){
        if(!o.value) return;
        var row=document.createElement('div'); row.textContent=o.label;
        row.addEventListener('mousedown',function(ev){
          ev.preventDefault(); ev.stopPropagation();
          if(o.value==='Other'){ otherRoom(list,el); return; }
          shutMenu(); addRoom(el,o.value,'');
        });
        list.appendChild(row);
      });
      place(list,el); menu=list;
    });
  }
  function floorPick(el){
    shut(); shutMenu();
    fetch('/api/fields/10.045/options?dp=FlooringType').then(function(r){return r.json();}).then(function(d){
      var list=document.createElement('div'); list.className='picklist';
      (d.options||[]).forEach(function(o){
        if(!o.value) return;
        var row=document.createElement('div'); row.textContent=o.label;
        row.addEventListener('mousedown',function(ev){
          ev.preventDefault(); ev.stopPropagation();
          if(o.value==='Other'){ otherFloor(list,el); return; }
          shutMenu(); addFloor(el,o.value,'');
        });
        list.appendChild(row);
      });
      place(list,el); menu=list;
    });
  }
  function addFloor(el,type,other){
    going(el.closest('tr'));
    json(api+'/flooring',{method:'POST',headers:{'Content-Type':'application/json'},
      body:JSON.stringify({unit:el.dataset.unit,type:type,other:other||''})})
      .then(roomsDone).catch(roomsFail);
  }
  function otherFloor(list,el){
    list.innerHTML='';
    var box=document.createElement('div'); box.className='otherbox';
    box.innerHTML='<label>Describe the flooring</label><input type="text" maxlength="50"><div class="ob">'
      +'<button type="button" class="no">Cancel</button><button type="button" class="go">Add</button></div>';
    var input=box.querySelector('input');
    list.appendChild(box);
    box.addEventListener('mousedown',function(ev){ ev.stopPropagation(); });
    var go=function(){
      var text=input.value.trim();
      if(!text){ input.focus(); input.classList.add('need'); return; }
      shutMenu(); addFloor(el,'Other',text);
    };
    box.querySelector('.go').onclick=go;
    box.querySelector('.no').onclick=function(){ shutMenu(); };
    input.addEventListener('keydown',function(ev){ if(ev.key==='Enter'){ ev.preventDefault(); go(); } });
    setTimeout(function(){ input.focus(); },0);
  }
  function roomAction(t){
    if(t.hasAttribute('data-floor-add')) return floorPick(t);
    if(t.hasAttribute('data-row-del')){
      return ask('The row and everything typed in it are removed.',{title:'Remove this row?',ok:'Remove',danger:true})
        .then(function(ok){
          if(!ok) return;
          going(t.closest('tr'));
          return json(api+'/rows?key='+encodeURIComponent(t.dataset.key)+'&tag='+encodeURIComponent(t.dataset.rowDel),
            {method:'DELETE'}).then(roomsDone).catch(roomsFail);
        });
    }
    if(t.hasAttribute('data-room-add')) return roomPick(t);
    if(t.hasAttribute('data-room-inc')) return addRoom(t,t.dataset.rtype,t.dataset.other);
    if(t.hasAttribute('data-room-dec')){
      going(t.closest('.rm'));
      return json(api+'/rooms?level='+encodeURIComponent(t.dataset.level)+'&type='+encodeURIComponent(t.dataset.rtype)
        +'&other='+encodeURIComponent(t.dataset.other||''),{method:'DELETE'}).then(roomsDone).catch(roomsFail);
    }
    if(t.hasAttribute('data-level-del')){
      return ask('Every room listed on it is removed with it.',{title:'Remove this level?',ok:'Remove level',danger:true})
        .then(function(ok){
          if(!ok) return;
          going(t.closest('tr'));
          return json(api+'/levels?level='+encodeURIComponent(t.dataset.level),{method:'DELETE'})
            .then(roomsDone).catch(roomsFail);
        });
    }
  }
  var ROOM_SEL='[data-room-add],[data-room-inc],[data-room-dec],[data-level-del],[data-floor-add],[data-row-del]';
  document.addEventListener('mousedown',function(e){
    var t=e.target.closest&&e.target.closest(ROOM_SEL);
    if(!t) return;
    e.preventDefault(); e.stopPropagation(); roomAction(t);
  },true);
  document.addEventListener('keydown',function(e){
    var t=e.target.closest&&e.target.closest(ROOM_SEL);
    if(t&&(e.key==='Enter'||e.key===' ')){ e.preventDefault(); roomAction(t); }
  });

  /* A grid cell is edited where it prints.  Each data point the cell is made
     of gets its own input -- an address is six -- and the list a field must
     come from is a list.  The cell shows the saved value straight away; the
     page is laid out again when it is next reloaded. */
  var gridData=null;
  var gridByKind={};
  function grid(kind){
    // the grid a cell belongs to: sales, rental or GRM (each has its own rows)
    kind=kind||'sales';
    if(kind==='sales' && gridData) return Promise.resolve(gridData);
    if(gridByKind[kind]) return Promise.resolve(gridByKind[kind]);
    return json(api+'/comparables?kind='+kind).then(function(d){
      gridByKind[kind]=d; if(kind==='sales') gridData=d; return d; });
  }
  var gedit=null, cellSeq=0;
  /* one editor at a time: opening another closes it, and an editor whose
     grid was still loading when a later cell was clicked never opens
     (owner 2026-10-08: two cell editors stood open side by side) */
  function shutEditor(){
    cellSeq++;
    [].forEach.call(document.querySelectorAll('.gedit'),function(b){ b.remove(); });
    gedit=null;
  }
  function openCell(td){
    shutEditor(); shutMenu(); shut();
    var seq=cellSeq;
    var col=Number(td.dataset.gc), fid=td.dataset.gf||'', adj=td.dataset.ga||'';
    var tbl=td.closest('table[data-gk]'), gkind=(tbl&&tbl.dataset.gk)||'sales', gscope=td.dataset.gs||'';
    grid(gkind).then(function(g){
      if(seq!==cellSeq) return;
      var row=null, item=lineOf(td,{}).item_name||'';
      for(var i=0;i<g.rows.length&&!row;i++){
        var r=g.rows[i];
        if((adj ? r.adjust_type===adj : (col===0 ? r.subject_fid===fid : r.comp_fid===fid))
           && (r.item_name||'')===item) row=r;
      }
      if(!row) return;
      var box=document.createElement('div'); box.className='gedit';
      var who=col===0?'Subject Property':'Comparable #'+col;
      box.innerHTML='<div class="gh"></div>';
      box.querySelector('.gh').textContent=row.label+' \u2014 '+who+(adj?' (adjustment)':'');
      var inputs=[];
      if(adj){
        var cellA=(row.cells[col-1]||{});
        inputs.push({dp:'',el:field('Adjustment',[],cellA.adjust_raw||'')});
      }else{
        var pts=(col===0?row.subject_points:row.comp_points)||[];
        var parts=(col===0?row.subject_parts:(row.cells[col-1]||{}).parts)||{};
        var bp=(col===0?row.subject_blocks:(row.cells[col-1]||{}).blocks)||{};   // its own unit's (T-1202)
        if(gscope && Object.prototype.hasOwnProperty.call(bp,gscope)) parts=bp[gscope];
        var lines=col===0?row.subject_lines:(row.cells[col-1]||{}).lines;
        if(!pts.length) pts=[{data_point:'',options:row.options||[]}];
        // a stacked cell (a line for each vehicle storage, view, street):
        // each line has its inputs, written into that line's own block, and
        // one more line can be added -- not every line written into the first
        var groups=lines?lines.concat([{line:'',parts:{},add:true}]):[{parts:parts}];
        groups.forEach(function(g,n){
          var head=null;
          if(lines){ head=document.createElement('div'); head.className='gl';
            head.textContent=g.add?'Add a line':'Line '+(n+1); }
          pts.filter(function(pt){ return !g.points||g.points.indexOf(pt.data_point)>=0; }).forEach(function(pt,i){
            var opts=pt.options||[];
            if((pt.format||'').toLowerCase()==='boolean') opts=[{value:'true',label:'Yes'},{value:'false',label:'No'}];
            var was=g.parts[pt.data_point]||'';
            inputs.push({dp:pt.data_point,el:field(pts.length>1?pt.data_point:'',opts,was),
                         group:lines?g:null,was:was,head:i===0?head:null});
          });
        });
      }
      inputs.forEach(function(x){ if(x.head) box.appendChild(x.head); box.appendChild(x.el); });
      var street=inputs.filter(function(x){return x.dp==='AddressLineText';})[0];
      if(street) addressLookup(street.el.querySelector('input'),inputs,box);
      var err=document.createElement('div'); err.className='err'; box.appendChild(err);
      var bar=document.createElement('div'); bar.className='gb';
      bar.innerHTML='<button type="button" class="no">Cancel</button><button type="button" class="go">Save</button>';
      box.appendChild(bar);
      bar.querySelector('.no').onclick=shutEditor;
      bar.querySelector('.go').onclick=function(){
        var chain=Promise.resolve(null), last=null;
        inputs.forEach(function(x){
          chain=chain.then(function(){
            var input=x.el.querySelector('input[type=hidden]')||x.el.querySelector('input,select');
            var typedOther=(input.dataset&&input.dataset.typed)||'';
            if(typedOther){
              // words that match no choice: the field's Other, described
              var desc=inputs.filter(function(y){ return /OtherDescription$/.test(y.dp)&&y.group===x.group; })[0];
              var di=desc&&desc.el.querySelector('input');
              if(di&&!di.value) di.value=typedOther;
            }
            var body=lineOf(td,adj?{kind:gkind,adjust_type:adj,value:input.value}
                                  :{kind:gkind,data_point:x.dp,value:input.value});
            if(adj&&td.dataset&&td.dataset.gai) body.instance=Number(td.dataset.gai);
            if(gscope) body.scope=gscope;
            if(x.group){
              // a line's value is sent when it changed; a new line is made by
              // its first value and the rest are written into it
              if(input.value===x.was) return null;
              if(x.group.line) body.line=x.group.line; else body.new=true;
            }
            return putJSON(api+'/comparables/'+col+'/fields/'+(adj?'adjustment':fid),body,'PATCH')
              .then(function(r){ if(x.group&&r&&r.line) x.group.line=r.line; if(r) last=r; return r; });
          });
        });
        chain.then(function(){
          var res=last;
          if(!res){ shutEditor(); return; }        // nothing changed
          gridData=null; gridByKind={};
          var span=td.tagName==='SPAN'?td:td.querySelector('span');
          var shown=(res&&res.value)||'';
          if(span && !td.querySelector('.ca')){
            // a stacked cell keeps a line for each, as the report prints it
            span.textContent='';
            (shown||(adj?'':'\u2014')).split(String.fromCharCode(10)).forEach(function(t,i){
              if(i) span.appendChild(document.createElement('br'));
              span.appendChild(document.createTextNode(t));
            });
          }
          else if(td.querySelector('.ca')) td.querySelector('.ca').textContent=shown||'\u2014';
          td.classList.toggle('grey',adj&&!shown);
          shutEditor();
          tell({uad:'saved'});
        }).catch(function(e2){ err.textContent=e2.message; });
      };
      box.addEventListener('keydown',function(ev){
        if(ev.key==='Escape'){ ev.preventDefault(); shutEditor(); }
        if(ev.key==='Enter' && (ev.target.tagName==='INPUT'||ev.target.classList.contains('gpick'))){
          ev.preventDefault(); bar.querySelector('.go').click();
        }
      });
      place(box,td);
      gedit=box;
      var first=box.querySelector('input[type=text],.gpick'); if(first) first.focus();
      if(first&&first.select) first.select();
    }).catch(function(e3){ say('The grid could not be read: '+e3.message); });
  }
  /* One typed value -- an adjustment, a price, an area, a count, a date --
     is typed where it prints: the click puts the caret in the cell, Enter
     or Tab saves and moves on, Escape puts it back.  The unit is the
     field's own (dollars, square feet), so nothing is asked about it.  The
     value shows at once; the save runs behind it (owner 2026-10-08). */
  function cellSpan(td){
    if(td.tagName==='SPAN') return td;
    var sp=td.querySelector('.ca')||td.querySelector(':scope > span');
    if(!sp){ sp=document.createElement('span'); td.appendChild(sp); }
    return sp;
  }
  function nextCell(td,dir){
    var all=[].slice.call(document.querySelectorAll('td[data-gin],span[data-gin]'));
    var i=all.indexOf(td);
    if(dir==='down'){
      var tr=td.closest('tr'), col=td.dataset.gc, adj=!!td.dataset.ga;
      for(var r=tr&&tr.nextElementSibling;r;r=r.nextElementSibling){
        var hit=[].filter.call(r.querySelectorAll('td[data-gin]'),function(c){ return c.dataset.gc===col&&!!c.dataset.ga===adj; })[0];
        if(hit) return hit;
      }
      return null;
    }
    return all[i+(dir==='back'?-1:1)]||null;
  }
  function typeInCell(td){
    shutEditor(); shutMenu(); shut();
    var sp=cellSpan(td), before=sp.textContent;
    var shownEmpty=/^[\u2014-]?$/.test(before.trim());
    td.classList.add('ginl');
    sp.contentEditable='true'; sp.spellcheck=false;
    if(shownEmpty) sp.textContent='';
    sp.focus();
    var rg=document.createRange(); rg.selectNodeContents(sp);
    var sel=window.getSelection(); sel.removeAllRanges(); sel.addRange(rg);
    var done=false;
    function finish(save,move){
      if(done) return; done=true;
      sp.removeAttribute('contenteditable'); td.classList.remove('ginl');
      sp.removeEventListener('keydown',keys); sp.removeEventListener('blur',blur);
      var typed=sp.textContent.trim();
      var was=shownEmpty?'':before.trim();
      if(!save||typed===was){ sp.textContent=before; }
      else saveCell(td,sp,typed,before);
      if(move){ var nx=nextCell(td,move); if(nx) setTimeout(function(){ typeInCell(nx); },0); }
    }
    function keys(ev){
      if(ev.key==='Enter'){ ev.preventDefault(); finish(true,'down'); }
      else if(ev.key==='Tab'){ ev.preventDefault(); finish(true,ev.shiftKey?'back':'next'); }
      else if(ev.key==='Escape'){ ev.preventDefault(); finish(false); }
    }
    function blur(){ finish(true); }
    sp.addEventListener('keydown',keys); sp.addEventListener('blur',blur);
  }
  function saveCell(td,sp,typed,before){
    var col=Number(td.dataset.gc), fid=td.dataset.gf||'', adj=td.dataset.ga||'';
    var tbl=td.closest('table[data-gk]'), gkind=(tbl&&tbl.dataset.gk)||'sales';
    var body=lineOf(td,adj?{kind:gkind,adjust_type:adj,value:typed}:{kind:gkind,data_point:td.dataset.gin,value:typed});
    if(adj&&td.dataset.gai) body.instance=Number(td.dataset.gai);   // its own unit's adjustment
    if(td.dataset.gs) body.scope=td.dataset.gs;
    sp.textContent=typed; td.classList.add('gsaving'); td.classList.remove('gfail','grey');
    putJSON(api+'/comparables/'+col+'/fields/'+(adj?'adjustment':fid),body,'PATCH').then(function(res){
      td.classList.remove('gsaving');
      var shown=(res&&res.value)||'';
      sp.textContent=shown||(adj?'':'\u2014');
      td.classList.toggle('grey',!!adj&&!shown);
      gridData=null; gridByKind={};
      tell({uad:'saved'});
    }).catch(function(e){
      td.classList.remove('gsaving'); td.classList.add('gfail');
      sp.textContent=before;
      say(e.message||'The value could not be saved.');
    });
  }
  /* Typing a street offers real addresses; picking one fills the city,
     state and ZIP beside it.  They are suggestions: every part stays
     editable, and nothing is saved until Save. */
  function addressLookup(input,inputs,box){
    if(!input) return;
    var list=document.createElement('div'); list.className='gsug'; list.hidden=true;
    input.parentNode.appendChild(list);
    var note=document.createElement('div'); note.className='gnote'; note.hidden=true;
    box.insertBefore(note,box.querySelector('.err'));
    var timer=null, asked='', idx=-1, items=[];
    function byDp(dp){ var x=inputs.filter(function(i){return i.dp===dp;})[0]; return x&&x.el.querySelector('input'); }
    function show(){
      list.innerHTML='';
      items.forEach(function(s,i){
        var r=document.createElement('div'); r.textContent=s.label; if(i===idx) r.className='on';
        r.addEventListener('mousedown',function(ev){ ev.preventDefault(); ev.stopPropagation(); setTimeout(function(){ pick(s); },0); });
        list.appendChild(r);
      });
      list.hidden=!items.length;
    }
    function pick(s){
      var set=function(dp,v){ var el=byDp(dp); if(el&&v){ el.value=v; el.classList.add('suggested'); } };
      set('AddressLineText',s.street); set('CityName',s.city); set('StateCode',s.state); set('PostalCode',s.postal_code);
      items=[]; show();
      note.hidden=false;
      note.textContent=s.house_number_matched
        ?'Filled from the address lookup \u2014 check it before saving.'
        :'The lookup found the street, not this house number \u2014 check the address before saving.';
    }
    input.setAttribute('autocomplete','off');
    input.addEventListener('input',function(){
      input.classList.remove('suggested');
      clearTimeout(timer);
      var q=input.value.trim();
      var city=byDp('CityName'), st=byDp('StateCode');
      if(city&&city.value) q+=' '+city.value; if(st&&st.value) q+=' '+st.value;
      if(input.value.trim().length<4){ items=[]; show(); return; }
      timer=setTimeout(function(){
        asked=q;
        fetch('/api/geocode/suggest?q='+encodeURIComponent(q)).then(function(r){return r.json();})
          .then(function(d){ if(asked!==q) return; items=d.suggestions||[]; idx=-1; show(); })
          .catch(function(){});
      },450);
    });
    input.addEventListener('keydown',function(ev){
      if(list.hidden) return;
      if(ev.key==='ArrowDown'||ev.key==='ArrowUp'){
        ev.preventDefault(); idx=Math.max(0,Math.min(items.length-1,idx+(ev.key==='ArrowDown'?1:-1))); show();
      } else if(ev.key==='Enter'&&idx>=0){ ev.preventDefault(); ev.stopPropagation(); pick(items[idx]); }
      else if(ev.key==='Escape'){ ev.stopPropagation(); items=[]; show(); }
    });
    input.addEventListener('blur',function(){ setTimeout(function(){ items=[]; show(); },150); });
  }
  function field(label,options,value){
    var wrap=document.createElement('div');
    if(label){ var l=document.createElement('label'); l.title=label;
      // AddressUnitDesignatorType -> Address Unit Designator
      l.textContent=label.replace(/(Text|Identifier|Type)$/,'').replace(/([a-z])([A-Z])/g,'$1 $2');
      wrap.appendChild(l); }
    var el;
    if(options&&options.length){
      // The field's official values as a short list inside the editor, sized
      // to the report -- not the browser's own drop-down, which is not.
      el=document.createElement('input'); el.type='hidden'; el.value=value||'';
      var list=document.createElement('div'); list.className='gpick'; list.tabIndex=0;
      list.setAttribute('role','listbox');
      var rows=[{value:'',label:'\\u2014 not answered \\u2014',clear:true}].concat(options);
      var mark=function(){
        [].forEach.call(list.children,function(r){ r.classList.toggle('on',r.dataset.value===el.value); });
      };
      rows.forEach(function(o){
        var r=document.createElement('div'); r.setAttribute('role','option');
        r.dataset.value=o.value; r.textContent=o.label; if(o.clear) r.className='clear';
        r.addEventListener('mousedown',function(ev){ ev.preventDefault(); ev.stopPropagation(); el.value=o.value; mark(); });
        r.addEventListener('dblclick',function(){
          var go=list.closest('.gedit').querySelector('.go'); if(go) go.click();
        });
        list.appendChild(r);
      });
      list.addEventListener('keydown',function(ev){
        if(ev.key!=='ArrowDown'&&ev.key!=='ArrowUp') return;
        ev.preventDefault();
        var i=rows.findIndex(function(o){return o.value===el.value;});
        i=Math.max(0,Math.min(rows.length-1,i+(ev.key==='ArrowDown'?1:-1)));
        el.value=rows[i].value; mark();
        list.children[i].scrollIntoView({block:'nearest'});
      });
      mark();
      // typed, not only picked: the list narrows to what is typed and the
      // first match is the answer; text that matches nothing goes to "Other"
      // with the words as its description, where the field has one
      var q=document.createElement('input'); q.type='text'; q.className='gq';
      q.placeholder='Type to find\u2026'; q.autocomplete='off';
      var other=options.filter(function(o){ return /^other$/i.test(o.value)||/^other$/i.test(o.label); })[0];
      q.addEventListener('input',function(){
        var t=q.value.trim().toLowerCase(), first=null;
        [].forEach.call(list.children,function(r){
          if(r.classList.contains('clear')){ r.hidden=!!t; return; }
          var hit=!t||r.textContent.toLowerCase().indexOf(t)>=0||String(r.dataset.value).toLowerCase().indexOf(t)>=0;
          r.hidden=!hit; if(hit&&!first) first=r;
        });
        if(!t){ mark(); return; }
        el.value=first?first.dataset.value:(other?other.value:el.value);
        el.dataset.typed=first?'':q.value.trim();
        mark();
      });
      q.addEventListener('keydown',function(ev){
        if(ev.key==='ArrowDown'){ ev.preventDefault(); list.focus(); }
      });
      wrap.appendChild(q);
      wrap.appendChild(list);
      setTimeout(function(){ var on=list.querySelector('.on'); if(on) on.scrollIntoView({block:'nearest'}); },0);
    }else{
      el=document.createElement('input'); el.type='text'; el.value=value;
    }
    wrap.appendChild(el);
    return wrap;
  }

  document.addEventListener('mousedown',function(e){
    if(gedit && !(e.target.closest && e.target.closest('.gedit'))) shutEditor();
    if(menu && !(e.target.closest && e.target.closest('.picklist'))) shutMenu();
  });

  document.addEventListener('click',function(e){
    var t=e.target;
    if(!t.closest) return;
    var rm=t.closest('.exremove');
    if(rm){
      e.preventDefault();
      if(rm.dataset.slot){ going(rm.closest('figure')); dropSlot(rm.dataset.slot).then(reloadHere); return; }
      ask('The picture is taken out of the report and the delivery package.',{title:'Remove this exhibit?',ok:'Remove',danger:true}).then(function(ok){
        if(!ok) return;
        going(rm.closest('figure'));
        if(rm.dataset.image){
          json(api+'/images?key='+encodeURIComponent(rm.dataset.image),{method:'DELETE'})
            .then(function(){ tell({uad:'media'}); reloadHere(); })
            .catch(function(err){ say(err.message); });
          return;
        }
        json(api+'/media/'+rm.dataset.media,{method:'DELETE'})
          .then(function(){ tell({uad:'media'}); reloadHere(); });
      });
      return;
    }
    var me=t.closest('.mapedit');
    if(me){ e.preventDefault(); e.stopPropagation(); editMap(me); return; }
    var ml=t.closest('.maploader');
    if(ml){ e.preventDefault(); e.stopPropagation(); loadMap(ml); return; }
    var add=t.closest('.exadd');
    if(add){ e.preventDefault(); addSlot(add.dataset.section,add); return; }
    var more=t.closest('.compadd');
    if(more){
      e.preventDefault();
      // answered at once: the comparable is added in the background and the
      // grid with its new column swaps in when it is laid out
      var was=more.textContent;
      more.textContent='\u2713 '+was.replace(/^\\+\\s*Add\\s*/,'')+' added';
      more.classList.add('uad-done');
      json(api+'/comparables',{method:'POST',headers:{'Content-Type':'application/json'},
                              body:JSON.stringify({kind:more.dataset.kind||'sales'})})
        .then(function(){ tell({uad:'media'}); reloadHere(); })
        .catch(function(err){ more.textContent=was; more.classList.remove('uad-done'); say(err.message); });
      return;
    }
    /* Additional Properties Analyzed Not Used: A-1 22.17, a list the
       appraiser lengthens and shortens like any other. */
    var nuadd=t.closest('.nuadd');
    if(nuadd){
      e.preventDefault();
      // the new row is on the page at once; it is saved in the background and
      // takes its own key when the laid-out report swaps in (until then it is
      // shown, not typed into, so nothing lands in another row)
      var ghost=null, blk=nuadd.closest('.blk');
      var holder=blk;
      while(holder && !(holder.querySelector&&holder.querySelector('table.tbl tbody tr'))) holder=holder.previousElementSibling;
      var last=holder&&[].slice.call(holder.querySelectorAll('table.tbl tbody tr')).pop();
      if(last){
        ghost=last.cloneNode(true);
        [].forEach.call(ghost.querySelectorAll('td'),function(td,i){
          var span=td.querySelector('span')||td;
          if(i===0){ var n=parseInt((last.cells[0].textContent||'0').trim(),10); span.textContent=isNaN(n)?'':String(n+1); return; }
          [].forEach.call(td.querySelectorAll('[contenteditable]'),function(c){ c.removeAttribute('contenteditable'); });
          [].forEach.call(td.querySelectorAll('.v'),function(v){ v.textContent=''; v.removeAttribute('data-tk'); });
          [].forEach.call(td.querySelectorAll('.lvdel'),function(x){ x.remove(); });
        });
        ghost.classList.add('uad-pending','uad-ghost');
        last.parentNode.appendChild(ghost);
      }
      json(api+'/comparables',{method:'POST',headers:{'Content-Type':'application/json'},
                              body:JSON.stringify({kind:'not_used'})})
        .then(function(){ reloadHere(); })
        .catch(function(err){ if(ghost) ghost.remove(); say(err.message); });
      return;
    }
    var liadd=t.closest('.liaddbtn');
    if(liadd){ e.preventDefault(); addRow(liadd); return; }
    var lidrop=t.closest('.lidrop');
    if(lidrop){
      e.preventDefault();
      var cell=lidrop.closest('td').querySelector('[data-li]');
      if(!cell) return;
      ask('The row is removed for the subject and every comparable.',{title:'Remove the row \u201c'+(cell.dataset.liwas||'')+'\u201d?',ok:'Remove row',danger:true}).then(function(ok){
        if(!ok) return;
        going(lidrop.closest('tr'));
        json(api+'/comparables/lineitems',
             {method:'PUT',headers:{'Content-Type':'application/json'},
              body:JSON.stringify({kind:cell.dataset.li,container:cell.dataset.lic,
                                   adjust_type:cell.dataset.lit,
                                   was:cell.dataset.liwas,name:''})})
          .then(function(){ reloadHere(); })
          .catch(function(err){ say(err.message); });
      });
      return;
    }
    var nudrop=t.closest('.nudrop');
    if(nudrop){
      e.preventDefault();
      var n=Number(nudrop.dataset.nu);
      ask('It is taken off the list of properties analyzed but not used.',{title:'Remove property #'+n+'?',ok:'Remove',danger:true}).then(function(ok){
        if(!ok) return;
        going(nudrop.closest('tr')||nudrop.closest('.blk'));
        json(api+'/comparables/'+n+'?kind=not_used',{method:'DELETE'})
          .then(function(){ reloadHere(); })
          .catch(function(err){ say(err.message); });
      });
      return;
    }
    // a rental comparable compared with a subject unit, or not: ticked at
    // once, saved in the background, the unit's grid follows
    var rp=t.closest('.rpairs .rpx');
    if(rp){
      e.preventDefault();
      var on=!rp.classList.contains('on'), ab=rp.dataset.rpair.split(',');
      rp.classList.toggle('on',on); rp.setAttribute('aria-checked',on?'true':'false'); rp.innerHTML=on?"__TICK__":'';
      putJSON(api+'/rentals/pairs',{comparable:+ab[0],unit:+ab[1],on:on},'PUT')
        .then(function(){ reloadHere(); })
        .catch(function(err){ rp.classList.toggle('on',!on); rp.innerHTML=on?'':"__TICK__"; say(err.message); });
      return;
    }
    // a per-report layout choice: saved with the case, the report laid out again
    var sw=t.closest('.layoutsw .lso[data-pref]');
    if(sw){
      if(sw.classList.contains('on')) return;
      var body={}; body[sw.dataset.pref]=sw.dataset.val;
      [].forEach.call(sw.parentNode.querySelectorAll('.lso'),function(o){
        o.classList.toggle('on',o===sw); o.setAttribute('aria-pressed',o===sw?'true':'false'); });
      putJSON(api+'/prefs',body,'PUT').then(function(){ reloadHere(); });
      return;
    }
    var th=t.closest('th[data-compmenu]');
    if(th){ e.preventDefault(); openCompMenu(th); return; }
    // a box waiting for a picture takes it straight from the file dialog
    var zone=t.closest('.exdrop');
    if(zone){ lastZone=zone; browse(zone); return; }
    var td=t.closest('td[data-gc],span[data-gc]');
    if(td && td.classList.contains('ginl')) return;
    if(td && !t.closest('.gedit')){ if(td.dataset.gin) typeInCell(td); else openCell(td); return; }
    // Public / Private in a utilities row: the click sets the ownership
    var tc=t.closest('td.tickcell');
    if(tc){
      // a click on the ticked one clears it: neither Public nor Private
      var row=tc.parentNode, on=!!tc.querySelector('svg.tick');
      send(tc,{value:on?'':tc.dataset.tval}).then(function(ok){
        if(!ok) return;
        var svg="<span>__TICK__</span>";
        [].forEach.call(row.querySelectorAll('td.tickcell'),function(c){ c.innerHTML= (c===tc && !on) ? svg : '<span></span>'; });
      });
      return;
    }
    var bx=t.closest('.bx[data-pick]');
    if(!bx) return;
    var want=bx.dataset.pick, run=bx.parentNode;
    var boxes=run.querySelectorAll('.bx[data-pick]');
    var already=bx.textContent.trim()==='\\uF052';
    send(bx,{value:already?'':want}).then(function(ok){
      if(!ok) return;
      boxes.forEach(function(b){b.innerHTML='\\uF0A3';});
      if(!already) bx.innerHTML='\\uF052';
      // answered, the pair no longer shows as waiting; cleared, it does again
      var host=run.closest('.bxs'); if(host) host.classList.toggle('untouched',already);
    });
  });

  ['dragenter','dragover'].forEach(function(kind){
    document.addEventListener(kind,function(e){
      var zone=e.target.closest && e.target.closest('.exadd,.exdrop');
      if(!zone) return;
      e.preventDefault(); lastZone=zone; zone.classList.add('over');
    });
  });
  document.addEventListener('dragleave',function(e){
    var zone=e.target.closest && e.target.closest('.exadd,.exdrop');
    if(zone) zone.classList.remove('over');
  });
  document.addEventListener('drop',function(e){
    var zone=e.target.closest && e.target.closest('.exadd,.exdrop');
    if(!zone) return;
    e.preventDefault(); zone.classList.remove('over');
    upload(zone,e.dataTransfer && e.dataTransfer.files);
  });
  document.addEventListener('mouseover',function(e){
    var zone=e.target.closest && e.target.closest('.exadd,.exdrop');
    if(zone) lastZone=zone;
  });
  // Paste goes to whichever drop zone the pointer was last over, so a
  // screenshot can go straight from the clipboard into the right section.
  document.addEventListener('paste',function(e){
    if(!lastZone||!e.clipboardData) return;
    var files=[].slice.call(e.clipboardData.files||[]);
    if(!files.length){
      files=[].slice.call(e.clipboardData.items||[])
        .filter(function(i){return i.kind==='file';})
        .map(function(i){return i.getAsFile();})
        .filter(Boolean);
    }
    if(!files.length) return;
    e.preventDefault();
    upload(lastZone,files);
  });

  /* ------------------------------------------------ guidance, problems, comments
     (from the owner's look at WinTOTAL's UAD 3.6 editor, 2026-10-09; see
     knowledge/competitors/WINTOTAL_UAD36.md)
     * Focusing a field asks what A-1 and H-1 say about it (/guide) and hands
       it to the editor's side panel, live: each H-1 rule passing or failing.
     * A comment shows how much of its length it has used.
     * The H-1 problems of the report are outlined on their own fields --
       fatal red, warning amber -- when the editor asks for it.
     * The comment library inserts a saved text where the caret is. */
  var guideCache={}, lastEditable=null, lastRange=null, counter=null;
  function fidOf(el){
    var hit=el.closest&&el.closest('[data-fid],td[data-gf]');
    if(!hit) return '';
    return hit.dataset.fid||hit.dataset.gf||'';
  }
  function guide(fid){
    if(guideCache[fid]) return Promise.resolve(guideCache[fid]);
    return fetch(api+'/guide/'+encodeURIComponent(fid)).then(function(r){ return r.ok?r.json():null; })
      .then(function(g){ if(g) guideCache[fid]=g; return g; }).catch(function(){ return null; });
  }
  function showCount(el,max){
    if(!max){ hideCount(); return; }
    if(!counter){ counter=document.createElement('div'); counter.className='lencount'; document.body.appendChild(counter); }
    var n=(el.innerText||'').trimEnd().length;
    counter.textContent=n.toLocaleString()+' / '+max.toLocaleString();
    counter.className='lencount'+(n>max?' over':n>max*0.9?' near':'');
    var r=el.getBoundingClientRect();
    counter.style.left=(window.scrollX+r.right-counter.offsetWidth)+'px';
    counter.style.top=(window.scrollY+r.bottom+2)+'px';
    counter.hidden=false;
  }
  function hideCount(){ if(counter) counter.hidden=true; }
  document.addEventListener('focusin',function(e){
    var el=e.target; if(!el.closest) return;
    var fid=fidOf(el); if(!fid) return;
    if(el.isContentEditable) lastEditable=el;
    guide(fid).then(function(g){
      if(!g) return;
      tell({uad:'guide',guide:g});
      if(document.activeElement===el && el.classList.contains('multiline')) showCount(el,g.max);
    });
  });
  document.addEventListener('focusout',function(e){
    if(e.target&&e.target.classList&&e.target.classList.contains('multiline')) setTimeout(hideCount,120);
    var sel=window.getSelection();
    if(sel&&sel.rangeCount&&e.target===lastEditable) lastRange=sel.getRangeAt(0).cloneRange();
  });
  document.addEventListener('input',function(e){
    var el=e.target;
    if(el.classList&&el.classList.contains('multiline')){
      var g=guideCache[fidOf(el)]; if(g) showCount(el,g.max);
    }
  });
  function insertText(text){
    var el=lastEditable;
    if(!el||!document.body.contains(el)){ say('Click into a comment first, then insert.'); return; }
    el.focus();
    var sel=window.getSelection();
    if(lastRange&&el.contains(lastRange.startContainer)){ sel.removeAllRanges(); sel.addRange(lastRange); }
    else{ var rg=document.createRange(); rg.selectNodeContents(el); rg.collapse(false); sel.removeAllRanges(); sel.addRange(rg); }
    document.execCommand('insertText',false,text);
    commit(el);
  }
  function snippets(){
    try{ return JSON.parse(localStorage.getItem('uad-snippets')||'[]'); }catch(e){ return []; }
  }
  // Alt+1 ... Alt+9: the comment library's entries, at the caret
  document.addEventListener('keydown',function(e){
    if(!e.altKey||e.ctrlKey||e.metaKey) return;
    var n='123456789'.indexOf(e.key); if(n<0) return;
    var el=e.target; if(!el.isContentEditable) return;
    var s=snippets()[n]; if(!s) return;
    e.preventDefault(); lastEditable=el;
    var sel=window.getSelection(); if(sel.rangeCount) lastRange=sel.getRangeAt(0).cloneRange();
    insertText(s.text);
  });
  function mark(items,on){
    [].forEach.call(document.querySelectorAll('.mk-fatal,.mk-warn'),function(x){
      x.classList.remove('mk-fatal','mk-warn'); if(x.dataset.mkt){ x.removeAttribute('title'); delete x.dataset.mkt; } });
    if(!on) return;
    (items||[]).forEach(function(it){
      var fid=it[0], cls=it[1]==='Fatal'?'mk-fatal':'mk-warn';
      var sel='.v[data-fid="'+fid+'"],.bxs .bx[data-fid="'+fid+'"],td[data-gf="'+fid+'"]';
      [].forEach.call(document.querySelectorAll(sel),function(x){
        if(x.classList.contains('mk-fatal')) return;
        x.classList.remove('mk-warn'); x.classList.add(cls);
        if(!x.title){ x.title=it[2]||''; x.dataset.mkt='1'; }
      });
    });
  }
  window.addEventListener('message',function(e){
    var m=e.data||{};
    if(m.uad==='marks'){ guideCache={}; mark(m.items,m.on); }   // a new review: guidance is asked again
    if(m.uad==='insert') insertText(m.text||'');
    if(m.uad==='add-go') addGo(m.i);
  });
  /* ------------------------------------------------- the "Add" list
     Every place the report takes another line -- an exhibit, a comparable, a
     room, a row at the foot of a table, the next certification -- listed for
     the side panel by section (WinTOTAL's per-section "+ Add" buttons), so
     the appraiser can see what can be added and go straight to it. */
  var ADDS=[];
  function headingFor(el){
    var b=el.closest('.blk');
    for(var n=0;b&&n<40;n++){
      var p=b.previousElementSibling;
      if(!p){ var pg=b.closest('.page'); pg=pg&&pg.previousElementSibling;
        while(pg&&!pg.querySelector('.blk')) pg=pg.previousElementSibling;
        p=pg?[].slice.call(pg.querySelectorAll('.blk')).pop():null; }
      b=p;
      var hd=b&&b.querySelector(':scope > .h1 > span:first-child, :scope > .h2');
      if(hd){
        var t=(hd.textContent||'').replace(/[(]continued[)]/i,'').trim();
        if(t) return t;
      }
    }
    return '';
  }
  function collectAdds(){
    ADDS=[]; var out=[];
    [].forEach.call(document.querySelectorAll(".exadd,.compadd,.nuadd,.rmadd,.ldadd,.ptyadd,tr.newrow,[data-route^='certifications/']"),function(el){
      if(el.matches("[data-route^='certifications/']")&&(el.textContent||'').trim()) return;   // only the open line
      var host=el.closest('[data-secn]'), secn=host?Number(host.dataset.secn):0;
      var h=headingFor(el), label;
      if(el.matches('tr.newrow')) label='Row: '+(h||'table');
      else if(el.matches("[data-route^='certifications/']"))
        label=el.dataset.route.indexOf('Supervisor')>0?'Supervisory appraiser certification':'Additional appraiser certification';
      else{
        label=(el.textContent||'').replace(/^[+] */,'').trim();
        if(el.matches('.exadd,.rmadd')&&h) label+=' \u2014 '+h;
      }
      ADDS.push(el); out.push({i:ADDS.length-1,secn:secn,label:label});
    });
    tell({uad:'adds',items:out});
  }
  function addGo(i){
    var el=ADDS[i]; if(!el||!el.isConnected) return;
    el.scrollIntoView({block:'center'});
    el.classList.add('addflash'); setTimeout(function(){ el.classList.remove('addflash'); },1400);
    var target=el.matches('tr.newrow')?el.querySelector('[contenteditable],.v'):el;
    if(!target) return;
    // after the scroll has fired (a scroll shuts any open list); a pick list
    // and the room controls open on mousedown, everything else on click
    setTimeout(function(){
      if(target.isContentEditable){ target.focus(); return; }
      if(target.matches('.v.pick,'+ROOM_SEL))
        target.dispatchEvent(new MouseEvent('mousedown',{bubbles:true,cancelable:true,view:window}));
      else target.click();
    },120);
  }
  setTimeout(collectAdds,200);
  /* ------------------------------------------------- a party a subsection waits on
     B-1 shows the Supervisory Appraiser (and Significant Real Property
     Appraisal Assistance) subsection only when there is one, so it is added
     here, and its fields follow; Remove takes the party away (T-1074). */
  function partyAdd(b){
    if(b.classList.contains('saving')) return;
    b.classList.add('saving');
    json(api+'/parties',{method:'POST',headers:{'Content-Type':'application/json'},
                         body:JSON.stringify({role:b.dataset.role})})
      .then(function(){ reloadHere(); })
      .catch(function(e){ b.classList.remove('saving'); b.title=e.message; });
  }
  function partyRemove(x){
    var h=x.closest('.h2,.h1'), name=h?h.textContent.replace(x.textContent,'').trim():'party';
    ask('Remove the '+name.toLowerCase()+' and everything entered for them?',
        {title:'Remove '+name,ok:'Remove',danger:true}).then(function(ok){
      if(!ok) return;
      json(api+'/parties/'+encodeURIComponent(x.dataset.role),{method:'DELETE'})
        .then(function(){ reloadHere(); })
        .catch(function(e){ x.title=e.message; });
    });
  }
  document.addEventListener('click',function(e){
    var b=e.target.closest&&e.target.closest('.ptyadd'); if(b){ partyAdd(b); return; }
    var x=e.target.closest&&e.target.closest('.ptyx'); if(x) partyRemove(x);
  });
  document.addEventListener('keydown',function(e){
    if(e.key!=='Enter'&&e.key!==' ') return;
    var b=e.target.closest&&e.target.closest('.ptyadd,.ptyx'); if(!b) return;
    e.preventDefault(); if(b.matches('.ptyadd')) partyAdd(b); else partyRemove(b);
  });
  /* ------------------------------------------------- adjustment colours
     A negative adjustment or net total reads red, a positive one green, in
     the editor only (WinTOTAL colours its net adjustment; the printed form
     stays black as C-1 draws it).  Kept current as cells are typed and saved. */
  function tint(){
    document.querySelectorAll("td.v.adj, td[data-gin='SalePriceNetTotalAdjustmentAmount']").forEach(function(td){
      var t=(td.textContent||'').trim();
      var num=Number(t.replace(/[^0-9.]/g,''));
      var neg=t.indexOf('(')>=0||t.charAt(0)==='-';
      td.classList.toggle('neg',!!num&&neg);
      td.classList.toggle('pos',!!num&&!neg);
    });
  }
  var tintSoon=null;
  new MutationObserver(function(){ clearTimeout(tintSoon); tintSoon=setTimeout(tint,150); })
    .observe(document.body,{subtree:true,childList:true,characterData:true});
  tint();
  /* ------------------------------------- adjustment worksheets (DR §11)
     Every adjustable row of the sales grid that has a worksheet -- GLA, site,
     age, beds, baths, garage, the area rows, basement, outdoor living,
     cooling, design, market exposure, and each unit's line on a 2-4 unit
     report -- carries a small green (+) in its label, put there whenever the
     grid is drawn (a new comparable or unit included).  The (+), or Ctrl+J in
     the row, opens the worksheet beside the report.  An applied row shows a
     tick and its rate ("$75/sf"); an adjustment cell's title is its
     arithmetic; one typed by hand is marked manual; one the worksheet just
     recalculated (a value it rests on changed) flashes once. */
  var WS={rows:{},cells:{},recalc:null}, wsLast=null;
  function wsLoad(){
    if(!document.querySelector('table.grid[data-gk="sales"]')) return;
    fetch(api+'/worksheets/marks').then(function(r){ return r.ok?r.json():null; })
      .then(function(d){ if(d){ WS=d; wsMark(); wsFlash(); } }).catch(function(){});
  }
  function wsSet(el,prop,val){ if(el[prop]!==val) el[prop]=val; }
  function wsMark(){
    document.querySelectorAll('table.grid[data-gk="sales"] tbody tr').forEach(function(tr){
      var adj=tr.querySelector('td.v.adj[data-ga]'); var lbl=tr.querySelector('td.lbl');
      if(!adj||!lbl) return;
      var type=adj.dataset.ga, row=WS.rows&&WS.rows[type];
      var icon=lbl.querySelector('.wsi');
      if(!row){ if(icon) icon.remove(); return; }
      if(!icon){ icon=document.createElement('span'); icon.className='wsi'; icon.setAttribute('role','button'); icon.tabIndex=0; lbl.appendChild(icon); }
      if(icon.dataset.kind!==row.kind) icon.dataset.kind=row.kind;
      if(icon.dataset.type!==type) icon.dataset.type=type;
      var inst=adj.dataset.gai||'0'; if(icon.dataset.inst!==inst) icon.dataset.inst=inst;
      if(icon.classList.contains('on')!==!!row.applied) icon.classList.toggle('on',!!row.applied);
      wsSet(icon,'textContent',row.applied?'\u2713 '+row.label:'\u2295');
      wsSet(icon,'title',row.applied?(row.title+' worksheet at '+row.label+' \u2014 open it (or Ctrl+J)')
                                    :('Open the '+row.title+' worksheet (or Ctrl+J in this row)'));
      tr.querySelectorAll('td.v.adj[data-ga]').forEach(function(td){
        var c=WS.cells&&WS.cells[type+'|'+td.dataset.gc+'|'+(td.dataset.gai||'0')];
        if(td.classList.contains('wsmanual')!==!!(c&&c.manual)) td.classList.toggle('wsmanual',!!(c&&c.manual));
        var t=c?(c.manual?'Typed by hand \u2014 the worksheet leaves it as it is':c.basis):'';
        if(t) wsSet(td,'title',t); else if(td.hasAttribute('title')&&td.dataset.wst) td.removeAttribute('title');
        if(t) td.dataset.wst='1';
      });
    });
  }
  function wsFlash(){
    var r=WS.recalc; if(!r||!r.at) return;
    var k='uad-wsflash-'+id, seen='';
    try{ seen=sessionStorage.getItem(k)||''; }catch(e){}
    if(seen>=r.at) return;
    try{ sessionStorage.setItem(k,r.at); }catch(e){}
    if(!seen) return;            // first look at this report: nothing to point at
    (r.cells||[]).forEach(function(c){
      var td=document.querySelector('td.v.adj[data-ga="'+c.adjust_type+'"][data-gc="'+c.comp+'"]'+
        (c.instance?'[data-gai="'+c.instance+'"]':''));
      if(td){ td.classList.remove('wsflash'); void td.offsetWidth; td.classList.add('wsflash'); }
    });
  }
  function wsOpen(type,inst){
    var row=WS.rows&&WS.rows[type];
    tell({uad:'worksheet',kind:row?row.kind:'',type:type||'',inst:Number(inst||0)});
  }
  document.addEventListener('click',function(e){
    var i=e.target.closest&&e.target.closest('.wsi'); if(!i) return;
    e.preventDefault(); e.stopPropagation(); wsOpen(i.dataset.type,i.dataset.inst);
  },true);
  document.addEventListener('keydown',function(e){
    var i=e.target.closest&&e.target.closest('.wsi');
    if(i&&(e.key==='Enter'||e.key===' ')){ e.preventDefault(); wsOpen(i.dataset.type,i.dataset.inst); return; }
    if(e.key==='Escape'&&!e.defaultPrevented&&!(e.target.isContentEditable||/^(INPUT|SELECT|TEXTAREA)$/.test(e.target.tagName||''))){
      tell({uad:'ws-esc'}); return;          // Esc in the report closes an open worksheet
    }
    if((e.ctrlKey||e.metaKey)&&(e.key==='j'||e.key==='J')){
      e.preventDefault();
      var at=(document.activeElement&&document.activeElement.closest&&document.activeElement.closest('tr'))||wsLast;
      var adj=at&&at.querySelector&&at.querySelector('td.v.adj[data-ga]');
      wsOpen(adj?adj.dataset.ga:'',adj?adj.dataset.gai:0);
    }
  });
  document.addEventListener('focusin',function(e){ var tr=e.target.closest&&e.target.closest('table.grid tr'); if(tr) wsLast=tr; });
  document.addEventListener('mousedown',function(e){ var tr=e.target.closest&&e.target.closest('table.grid tr'); if(tr) wsLast=tr; });
  window.addEventListener('message',function(e){
    var m=e.data||{};
    if(m.uad==='ws-focus'){
      document.querySelectorAll('tr.wsrow').forEach(function(t){ t.classList.remove('wsrow'); });
      if(m.type) document.querySelectorAll('td.v.adj[data-ga="'+m.type+'"]').forEach(function(td){ td.closest('tr').classList.add('wsrow'); });
      var first=document.querySelector('tr.wsrow'); if(first&&m.scroll) first.scrollIntoView({block:'center',behavior:'smooth'});
    }
    if(m.uad==='ws-marks') wsLoad();
  });
  var wsSoon=null;
  new MutationObserver(function(){ clearTimeout(wsSoon); wsSoon=setTimeout(wsMark,180); })
    .observe(document.body,{subtree:true,childList:true});
  wsLoad();
  /* --------------------------------------- additional certifications
     x beside a certification removes it (WinTOTAL's Alt+R); the next number
     is always open to type a new one into (uad/certifications.py). */
  document.addEventListener('click',function(e){
    var x=e.target.closest&&e.target.closest('.certx'); if(!x) return;
    e.preventDefault();
    var v=x.parentNode.querySelector('.v[data-route]'); if(!v) return;
    ask('It is taken out of the report and its XML; the ones after it move up.',
        {title:'Remove certification '+v.dataset.ordinal+'?',ok:'Remove',danger:true}).then(function(ok){
      if(!ok) return;
      v.textContent=''; v.dataset.was='';
      send(v,{value:''});
    });
  });
  /* ------------------------------------------- units in the rent schedule
     One switch per subject unit (A-1 UnitIncludedInRentScheduleIndicator);
     the rent schedule's lines follow, so the page is laid out again. */
  function rentUnit(el){
    var on=!el.classList.contains('on');
    el.classList.remove('on','off','unset'); el.classList.add(on?'on':'off');
    el.setAttribute('aria-checked',on?'true':'false');
    el.querySelector('i').innerHTML=on?"__TICK__":'';
    putJSON(api+'/rentals/included',{unit:+el.dataset.rsunit,on:on},'PUT')
      .then(function(){ tell({uad:'saved'}); reloadHere(); })
      .catch(function(err){ say(err.message); });
  }
  document.addEventListener('click',function(e){
    var el=e.target.closest&&e.target.closest('.rsinc .rsu'); if(!el) return;
    e.preventDefault(); rentUnit(el);
  });
  document.addEventListener('keydown',function(e){
    var el=e.target.closest&&e.target.closest('.rsinc .rsu');
    if(el&&(e.key===' '||e.key==='Enter')){ e.preventDefault(); rentUnit(el); }
  });
  /* ------------------------------------------- legal description image
     B-1 p122: the legal description as text or as an image.  The picture is
     sent to its own route, which writes the IMAGE (3.031.1) into the report. */
  function legalImage(){
    var input=document.createElement('input');
    input.type='file'; input.accept='image/*'; input.style.display='none';
    document.body.appendChild(input);
    input.addEventListener('change',function(){
      var f=input.files&&input.files[0]; input.remove(); if(!f) return;
      var fd=new FormData(); fd.append('file',f,f.name||'legal-description.png');
      json(api+'/legal-description/photo',{method:'POST',body:fd})
        .then(function(){ tell({uad:'media'}); tell({uad:'saved'}); reloadHere(); })
        .catch(function(err){ say('The legal description image could not be added: '+err.message); });
    });
    input.click();
  }
  document.addEventListener('click',function(e){
    var b=e.target.closest&&e.target.closest('.ldadd'); if(!b) return;
    e.preventDefault(); legalImage();
  });
  document.addEventListener('keydown',function(e){
    var b=e.target.closest&&e.target.closest('.ldadd');
    if(b&&(e.key==='Enter'||e.key===' ')){ e.preventDefault(); legalImage(); }
  });
})();
</script>"""


def _stamp(piece: Piece, kind: str = "urar") -> str:
    """Name the section a piece of the page belongs to (editor only).

    The rail navigates by it and follows the reader by it; an attribute moves
    nothing on the page, and the printed report never carries it.
    """
    number = form.section_number(piece.section, kind)
    return piece.html.replace(
        "<div class='blk",
        f"<div data-secn='{number}' data-sec='{form.esc(piece.section)}' class='blk", 1)


def render(pages: list[Page], meta: Meta, *, embed_fonts: bool = True,
           screen: bool = False, edit: bool = False,
           imported: Iterable[str] = ()) -> str:
    total = len(pages)
    body = []
    for n, pg in enumerate(pages, start=1):
        band = "band first" if n == 1 and not meta.header_on_first else "band"
        pieces = "".join(_stamp(p, meta.kind) if edit else p.html for p in pg.pieces)
        body.append(f"<div class='page' data-page='{n}'><div class='hi'><div class='hz'>"
                    f"{_furniture(meta, n, total, edit)}"
                    f"<div class='{band}'>{pieces}</div></div></div></div>")
    return (f"<!doctype html><html><head><meta charset='utf-8'>"
            f"<title>{form.esc(meta.title)}</title><style>"
            f"{form.stylesheet(embed_fonts=embed_fonts, screen=screen, edit=edit)}"
            f".band > .blk:not(.cols){{display:flow-root}}"
            f".band > .blk.top{{margin-top:0}}"
            f".band > .blk.top .tabwrap,.band > .blk.top .h1,.band > .blk.top .h2{{margin-top:0}}"
            f"</style></head><body>{''.join(body)}"
            f"{_imported_js(imported) if edit else ''}"
            f"{FIT_JS if screen else ''}{EDIT_JS.replace('__BODY_BOTTOM__', str(BODY_BOTTOM)).replace('__TICK__', form.EDIT_TICK) if edit else ''}</body></html>")


def _imported_js(imported: Iterable[str]) -> str:
    """The Report Field IDs a file brought in, for the editor to mark.

    Named here rather than stamped on every control because the marking is a
    view of the page, not a property of a value: the same field shows green
    the moment it arrives and plain once the appraiser turns the marking off.
    """
    fids = sorted({str(f) for f in imported if f})
    if not fids:
        return ""
    return f"<script>window.UAD_IMPORTED={json.dumps(fids)};</script>"


OVERFLOW_JS = """
() => Array.from(document.querySelectorAll('.page')).map(pg => {
  const band = pg.querySelector('.band');
  const top = pg.getBoundingClientRect().top;
  let bottom = 0;
  for (const el of band.querySelectorAll(':scope > .blk, :scope > .blk > .col > *, :scope > .blk *')) {
    const r = el.getBoundingClientRect();
    if (r.height > 0) bottom = Math.max(bottom, r.bottom);
  }
  return (bottom - top) * 72 / 96;
})
"""


def verify(html: str) -> list[float]:
    """The real bottom of the content on every page, in points."""
    _allow_subprocesses()
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--font-render-hinting=none"])
        try:
            pg = browser.new_page(viewport={"width": 900, "height": 1400}, device_scale_factor=1)
            pg.set_content(html, wait_until="load", timeout=90_000)
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(100)
            return pg.evaluate(OVERFLOW_JS)
        finally:
            browser.close()


def build(tree, *, folder=None, media=None, sample=False, screen=False,
          embed_fonts=True, edit=False, diagnostics: dict | None = None,
          slots: list[dict] | None = None, imported: Iterable[str] = ()) -> str:
    """Lay the report out so that nothing lands below the body rule.

    The planner works from measured heights, so a first pass is normally right
    to within a couple of points -- the residual is sub-pixel rounding and the
    small optical offsets Appendix E puts on prose blocks.  The loop below
    closes that residual by re-planning with a tightened cap on whichever page
    ran long, and it is a net, not the mechanism: if it is doing more than two
    rounds of work, a height is being measured wrong and that is the bug to
    fix.

    Pass a dict as ``diagnostics`` to get the outcome back -- ``pages``,
    ``attempts``, the worst ``drift`` between plan and render, and ``overflow``,
    which is empty when every page is clean.  A caller that must not ship an
    overflowing page checks it; nothing is swallowed.
    """
    from uad.report import browser
    if not browser.AVAILABLE:
        raise browser.BrowserUnavailable(browser.MESSAGE)
    galley, meta = prepare(tree, folder=folder, media=media, sample=sample,
                           embed_fonts=embed_fonts, edit=edit, slots=slots,
                           imported=imported)
    measured = measure(galley)
    caps: dict[int, float] = {}
    html = ""
    over: dict[int, float] = {}
    pages: list[Page] = []
    drift = 0.0
    attempt = 0
    for attempt in range(1, ATTEMPTS + 1):
        html, pages = paginate(measured, meta, caps, embed_fonts=embed_fonts,
                               screen=screen, edit=edit, imported=imported)
        bottoms = verify(html)
        drift = max((b - pg.planned for pg, b in zip(pages, bottoms)), default=0.0)
        over = overflowing(bottoms)
        if not over:
            break
        caps = tighten(caps, over)
    if diagnostics is not None:
        diagnostics.update(pages=len(pages), attempts=attempt,
                           drift=round(drift, 2), overflow=over)
    return html


# The three steps of ``build`` without the browser in between, so a caller
# whose browser is elsewhere -- the appraiser's own, when the server has no
# Chromium (a serverless deployment) -- can run the measuring itself.  The
# arithmetic stays here, in one place; the browser only reports geometry.
ATTEMPTS = 6


def prepare(tree, *, folder=None, media=None, sample=False, embed_fonts=True,
            edit=False, slots=None, imported: Iterable[str] = ()) -> tuple[str, "Meta"]:
    """The galley to measure, and the page furniture's facts."""
    blocks = form.build(tree, folder=folder, media=media, sample=sample,
                        edit=edit, slots=slots, imported=imported)
    return _galley(blocks, embed_fonts=embed_fonts, edit=edit), Meta.from_case(tree)


def paginate(measured: list[dict], meta: "Meta", caps: dict[int, float] | None = None, *,
             embed_fonts=True, screen=False, edit=False,
             imported: Iterable[str] = ()) -> tuple[str, list[Page]]:
    """Plan pages from measured blocks and render them."""
    pages = plan(measured, caps or {}, header_on_first=meta.header_on_first)
    return render(pages, meta, embed_fonts=embed_fonts, screen=screen, edit=edit,
                  imported=imported), pages


def overflowing(bottoms: list[float]) -> dict[int, float]:
    """Pages (1-based) whose content runs below the body rule, and how far."""
    return {n + 1: round(b, 1) for n, b in enumerate(bottoms) if b > BODY_BOTTOM}


def tighten(caps: dict[int, float], over: dict[int, float]) -> dict[int, float]:
    """The caps for the next pass, given which pages ran long.

    Shrink from the cap already in force, never from BODY_BOTTOM: the latter
    recomputes the same number every round, and the loop sits on a page that
    is long by a hair until it runs out of attempts."""
    caps = dict(caps)
    for n, b in over.items():
        caps[n] = caps.get(n, BODY_BOTTOM) - (b - BODY_BOTTOM) - 1.0
    return caps


def to_pdf(html: str, out_path) -> Any:
    _allow_subprocesses()
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--font-render-hinting=none"])
        try:
            pg = browser.new_page()
            pg.set_content(html, wait_until="load", timeout=120_000)
            pg.evaluate("document.fonts.ready")
            pg.wait_for_timeout(200)
            pg.pdf(path=str(out_path), width="8.5in", height="14in",
                   print_background=True,
                   margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                   prefer_css_page_size=True)
        finally:
            browser.close()
    return out_path


# ------------------------------------------------- geometry from elsewhere
def _outer(el) -> str:
    from lxml import html as lhtml
    return lhtml.tostring(el, encoding="unicode", with_tail=False)


def _inner(el) -> str:
    from lxml import html as lhtml
    return (el.text or "") + "".join(lhtml.tostring(c, encoding="unicode", with_tail=True) for c in el)


def skeleton(galley_html: str) -> list[dict]:
    """What MEASURE_JS reports, minus the numbers: every block's markup and
    parts, read from the server's own galley.  The browser's measurement is
    then trusted for geometry only (``trusted``)."""
    from lxml import html as lhtml
    doc = lhtml.fromstring(galley_html)
    galley = doc.get_element_by_id("galley")
    out = []
    for blk in [c for c in galley if isinstance(c.tag, str) and "blk" in (c.get("class") or "").split()]:
        e = {"n": int(blk.get("data-n") or 0), "kind": blk.get("data-kind"),
             "group": int(blk.get("data-group") or 0), "section": blk.get("data-section") or "",
             "newpage": blk.get("data-newpage") is not None, "html": _inner(blk),
             "outer": _outer(blk)[:80], "cols": [], "rows": [], "head": ""}
        if "cols" in (blk.get("class") or "").split():
            for col in [c for c in blk if isinstance(c.tag, str) and "col" in (c.get("class") or "").split()]:
                kids = [k for k in col if isinstance(k.tag, str)]
                items, i = [], 0
                while i < len(kids):
                    html = _outer(kids[i])
                    if "yn" in (kids[i].get("class") or "").split() and i + 1 < len(kids):
                        html += _outer(kids[i + 1])
                        i += 1
                    items.append({"html": html})
                    i += 1
                e["cols"].append(items)
        table = next((c for c in blk if isinstance(c.tag, str) and c.tag == "table"), None)
        if table is not None:
            head = table.find("thead")
            cg = table.find("colgroup")
            e["head"] = (_outer(cg) if cg is not None else "") + (_outer(head) if head is not None else "")
            t_outer = _outer(table)
            e["tableOpen"] = t_outer[:t_outer.index(">") + 1]
            body = table.find("tbody")
            for tr in ([r for r in body if isinstance(r.tag, str) and r.tag == "tr"] if body is not None else []):
                e["rows"].append({"html": _outer(tr), "sub": "sub" in (tr.get("class") or "").split()})
        out.append(e)
    return out


def trusted(measured: list[dict], galley_html: str) -> list[dict]:
    """The server's own markup with the browser's numbers.

    A layout another browser will be shown must hold nothing a browser sent
    but geometry: block by block, item by item and row by row the structure
    has to agree with the server's galley, and only heights and offsets are
    taken.  Any disagreement (a different document, a stale galley, a forged
    payload) raises -- the layout is then simply not shared."""
    base = skeleton(galley_html)
    if len(base) != len(measured):
        raise ValueError("the measurement is of a different report")
    num = lambda v: float(v) if isinstance(v, (int, float)) and v == v else 0.0   # noqa: E731
    for e, m in zip(base, measured):
        if not isinstance(m, dict) or int(m.get("n", -1)) != e["n"]:
            raise ValueError("the measurement is of a different report")
        e["height"], e["lead"] = num(m.get("height")), num(m.get("lead"))
        if e["cols"]:
            mc = m.get("cols") or []
            if len(mc) != len(e["cols"]) or any(len(a) != len(b) for a, b in zip(mc, e["cols"])):
                raise ValueError("the measurement is of a different report")
            for items, mitems in zip(e["cols"], mc):
                for it, mi in zip(items, mitems):
                    it["top"], it["height"] = num(mi.get("top")), num(mi.get("height"))
        if "tableOpen" in e:
            mr = m.get("rows") or []
            if len(mr) != len(e["rows"]):
                raise ValueError("the measurement is of a different report")
            for r, mrow in zip(e["rows"], mr):
                r["height"] = num(mrow.get("height"))
            e["headHeight"] = num(m.get("headHeight"))
            e["contHeadHeight"] = num(m.get("contHeadHeight"))
    return base
