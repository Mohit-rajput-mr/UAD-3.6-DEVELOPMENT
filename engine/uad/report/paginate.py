"""Split the report into pages by measuring it, not by estimating it.

A field's height is not knowable from the data: a one-line label wraps to two
when the value is long, a commentary block runs to twenty, a photo occupies a
fixed box.  Guessing produces a page count that drifts from the truth and a
last page that overflows.

So the document is laid out once in the browser at the real page width, every
row's height is read back, and the breaks are placed where the content actually
runs out of page.  The two body columns are filled independently, as the
samples show them: each takes as many of its own rows as fit before the page
turns.  A section that carries over reopens with its "(continued)" tab.

This is what makes the page count follow the case -- more units, more
comparables, longer commentary, more pages -- with no fixed template.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from uad.report.browser import sync_playwright  # optional: BrowserUnavailable without Chromium

from . import page as geom
from . import urar

# Read every block's height, and inside a rows block each column's rows, in one
# pass.  Heights come back in points because the page is laid out in points.
MEASURE_JS = """
() => {
  const px2pt = 72 / 96;
  // A block's own margins are part of the space it takes.  Measuring only the
  // border box under-counts every bar by its 12.4pt of margin, and after a
  // dozen of them a page runs past the footer.
  const blockHeight = (blk) => {
    let h = blk.getBoundingClientRect().height;
    for (const child of blk.children) {
      const cs = getComputedStyle(child);
      h += parseFloat(cs.marginTop || 0) + parseFloat(cs.marginBottom || 0);
    }
    return h;
  };
  const out = [];
  for (const blk of document.querySelectorAll('#galley .blk')) {
    const kind = blk.classList.contains('tabblk') ? 'tab'
               : blk.classList.contains('lead') ? 'lead'
               : blk.classList.contains('grid') ? 'grid'
               : blk.classList.contains('solid') ? 'solid' : 'rows';
    const entry = {
      kind: kind,
      section: blk.dataset.section || '',
      height: blockHeight(blk) * px2pt,
      columns: [],
      rows: [],
      head: '',
      open: '',
      html: '',
    };
    if (kind === 'solid') { entry.html = blk.innerHTML; }
    if (kind === 'grid') {
      const table = blk.querySelector('table');
      if (table) {
        const cg = table.querySelector('colgroup');
        const th = table.querySelector('thead');
        entry.open = (cg ? cg.outerHTML : '');
        entry.head = (th ? th.outerHTML : '');
        entry.headHeight = th ? th.getBoundingClientRect().height * px2pt : 0;
        for (const tr of table.querySelectorAll('tbody tr')) {
          entry.rows.push({
            height: tr.getBoundingClientRect().height * px2pt,
            html: tr.outerHTML,
          });
        }
      }
    }
    for (const col of blk.querySelectorAll('.col')) {
      const rows = [];
      for (const r of col.children) {
        const cs = getComputedStyle(r);
        rows.push({
          height: (r.getBoundingClientRect().height
                   + parseFloat(cs.marginTop || 0)
                   + parseFloat(cs.marginBottom || 0)) * px2pt,
          html: r.outerHTML,
        });
      }
      entry.columns.push(rows);
    }
    out.push(entry);
  }
  return out;
}
"""


@dataclass
class Fragment:
    """One piece of content placed on one page."""
    kind: str                      # lead | tab | rows
    section: str = ""
    html: str = ""
    columns: tuple[list[str], list[str]] = ((), ())
    continued: bool = False


def _fill(rows: list[dict], start: int, available: float) -> tuple[int, float]:
    """How many rows fit, and how much height they take."""
    used, i = 0.0, start
    while i < len(rows) and used + rows[i]["height"] <= available + 0.5:
        used += rows[i]["height"]
        i += 1
    return i, used


def plan(blocks: list[dict], *, first_page_top: float | None = None
         ) -> list[list[Fragment]]:
    """Assign every measured block to a page."""
    pages: list[list[Fragment]] = []
    current: list[Fragment] = []
    top = first_page_top if first_page_top is not None else geom.BODY_TOP_SUMMARY
    y = top
    bottom = geom.BODY_BOTTOM

    def newpage() -> None:
        nonlocal current, y
        pages.append(current)
        current = []
        y = geom.BODY_TOP

    for block in blocks:
        if block["kind"] == "grid":
            # A grid is split by its own rows, and its column heads are
            # repeated at the top of each page it runs on -- a page of figures
            # with no heading above them cannot be read.
            head = block.get("head", "")
            open_tags = block.get("open", "")
            head_h = block.get("headHeight") or geom.ROW_PITCH
            grid_rows = block.get("rows", [])
            i = 0
            while i < len(grid_rows):
                # One row of slack: a wrapped cell can measure a little taller
                # once it is re-laid out on its own page, and a grid that runs
                # under the footer is worse than one that breaks a row early.
                available = bottom - y - head_h - geom.ROW_PITCH * 2
                if available < geom.ROW_PITCH * 2:
                    newpage()
                    available = bottom - y - head_h
                ni, used = _fill(grid_rows, i, available)
                if ni == i:
                    ni, used = i + 1, grid_rows[i]["height"]
                current.append(Fragment(
                    kind="grid", section=block["section"],
                    html=("<table class='grid'>" + open_tags + head + "<tbody>"
                          + "".join(r["html"] for r in grid_rows[i:ni])
                          + "</tbody></table>")))
                y += used + head_h
                i = ni
                if i < len(grid_rows):
                    newpage()
            continue

        if block["kind"] == "solid":
            # A bar, a narrative or a row of exhibits moves whole.  A bar must
            # not be the last thing on a page either: it announces what comes
            # under it.
            need = block["height"] + (geom.ROW_PITCH if block["height"] < 20 else 0)
            if y + need > bottom and current:
                newpage()
            current.append(Fragment(kind="solid", section=block["section"],
                                    html=block.get("html", "")))
            y += block["height"]
            continue

        if block["kind"] in ("lead", "tab"):
            # A tab must not be the last thing on a page; it opens a section
            # and needs at least one row under it.
            if y + block["height"] + geom.ROW_PITCH > bottom and current:
                newpage()
            current.append(Fragment(kind=block["kind"], section=block["section"],
                                    html=block.get("html", "")))
            y += block["height"]
            continue

        left = block["columns"][0] if block["columns"] else []
        right = block["columns"][1] if len(block["columns"]) > 1 else []
        i = j = 0
        first = True
        while i < len(left) or j < len(right):
            available = bottom - y
            if available < geom.ROW_PITCH:
                newpage()
                available = bottom - y
                first = False
            ni, used_l = _fill(left, i, available)
            nj, used_r = _fill(right, j, available)
            if ni == i and nj == j:
                # nothing fits -- force one row so the loop cannot stall
                if i < len(left):
                    ni, used_l = i + 1, left[i]["height"]
                elif j < len(right):
                    nj, used_r = j + 1, right[j]["height"]
            if not first:
                current.append(Fragment(kind="tab", section=block["section"],
                                        continued=True))
            current.append(Fragment(
                kind="rows", section=block["section"],
                columns=([r["html"] for r in left[i:ni]],
                         [r["html"] for r in right[j:nj]])))
            y += max(used_l, used_r)
            i, j = ni, nj
            first = False
            if i < len(left) or j < len(right):
                newpage()
    if current:
        pages.append(current)
    return pages


def measure(html: str, *, timeout_ms: int = 60_000) -> list[dict]:
    """Lay the document out once and read every row's real height."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--font-render-hinting=none"])
        try:
            context = browser.new_context(
                viewport={"width": int(geom.PAGE_W * 96 / 72) + 40, "height": 1200},
                device_scale_factor=1)
            pg = context.new_page()
            pg.set_content(html, wait_until="load", timeout=timeout_ms)
            pg.wait_for_timeout(120)          # let webfonts settle
            return pg.evaluate(MEASURE_JS)
        finally:
            browser.close()


def render_pages(pages: list[list[Fragment]], meta: urar.Meta,
                 section_names: dict[str, str], lead: str) -> str:
    """The final HTML: one absolutely-sized page div per printed page."""
    total = len(pages)
    out: list[str] = []
    for n, fragments in enumerate(pages, start=1):
        body: list[str] = []
        for frag in fragments:
            if frag.kind == "lead":
                body.append(lead)
            elif frag.kind in ("grid", "solid"):
                body.append(frag.html)
            elif frag.kind == "tab":
                name = section_names.get(frag.section, "")
                cont = "<span class='cont'>(continued)</span>" if frag.continued else ""
                body.append(f"<div class='tab'>{urar.esc(name)}{cont}</div>")
            else:
                left, right = frag.columns
                body.append(
                    "<div class='cols'>"
                    f"<div class='col left'>{''.join(left)}</div>"
                    f"<div class='col right'>{''.join(right)}</div>"
                    "</div>")
        band = "summary" if n == 1 else ""
        header = "" if n in geom.HEADER["suppressed_on_pages"] else urar._header(
            meta, n, total)
        out.append(f"<div class='page' data-page='{n}'>{header}"
                   f"<div class='band {band}'>{''.join(body)}</div>"
                   f"{urar._footer(meta)}</div>")
    return "".join(out)


def build(sections: list[urar.Section], meta: urar.Meta, lead: str, *,
          screen: bool = False, embed_fonts: bool = True) -> str:
    """Measure, paginate and emit the finished document."""
    draft = urar.document(sections, meta, screen=False,
                          embed_fonts=embed_fonts, lead=lead)
    blocks = measure(draft)
    names = {str(s.number): s.tab for s in sections}
    pages = plan(blocks)
    return f"""<!doctype html>
<html><head><meta charset="utf-8">
<title>Uniform Residential Appraisal Report</title>
<style>{urar.stylesheet(embed_fonts=embed_fonts, screen=screen)}</style>
</head><body>{render_pages(pages, meta, names, lead)}</body></html>"""


def to_pdf(html: str, out_path: str | Any, *, timeout_ms: int = 120_000) -> Any:
    """Print the finished document, through the same engine as the preview."""
    with sync_playwright() as p:
        browser = p.chromium.launch(args=["--font-render-hinting=none"])
        try:
            pg = browser.new_page()
            pg.set_content(html, wait_until="load", timeout=timeout_ms)
            pg.wait_for_timeout(200)
            # Chromium rejects a fractional point value here, so the page is
            # given in inches -- 8.5 x 14, the Legal sheet the samples measure.
            pg.pdf(path=str(out_path),
                   width=f"{geom.PAGE_W / geom.PT_PER_IN:g}in",
                   height=f"{geom.PAGE_H / geom.PT_PER_IN:g}in",
                   print_background=True,
                   margin={"top": "0", "bottom": "0", "left": "0", "right": "0"},
                   prefer_css_page_size=True)
        finally:
            browser.close()
    return out_path
