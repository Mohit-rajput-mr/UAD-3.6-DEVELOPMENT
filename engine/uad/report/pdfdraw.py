"""The PDF, drawn from the pages a browser has laid out -- no Chromium on the server.

A serverless host (the live site on Vercel) cannot run a browser, so it could
lay a report out only in the appraiser's own browser (``app/api.py``
``CLIENT_LAYOUT_HTML``) and answered the PDF -- and with it the deliverable
ZIP -- with 503 (owner's section test B5).  A browser cannot print to a file
a script can read, but it can say exactly where it put everything:

* ``DISPLAY_JS`` runs in the laid-out pages and reports, per page and in
  points, every glyph's position (so kerning, letter spacing and line breaks
  are the browser's own), every filled box and border (pseudo-elements
  included), every picture with its fit and clip, and the strokes of the
  inline SVG ticks;
* ``write`` turns that display list into a PDF with nothing but the Python
  standard library, fontTools and Pillow: the report's own TrueType faces
  embedded and subset (Type 0 / CIDFontType2 with a ToUnicode map, so the
  text is text), the case's own image files, filled rectangles and paths.

The browser contributes geometry.  What the page *says* is checked against
the server's own pages before a PDF is kept (``check_text``), and pictures
are read from the server's own files, never taken from the browser -- the one
exception is an SVG picture (a market chart), which the browser rasterises
because the server has no SVG renderer.
"""
from __future__ import annotations

import io
import re
import zlib
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Callable

# --------------------------------------------------------------- the browser
# Runs in the document that holds the laid-out ``.page`` elements (the preview,
# the print HTML, or a hidden frame of either).  Returns plain JSON.
DISPLAY_JS = r"""
() => {
  const PT = 0.75, R2 = v => Math.round(v * 100) / 100;
  const pages = Array.from(document.querySelectorAll('.page'));
  const out = {v: 1, w: 612, h: 1008, fonts: [], pages: [],
               stats: {runs: 0, chars: 0, rects: 0, images: 0, svgs: 0, pseudoSkipped: 0,
                       shapesSkipped: 0, clipped: 0}};
  if (!pages.length) return out;
  // A page shown smaller (the preview fits pages to the window) snaps glyphs
  // to a coarser pixel grid: draw every page at full size while it is read,
  // and give it back its zoom afterwards.
  const zooms = pages.map(p => p.style.zoom);
  pages.forEach(p => { p.style.zoom = '1'; });
  try {
  const fontIx = new Map(), ratios = [];
  const range = document.createRange();

  function rgb(c) {
    const m = /rgba?\(([^)]+)\)/.exec(c || '');
    if (!m) return null;
    const p = m[1].split(/[\s,\/]+/).filter(Boolean).map(parseFloat);
    let a = p.length > 3 ? p[3] : 1;
    if (!(a > 0.01)) return null;
    // a translucent colour is laid on white paper: blend it there
    const h = v => Math.round(255 - (255 - v) * a).toString(16).padStart(2, '0');
    return '#' + h(p[0]) + h(p[1]) + h(p[2]);
  }
  const num = v => { const f = parseFloat(v); return isFinite(f) ? f : 0; };

  for (const page of pages) {
    const P = page.getBoundingClientRect();
    const S = P.width / 816;                       // 612 pt = 816 CSS px
    const X = x => R2((x - P.left) / S * PT), Y = y => R2((y - P.top) / S * PT);
    const D = d => R2(d / S * PT);
    // How a computed length relates to the screen.  Browsers disagree on
    // whether computed values include CSS zoom (the report is laid out at 3x
    // inside .hz), so it is measured rather than assumed.
    const hz = page.querySelector('.hz') || page;
    const probe = document.createElement('div');
    probe.style.cssText = 'position:absolute;left:0;top:0;width:100pt;height:1pt;visibility:hidden';
    hz.appendChild(probe);
    const K = probe.getBoundingClientRect().width / num(getComputedStyle(probe).width);
    probe.remove();
    const L = v => R2(num(v) * K / S * PT);         // computed px -> pt

    function font(cs) {
      const key = [cs.fontFamily, cs.fontWeight, cs.fontStyle, cs.fontSize].join('|');
      let ix = fontIx.get(key);
      if (ix !== undefined) return ix;
      // where the baseline sits in the glyph box, measured with the same face
      const s = document.createElement('span');
      s.style.cssText = 'position:absolute;left:0;top:0;white-space:nowrap;line-height:normal;' +
        'letter-spacing:normal;font-family:' + cs.fontFamily + ';font-weight:' + cs.fontWeight +
        ';font-style:' + cs.fontStyle + ';font-size:' + cs.fontSize;
      s.textContent = 'Hg';
      const z = document.createElement('span');
      z.style.cssText = 'display:inline-block;width:0;height:0;vertical-align:baseline';
      s.appendChild(z); hz.appendChild(s);
      range.selectNodeContents(s.firstChild);
      const tr = range.getBoundingClientRect(), zr = z.getBoundingClientRect();
      s.remove();
      ix = out.fonts.length;
      out.fonts.push({family: cs.fontFamily, weight: num(cs.fontWeight) || 400,
                      style: cs.fontStyle, size: L(cs.fontSize)});
      ratios.push(tr.height > 0 ? (zr.top - tr.top) / tr.height : 0.8);
      fontIx.set(key, ix);
      return ix;
    }

    const pg = {t: [], r: [], i: [], s: []};
    const inter = (a, b) => {
      if (!a) return b; if (!b) return a;
      const l = Math.max(a[0], b[0]), t = Math.max(a[1], b[1]);
      const r = Math.min(a[0] + a[2], b[0] + b[2]), bt = Math.min(a[1] + a[3], b[1] + b[3]);
      return [l, t, Math.max(0, r - l), Math.max(0, bt - t)];
    };
    const inside = (c, x, y) => !c || (x >= c[0] - 0.3 && x <= c[0] + c[2] + 0.3 &&
                                       y >= c[1] - 0.3 && y <= c[1] + c[3] + 0.3);
    const box = (b) => [X(b.left), Y(b.top), D(b.width), D(b.height)];

    function fill(x, y, w, h, color, clip, radius) {
      let b = [x, y, w, h];
      if (clip) { b = inter(b, clip); if (b[2] <= 0 || b[3] <= 0) return; }
      const e = [R2(b[0]), R2(b[1]), R2(b[2]), R2(b[3]), color];
      if (radius && radius.some(v => v > 0)) e.push(radius);
      pg.r.push(e); out.stats.rects++;
    }

    function paint(el, cs, b, clip) {
      const bg = rgb(cs.backgroundColor);
      const rad = [cs.borderTopLeftRadius, cs.borderTopRightRadius,
                   cs.borderBottomRightRadius, cs.borderBottomLeftRadius].map(L);
      if (cs.display === 'inline') {
        if (bg) for (const q of el.getClientRects()) fill(X(q.left), Y(q.top), D(q.width), D(q.height), bg, clip);
        return;
      }
      const [x, y, w, h] = box(b);
      if (bg) fill(x, y, w, h, bg, clip, rad);
      // a collapsed table border straddles the grid line: half in each cell
      const collapse = cs.borderCollapse === 'collapse' && /^(TD|TH|TR|TABLE)$/.test(el.tagName);
      for (const [side, horiz] of [['Top', 1], ['Bottom', 1], ['Left', 0], ['Right', 0]]) {
        const st = cs['border' + side + 'Style'];
        if (st === 'none' || st === 'hidden') continue;
        const bw = L(cs['border' + side + 'Width']);
        const c = rgb(cs['border' + side + 'Color']);
        if (!(bw > 0) || !c) continue;
        const off = collapse ? bw / 2 : 0;
        if (side === 'Top') fill(x, y - off, w, bw, c, clip);
        else if (side === 'Bottom') fill(x, y + h - bw + off, w, bw, c, clip);
        else if (side === 'Left') fill(x - off, y, bw, h, c, clip);
        else fill(x + w - bw + off, y, bw, h, c, clip);
      }
    }

    function pad(b, cs) {   // the padding box: where an absolute child is placed, and the clip
      return [X(b.left) + L(cs.borderLeftWidth), Y(b.top) + L(cs.borderTopWidth),
              D(b.width) - L(cs.borderLeftWidth) - L(cs.borderRightWidth),
              D(b.height) - L(cs.borderTopWidth) - L(cs.borderBottomWidth)];
    }

    function pseudo(el, cs, b, which, clip) {
      const ps = getComputedStyle(el, which);
      if (!ps.content || ps.content === 'none' || ps.content === 'normal' || ps.display === 'none') return;
      const bg = rgb(ps.backgroundColor);
      if (!bg) return;
      if (ps.position !== 'absolute') { out.stats.pseudoSkipped++; return; }
      const cb = pad(b, cs);
      const w = ps.width === 'auto' ? cb[2] - L(ps.left) - L(ps.right) : L(ps.width);
      const h = ps.height === 'auto' ? cb[3] - L(ps.top) - L(ps.bottom) : L(ps.height);
      const x = ps.left !== 'auto' ? cb[0] + L(ps.left) : cb[0] + cb[2] - L(ps.right) - w;
      const y = ps.top !== 'auto' ? cb[1] + L(ps.top) : cb[1] + cb[3] - L(ps.bottom) - h;
      fill(x, y, w, h, bg, clip);
    }

    function text(node, clip) {
      const data = node.data;
      if (!/\S/.test(data)) return;
      const el = node.parentElement, cs = getComputedStyle(el);
      if (cs.visibility !== 'visible') return;
      const color = rgb(cs.color);
      if (!color) return;
      const fi = font(cs), ratio = ratios[fi];
      let run = null, gap = null;
      const flush = () => {
        if (!run) return;
        const dx = [];
        for (let k = 1; k < run.xs.length; k++) dx.push(Math.round((run.xs[k] - run.xs[k - 1]) * 100));
        pg.t.push([fi, color, R2(run.xs[0]), R2(run.base), run.s, dx, R2(run.end)]);
        out.stats.runs++; out.stats.chars += run.s.length; run = null;
      };
      for (let i = 0; i < data.length;) {
        const cp = data.codePointAt(i), n = cp > 0xffff ? 2 : 1;
        range.setStart(node, i); range.setEnd(node, i + n);
        i += n;
        const ch = String.fromCodePoint(cp), space = /\s/.test(ch);
        let q = null;
        for (const r of range.getClientRects()) { if (r.width > 0) { q = r; break; } }
        if (!q) continue;                              // collapsed white space
        const x = X(q.left), top = Y(q.top), h = D(q.height), base = top + ratio * h;
        if (space) { if (run && Math.abs(base - run.base) < 0.6) gap = x; continue; }
        if (!inside(clip, x + D(q.width) / 2, base - h * 0.3)) { out.stats.clipped++; flush(); gap = null; continue; }
        if (run && Math.abs(base - run.base) < 0.6 && x > run.xs[run.xs.length - 1] - 0.5) {
          if (gap !== null) { run.s += ' '; run.xs.push(gap); }
          run.s += ch; run.xs.push(x);
        } else {
          flush();
          run = {s: ch, xs: [x], base: base};
        }
        run.end = x + D(q.width);
        gap = null;
      }
      flush();
    }

    function picture(el, cs, b, clip) {
      const nw = el.naturalWidth, nh = el.naturalHeight;
      if (!nw || !nh) return;
      const cb = pad(b, cs);
      const c = [cb[0] + L(cs.paddingLeft), cb[1] + L(cs.paddingTop),
                 cb[2] - L(cs.paddingLeft) - L(cs.paddingRight),
                 cb[3] - L(cs.paddingTop) - L(cs.paddingBottom)];
      let w = c[2], h = c[3];
      const fit = cs.objectFit || 'fill';
      const sc = (fit === 'contain' || fit === 'scale-down') ? Math.min(c[2] / nw, c[3] / nh)
               : fit === 'cover' ? Math.max(c[2] / nw, c[3] / nh) : fit === 'none' ? PT : null;
      if (sc !== null) {
        const s2 = fit === 'scale-down' ? Math.min(sc, PT) : sc;
        w = nw * s2; h = nh * s2;
      }
      const op = (cs.objectPosition || '50% 50%').split(/\s+/);
      const at = (v, free) => /%$/.test(v) ? free * parseFloat(v) / 100 : L(v);
      const x = c[0] + at(op[0] || '50%', c[2] - w), y = c[1] + at(op[1] || '50%', c[3] - h);
      const clip2 = inter(clip, c);
      if (clip2[2] <= 0 || clip2[3] <= 0) return;
      const src = el.currentSrc || el.src || '';
      const e = {x: R2(x), y: R2(y), w: R2(w), h: R2(h), clip: clip2.map(R2), src: src};
      if (/^data:image\/svg|\.svg(\?|#|$)/i.test(src)) {
        // the server has no SVG renderer: this one picture is rasterised here,
        // at four device pixels to the point
        try {
          const cv = document.createElement('canvas');
          cv.width = Math.max(1, Math.round(w * 4)); cv.height = Math.max(1, Math.round(h * 4));
          const g = cv.getContext('2d'); g.fillStyle = '#fff'; g.fillRect(0, 0, cv.width, cv.height);
          g.drawImage(el, 0, 0, cv.width, cv.height);
          e.png = cv.toDataURL('image/png');
        } catch (err) { return; }
      }
      pg.i.push(e); out.stats.images++;
    }

    function svg(el, clip) {
      const b = el.getBoundingClientRect();
      if (!(b.width > 0)) return;
      const vb = el.viewBox && el.viewBox.baseVal && el.viewBox.baseVal.width
        ? [el.viewBox.baseVal.x, el.viewBox.baseVal.y, el.viewBox.baseVal.width, el.viewBox.baseVal.height]
        : [0, 0, b.width, b.height];
      const shapes = [];
      for (const s of el.querySelectorAll('path,line,polyline,polygon,rect,circle,ellipse')) {
        const cs = getComputedStyle(s);
        if (cs.display === 'none' || cs.visibility !== 'visible') continue;
        if (s.transform && s.transform.baseVal && s.transform.baseVal.numberOfItems) { out.stats.shapesSkipped++; continue; }
        const a = n => num(s.getAttribute(n));
        let d = '';
        const t = s.tagName.toLowerCase();
        if (t === 'path') d = s.getAttribute('d') || '';
        else if (t === 'line') d = `M${a('x1')} ${a('y1')}L${a('x2')} ${a('y2')}`;
        else if (t === 'polyline' || t === 'polygon') d = 'M' + (s.getAttribute('points') || '').trim() + (t === 'polygon' ? 'Z' : '');
        else if (t === 'rect') d = `M${a('x')} ${a('y')}h${a('width')}v${a('height')}h${-a('width')}Z`;
        else { const rx = t === 'circle' ? a('r') : a('rx'), ry = t === 'circle' ? a('r') : a('ry');
               d = `E${a('cx')} ${a('cy')} ${rx} ${ry}`; }
        shapes.push([d, rgb(cs.fill === 'none' ? '' : cs.fill), rgb(cs.stroke === 'none' ? '' : cs.stroke),
                     num(cs.strokeWidth), cs.strokeLinecap, cs.strokeLinejoin]);
      }
      pg.s.push({x: X(b.left), y: Y(b.top), w: D(b.width), h: D(b.height), vb: vb,
                 par: el.getAttribute('preserveAspectRatio') || '', shapes: shapes, clip: clip});
      out.stats.svgs++;
    }

    function walk(el, clip) {
      const cs = getComputedStyle(el);
      if (cs.display === 'none') return;
      const b = el.getBoundingClientRect();
      const vis = cs.visibility === 'visible' && num(cs.opacity) > 0.01;
      if (el.namespaceURI === 'http://www.w3.org/2000/svg') { if (vis) svg(el, clip); return; }
      if (vis && el !== page && (b.width > 0 || b.height > 0)) paint(el, cs, b, clip);
      if (el.tagName === 'IMG') { if (vis) picture(el, cs, b, clip); return; }
      if (/^(SCRIPT|STYLE|TEMPLATE|NOSCRIPT)$/.test(el.tagName)) return;
      if (vis) pseudo(el, cs, b, '::before', clip);
      let inner = clip;
      if (cs.overflowX !== 'visible' || cs.overflowY !== 'visible' || /paint|strict|content/.test(cs.contain || ''))
        inner = inter(clip, pad(b, cs));
      for (const c of el.childNodes) {
        if (c.nodeType === 3) { if (vis || cs.visibility === 'visible') text(c, inner); }
        else if (c.nodeType === 1) walk(c, inner);
      }
      if (vis) pseudo(el, cs, b, '::after', clip);
    }

    walk(page, [0, 0, 612, 1008]);
    out.pages.push(pg);
  }
  } finally { pages.forEach((p, i) => { p.style.zoom = zooms[i]; }); }
  return out;
}
"""


# ------------------------------------------------------------------ the faces
def _family(css_family: str) -> str:
    """The first family a computed ``font-family`` names, unquoted."""
    first = (css_family or "").split(",")[0].strip()
    return first.strip("'\"")


def _myriad_face(weight: float, style: str) -> str:
    italic = style in ("italic", "oblique")
    if weight >= 800 and not italic:
        return "MyriadPro-Black"
    if weight >= 600:
        return "MyriadPro-BoldIt" if italic else "MyriadPro-Bold"
    return "MyriadPro-It" if italic else "MyriadPro-Regular"


def face_path(family: str, weight: float, style: str) -> Path | None:
    """The TrueType file the page set this text in.

    ``UAD <size>`` are the per-size kerned copies (``kerned_fonts``), ``UAD
    Wingdings2`` the checkbox face, ``Myriad Pro`` the plain faces; anything
    else -- the browser's own fallback -- is drawn in Myriad's face of the same
    weight, the way the report would have been had the face been there."""
    from . import fonts, kerned_fonts
    name = _family(family)
    m = re.fullmatch(r"UAD (\d+(?:\.\d+)?)", name)
    face = _myriad_face(weight, style)
    if m:
        try:
            return kerned_fonts.build(face, float(m.group(1)))
        except (FileNotFoundError, OSError):
            pass
    if name == "UAD Wingdings2":
        return fonts.source("Wingdings2")
    if face == "MyriadPro-Black":
        face = "MyriadPro-Bold"
    return fonts.face_file(face)


@lru_cache(maxsize=None)
def _fallback_paths(italic: bool, bold: bool) -> tuple[Path, ...]:
    """Faces with a wider character set, for a character the report face lacks
    (the kerned faces carry WinAnsi only): the whole face it was cut from
    (licensed, or the committed substitute, ~340 characters with the symbols
    the form uses), then Source Sans 3, the substitute's own outlines, where
    the deployment carries it."""
    from . import fonts, substitute_fonts
    face = _myriad_face(700 if bold else 400, "italic" if italic else "normal")
    out = [fonts.source(face), fonts.source("MyriadPro-Regular")]
    name = "SourceSans3-" + {(False, False): "Regular", (False, True): "Bold",
                             (True, False): "It", (True, True): "BoldIt"}[(italic, bold)]
    out += [substitute_fonts.SOURCE / f"{name}.ttf", substitute_fonts.SOURCE / "SourceSans3-Regular.ttf"]
    seen, keep = set(), []
    for p in out:
        if p is not None and p.is_file() and p not in seen:
            seen.add(p)
            keep.append(p)
    return tuple(keep)


class _Face:
    """One TrueType file as it goes into the PDF."""

    def __init__(self, path: Path, ref: str):
        from fontTools.ttLib import TTFont
        self.path, self.ref = path, ref
        self.data = path.read_bytes()
        self.font = TTFont(io.BytesIO(self.data), recalcTimestamp=False, lazy=False)
        self.cmap = self.font.getBestCmap() or {}
        self.upem = self.font["head"].unitsPerEm
        self.hmtx = self.font["hmtx"]
        self.used: dict[int, str] = {}            # glyph id -> the text it stands for

    def gid(self, ch: str) -> int | None:
        name = self.cmap.get(ord(ch))
        if name is None:
            return None
        return self.font.getGlyphID(name)

    def width(self, gid: int) -> float:
        """Advance in 1/1000 em, as the /W array states it."""
        name = self.font.getGlyphName(gid)
        return round(self.hmtx[name][0] * 1000 / self.upem, 2)

    def use(self, gid: int, ch: str) -> None:
        self.used.setdefault(gid, ch)


# -------------------------------------------------------------- PDF objects
def _pdf_str(s: str) -> bytes:
    return b"(" + s.encode("latin-1", "replace").replace(b"\\", b"\\\\").replace(
        b"(", b"\\(").replace(b")", b"\\)") + b")"


def _n(v: float) -> str:
    """A number as PDF writes it: short, no exponent."""
    if abs(v - round(v)) < 1e-6:
        return str(int(round(v)))
    return f"{v:.3f}".rstrip("0").rstrip(".")


def _rgb(hexcolor: str) -> tuple[float, float, float]:
    h = (hexcolor or "#000000").lstrip("#")
    if len(h) != 6 or not re.fullmatch(r"[0-9a-fA-F]{6}", h):
        return (0.0, 0.0, 0.0)
    return tuple(int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))  # type: ignore[return-value]


class _Writer:
    def __init__(self):
        self.objects: list[bytes | None] = [None]   # 1-based ids

    def reserve(self) -> int:
        self.objects.append(None)
        return len(self.objects) - 1

    def put(self, oid: int, body: bytes) -> int:
        self.objects[oid] = body
        return oid

    def add(self, body: bytes) -> int:
        return self.put(self.reserve(), body)

    def stream(self, data: bytes, extra: str = "", compress: bool = True) -> int:
        if compress:
            data = zlib.compress(data, 6)
            extra = "/Filter /FlateDecode " + extra
        return self.add(f"<< /Length {len(data)} {extra}>>\nstream\n".encode() + data + b"\nendstream")

    def finish(self, root: int, info: int) -> bytes:
        out = io.BytesIO()
        out.write(b"%PDF-1.7\n%\xe2\xe3\xcf\xd3\n")
        offsets = [0] * len(self.objects)
        for oid in range(1, len(self.objects)):
            offsets[oid] = out.tell()
            out.write(f"{oid} 0 obj\n".encode() + (self.objects[oid] or b"null") + b"\nendobj\n")
        xref = out.tell()
        out.write(f"xref\n0 {len(self.objects)}\n0000000000 65535 f \n".encode())
        for oid in range(1, len(self.objects)):
            out.write(f"{offsets[oid]:010d} 00000 n \n".encode())
        out.write(f"trailer\n<< /Size {len(self.objects)} /Root {root} 0 R /Info {info} 0 R >>\n"
                  f"startxref\n{xref}\n%%EOF\n".encode())
        return out.getvalue()


def _embed_face(w: _Writer, face: _Face) -> int:
    """Type 0 font, CIDFontType2, glyph ids as character codes (Identity-H),
    subset to the glyphs the pages use, with a ToUnicode map."""
    import hashlib

    from fontTools.subset import Options, Subsetter
    gids = sorted(face.used)
    opts = Options()
    opts.retain_gids = True
    opts.notdef_outline = True
    opts.name_IDs = ["*"]
    opts.layout_features = []
    opts.hinting = False
    opts.drop_tables += ["GSUB", "GPOS", "GDEF", "kern", "DSIG"]
    from fontTools.ttLib import TTFont
    font = TTFont(io.BytesIO(face.data), recalcTimestamp=False)
    sub = Subsetter(opts)
    sub.populate(gids=[0] + gids)
    sub.subset(font)
    buf = io.BytesIO()
    font.save(buf)
    program = buf.getvalue()

    ps = face.font["name"].getDebugName(6) or face.path.stem
    ps = re.sub(r"[^A-Za-z0-9-]", "", ps) or "Face"
    digest = hashlib.sha1((ps + ",".join(map(str, gids))).encode()).digest()
    tag = "".join(chr(65 + b % 26) for b in digest[:6])
    base = f"{tag}+{ps}"

    head, hhea = face.font["head"], face.font["hhea"]
    scale = 1000 / face.upem
    os2 = face.font["OS/2"] if "OS/2" in face.font else None
    cap = getattr(os2, "sCapHeight", 0) or hhea.ascent
    italic = face.font["post"].italicAngle if "post" in face.font else 0
    symbolic = "Wingdings" in face.path.stem
    file_id = w.stream(program, f"/Length1 {len(program)} ")
    desc = w.add((
        f"<< /Type /FontDescriptor /FontName /{base} /Flags {4 if symbolic else 32} "
        f"/FontBBox [{_n(head.xMin * scale)} {_n(head.yMin * scale)} {_n(head.xMax * scale)} {_n(head.yMax * scale)}] "
        f"/ItalicAngle {_n(italic)} /Ascent {_n(hhea.ascent * scale)} /Descent {_n(hhea.descent * scale)} "
        f"/CapHeight {_n(cap * scale)} /StemV 80 /FontFile2 {file_id} 0 R >>").encode())
    widths = " ".join(f"{g} [{_n(face.width(g))}]" for g in gids)
    cid = w.add((
        f"<< /Type /Font /Subtype /CIDFontType2 /BaseFont /{base} "
        f"/CIDSystemInfo << /Registry (Adobe) /Ordering (Identity) /Supplement 0 >> "
        f"/FontDescriptor {desc} 0 R /DW 0 /W [{widths}] /CIDToGIDMap /Identity >>").encode())
    lines = []
    for g in gids:
        u = face.used[g].encode("utf-16-be").hex().upper()
        lines.append(f"<{g:04X}> <{u}>")
    chunks = [lines[i:i + 100] for i in range(0, len(lines), 100)]
    cmap = ("/CIDInit /ProcSet findresource begin\n12 dict begin\nbegincmap\n"
            "/CIDSystemInfo << /Registry (Adobe) /Ordering (UCS) /Supplement 0 >> def\n"
            "/CMapName /Adobe-Identity-UCS def\n/CMapType 2 def\n"
            "1 begincodespacerange\n<0000> <FFFF>\nendcodespacerange\n"
            + "".join(f"{len(c)} beginbfchar\n" + "\n".join(c) + "\nendbfchar\n" for c in chunks)
            + "endcmap\nCMapName currentdict /CMap defineresource pop\nend\nend\n")
    tounicode = w.stream(cmap.encode("ascii"))
    return w.add((
        f"<< /Type /Font /Subtype /Type0 /BaseFont /{base} /Encoding /Identity-H "
        f"/DescendantFonts [{cid} 0 R] /ToUnicode {tounicode} 0 R >>").encode())


# ------------------------------------------------------------------ pictures
def _png_passthrough(data: bytes):
    """An 8-bit, non-interlaced RGB or grey PNG goes in as it is: its IDAT
    stream is already Flate with PNG predictors, which PDF reads directly."""
    import struct
    if not data.startswith(b"\x89PNG\r\n\x1a\n"):
        return None
    pos, idat, ihdr = 8, [], None
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IHDR":
            ihdr = struct.unpack(">IIBBBBB", body)
        elif kind == b"IDAT":
            idat.append(body)
        elif kind in (b"PLTE", b"tRNS"):
            return None
        pos += 12 + length
    if not ihdr or not idat:
        return None
    width, height, depth, ctype, _comp, _filt, interlace = ihdr
    if depth != 8 or interlace or ctype not in (0, 2):
        return None
    colors = 3 if ctype == 2 else 1
    return width, height, colors, b"".join(idat)


def _image_object(w: _Writer, data: bytes) -> int | None:
    from PIL import Image, ImageOps
    passed = _png_passthrough(data)
    if passed:
        width, height, colors, idat = passed
        space = "/DeviceRGB" if colors == 3 else "/DeviceGray"
        return w.stream(idat, f"/Type /XObject /Subtype /Image /Width {width} /Height {height} "
                              f"/ColorSpace {space} /BitsPerComponent 8 /Filter /FlateDecode "
                              f"/DecodeParms << /Predictor 15 /Colors {colors} /BitsPerComponent 8 "
                              f"/Columns {width} >> ", compress=False)
    try:
        img = Image.open(io.BytesIO(data))
        img.load()
    except Exception:
        return None
    # the browser turns a photograph by its EXIF orientation; so must the PDF
    orientation = 1
    try:
        orientation = img.getexif().get(0x0112, 1)
    except Exception:
        pass
    if img.format == "JPEG" and img.mode in ("RGB", "L") and orientation in (1, None):
        space = "/DeviceRGB" if img.mode == "RGB" else "/DeviceGray"
        return w.stream(data, f"/Type /XObject /Subtype /Image /Width {img.width} /Height {img.height} "
                              f"/ColorSpace {space} /BitsPerComponent 8 /Filter /DCTDecode ",
                        compress=False)
    img = ImageOps.exif_transpose(img)
    if img.format == "JPEG" or (img.mode in ("RGB", "CMYK", "YCbCr") and img.format not in ("PNG", "GIF")):
        rgb = img.convert("RGB")
        buf = io.BytesIO()
        rgb.save(buf, "JPEG", quality=92)
        return w.stream(buf.getvalue(), f"/Type /XObject /Subtype /Image /Width {rgb.width} "
                                        f"/Height {rgb.height} /ColorSpace /DeviceRGB "
                                        f"/BitsPerComponent 8 /Filter /DCTDecode ", compress=False)
    has_alpha = img.mode in ("RGBA", "LA", "PA") or (img.mode == "P" and "transparency" in img.info)
    rgba = img.convert("RGBA") if has_alpha else img.convert("RGB")
    smask = ""
    if has_alpha:
        alpha = rgba.getchannel("A")
        if alpha.getextrema() != (255, 255):
            sm = w.stream(alpha.tobytes(), f"/Type /XObject /Subtype /Image /Width {rgba.width} "
                                           f"/Height {rgba.height} /ColorSpace /DeviceGray "
                                           f"/BitsPerComponent 8 ")
            smask = f"/SMask {sm} 0 R "
        rgba = rgba.convert("RGB")
    return w.stream(rgba.tobytes(), f"/Type /XObject /Subtype /Image /Width {rgba.width} "
                                    f"/Height {rgba.height} /ColorSpace /DeviceRGB "
                                    f"/BitsPerComponent 8 {smask}")


def _data_uri(src: str) -> bytes | None:
    import base64
    m = re.match(r"data:[^;,]*(;base64)?,", src)
    if not m:
        return None
    body = src[m.end():]
    if m.group(1):
        return base64.b64decode(body)
    from urllib.parse import unquote_to_bytes
    return unquote_to_bytes(body)


# --------------------------------------------------------------------- paths
_TOKEN = re.compile(r"[MmLlHhVvCcSsQqTtAaZzE]|[-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?")
_ARGS = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0, "E": 4}
_K = 0.5522847498


def _path_ops(d: str) -> str:
    """An SVG path (plus ``E cx cy rx ry``, an ellipse) in PDF path operators."""
    toks = _TOKEN.findall(d or "")
    ops: list[str] = []
    i, cmd = 0, ""
    x = y = sx = sy = 0.0
    lc = None                                   # last control point, for S / T
    while i < len(toks):
        t = toks[i]
        if t.isalpha():
            cmd = t
            i += 1
            if cmd in "Zz":
                ops.append("h")
                x, y, lc = sx, sy, None
                continue
        if not cmd:
            break
        n = _ARGS[cmd.upper()]
        args = toks[i:i + n]
        if len(args) < n or any(a.isalpha() for a in args):
            break
        i += n
        a = [float(v) for v in args]
        rel = cmd.islower()
        up = cmd.upper()
        if up == "M":
            x, y = (x + a[0], y + a[1]) if rel else (a[0], a[1])
            sx, sy = x, y
            ops.append(f"{_n(x)} {_n(y)} m")
            cmd = "l" if rel else "L"            # further pairs are line-tos
            lc = None
        elif up in "LHV":
            if up == "L":
                x, y = (x + a[0], y + a[1]) if rel else (a[0], a[1])
            elif up == "H":
                x = x + a[0] if rel else a[0]
            else:
                y = y + a[0] if rel else a[0]
            ops.append(f"{_n(x)} {_n(y)} l")
            lc = None
        elif up in "CS":
            if up == "C":
                c1 = (x + a[0], y + a[1]) if rel else (a[0], a[1])
                rest = a[2:]
            else:
                c1 = (2 * x - lc[0], 2 * y - lc[1]) if lc else (x, y)
                rest = a
            c2 = (x + rest[0], y + rest[1]) if rel else (rest[0], rest[1])
            end = (x + rest[2], y + rest[3]) if rel else (rest[2], rest[3])
            ops.append(f"{_n(c1[0])} {_n(c1[1])} {_n(c2[0])} {_n(c2[1])} {_n(end[0])} {_n(end[1])} c")
            lc, (x, y) = c2, end
        elif up in "QT":
            if up == "Q":
                q = (x + a[0], y + a[1]) if rel else (a[0], a[1])
                end = (x + a[2], y + a[3]) if rel else (a[2], a[3])
            else:
                q = (2 * x - lc[0], 2 * y - lc[1]) if lc else (x, y)
                end = (x + a[0], y + a[1]) if rel else (a[0], a[1])
            c1 = (x + 2 / 3 * (q[0] - x), y + 2 / 3 * (q[1] - y))
            c2 = (end[0] + 2 / 3 * (q[0] - end[0]), end[1] + 2 / 3 * (q[1] - end[1]))
            ops.append(f"{_n(c1[0])} {_n(c1[1])} {_n(c2[0])} {_n(c2[1])} {_n(end[0])} {_n(end[1])} c")
            lc, (x, y) = q, end
        elif up == "A":
            # an arc is drawn as its chord; none of the report's strokes uses one
            x, y = (x + a[5], y + a[6]) if rel else (a[5], a[6])
            ops.append(f"{_n(x)} {_n(y)} l")
            lc = None
        elif up == "E":
            cx, cy, rx, ry = a
            kx, ky = rx * _K, ry * _K
            ops.append(f"{_n(cx + rx)} {_n(cy)} m "
                       f"{_n(cx + rx)} {_n(cy + ky)} {_n(cx + kx)} {_n(cy + ry)} {_n(cx)} {_n(cy + ry)} c "
                       f"{_n(cx - kx)} {_n(cy + ry)} {_n(cx - rx)} {_n(cy + ky)} {_n(cx - rx)} {_n(cy)} c "
                       f"{_n(cx - rx)} {_n(cy - ky)} {_n(cx - kx)} {_n(cy - ry)} {_n(cx)} {_n(cy - ry)} c "
                       f"{_n(cx + kx)} {_n(cy - ry)} {_n(cx + rx)} {_n(cy - ky)} {_n(cx + rx)} {_n(cy)} c h")
            x, y = cx + rx, cy
    return " ".join(ops)


def _rounded(x: float, y: float, w: float, h: float, r: list[float]) -> str:
    tl, tr, br, bl = [max(0.0, min(v, w / 2, h / 2)) for v in (list(r) + [0, 0, 0, 0])[:4]]
    k = 1 - _K
    return (f"{_n(x + tl)} {_n(y)} m {_n(x + w - tr)} {_n(y)} l "
            f"{_n(x + w - tr * k)} {_n(y)} {_n(x + w)} {_n(y + tr * k)} {_n(x + w)} {_n(y + tr)} c "
            f"{_n(x + w)} {_n(y + h - br)} l "
            f"{_n(x + w)} {_n(y + h - br * k)} {_n(x + w - br * k)} {_n(y + h)} {_n(x + w - br)} {_n(y + h)} c "
            f"{_n(x + bl)} {_n(y + h)} l "
            f"{_n(x + bl * k)} {_n(y + h)} {_n(x)} {_n(y + h - bl * k)} {_n(x)} {_n(y + h - bl)} c "
            f"{_n(x)} {_n(y + tl)} l "
            f"{_n(x)} {_n(y + tl * k)} {_n(x + tl * k)} {_n(y)} {_n(x + tl)} {_n(y)} c h")


# ------------------------------------------------------------------- writing
@dataclass
class Result:
    pdf: bytes
    pages: int
    missing_glyphs: dict[str, int] = field(default_factory=dict)
    missing_images: list[str] = field(default_factory=list)


class DisplayError(ValueError):
    """The display list is not one this writer can trust."""


def write(display: dict, *, resolve: Callable[[str], bytes | None] | None = None,
          title: str = "", allow_data_uri: bool = False,
          raster_ok: Callable[[str], bool] | None = None) -> Result:
    """The PDF for a display list from ``DISPLAY_JS``.

    ``resolve`` turns a picture's ``src`` into the file's bytes -- the server's
    own copy; a ``data:`` URI is read directly only with ``allow_data_uri``
    (pages built for a local PDF embed their pictures that way).  A picture
    the browser rasterised (``png``) is taken only for an SVG picture, and
    with ``raster_ok`` only where it accepts the picture's ``src``."""
    if not isinstance(display, dict) or not isinstance(display.get("pages"), list):
        raise DisplayError("no pages")
    width = float(display.get("w") or 612)
    height = float(display.get("h") or 1008)
    fonts_in = display.get("fonts") or []
    w = _Writer()
    pages_id = w.reserve()
    faces: dict[Path, _Face] = {}
    images: dict[str, int | None] = {}
    result = Result(b"", 0)

    def face_for(path: Path) -> _Face:
        if path not in faces:
            faces[path] = _Face(path, f"F{len(faces) + 1}")
        return faces[path]

    resolved_fonts: list[tuple[_Face | None, float, tuple[_Face, ...]]] = []
    for f in fonts_in:
        if not isinstance(f, dict):
            resolved_fonts.append((None, 0.0, ()))
            continue
        weight = float(f.get("weight") or 400)
        style = str(f.get("style") or "normal")
        path = face_path(str(f.get("family") or ""), weight, style)
        primary = face_for(path) if path else None
        backups = tuple(face_for(p) for p in _fallback_paths(style in ("italic", "oblique"), weight >= 600)
                        if p != path)
        resolved_fonts.append((primary, float(f.get("size") or 9), backups))

    page_ids = []
    for pg in display["pages"]:
        if not isinstance(pg, dict):
            raise DisplayError("a page is not an object")
        ops: list[str] = [f"1 0 0 -1 0 {_n(height)} cm"]
        used_faces: set[str] = set()
        used_images: dict[str, int] = {}

        # filled boxes and rules, in the order the page painted them
        for r in pg.get("r") or []:
            x, y, rw, rh = (float(v) for v in r[:4])
            red, green, blue = _rgb(str(r[4]))
            ops.append(f"{_n(red)} {_n(green)} {_n(blue)} rg")
            if len(r) > 5 and r[5]:
                ops.append(_rounded(x, y, rw, rh, [float(v) for v in r[5]]) + " f")
            else:
                ops.append(f"{_n(x)} {_n(y)} {_n(rw)} {_n(rh)} re f")

        # pictures
        for im in pg.get("i") or []:
            src = str(im.get("src") or "")
            key = str(im.get("png") or src)
            if key not in images:
                data = None
                if im.get("png"):
                    svg = bool(re.match(r"data:image/svg", src, re.I) or
                               re.search(r"\.svg(?:[?#]|$)", src, re.I))
                    if svg and (raster_ok is None or raster_ok(src)):
                        data = _data_uri(str(im["png"]))
                elif key.startswith("data:"):
                    data = _data_uri(key) if allow_data_uri else None
                elif resolve is not None:
                    data = resolve(key)
                images[key] = _image_object(w, data) if data else None
                if images[key] is None:
                    result.missing_images.append(src[:120] or key[:120])
            oid = images[key]
            if oid is None:
                continue
            name = used_images.setdefault(key, f"Im{oid}")
            x, y, iw, ih = (float(im[k]) for k in ("x", "y", "w", "h"))
            clip = im.get("clip")
            ops.append("q")
            if clip:
                cx, cy, cw, ch = (float(v) for v in clip)
                ops.append(f"{_n(cx)} {_n(cy)} {_n(cw)} {_n(ch)} re W n")
            ops.append(f"{_n(iw)} 0 0 {_n(-ih)} {_n(x)} {_n(y + ih)} cm /{name} Do Q")

        # inline SVG (the ticks)
        for sv in pg.get("s") or []:
            vb = [float(v) for v in (sv.get("vb") or [0, 0, 1, 1])]
            x, y, bw, bh = (float(sv[k]) for k in ("x", "y", "w", "h"))
            if vb[2] <= 0 or vb[3] <= 0 or bw <= 0 or bh <= 0:
                continue
            sx, sy = bw / vb[2], bh / vb[3]
            par = str(sv.get("par") or "")
            tx, ty = x, y
            if not par.startswith("none"):
                s = min(sx, sy) if "slice" not in par else max(sx, sy)
                tx += (bw - vb[2] * s) / 2
                ty += (bh - vb[3] * s) / 2
                sx = sy = s
            ops.append("q")
            clip = sv.get("clip")
            if clip:
                cx, cy, cw, ch = (float(v) for v in clip)
                ops.append(f"{_n(cx)} {_n(cy)} {_n(cw)} {_n(ch)} re W n")
            ops.append(f"{_n(sx)} 0 0 {_n(sy)} {_n(tx - vb[0] * sx)} {_n(ty - vb[1] * sy)} cm")
            for d, fill, stroke, sw, cap, join in sv.get("shapes") or []:
                path = _path_ops(str(d))
                if not path or (not fill and not stroke):
                    continue
                if fill:
                    ops.append("{} {} {} rg".format(*map(_n, _rgb(fill))))
                if stroke:
                    ops.append("{} {} {} RG".format(*map(_n, _rgb(stroke))))
                    ops.append(f"{_n(float(sw or 1))} w "
                               f"{ {'round': 1, 'square': 2}.get(str(cap), 0)} J "
                               f"{ {'round': 1, 'bevel': 2}.get(str(join), 0)} j")
                ops.append(path + (" B" if fill and stroke else " f" if fill else " S"))
            ops.append("Q")

        # text, last, over everything
        for t in pg.get("t") or []:
            fi, color, x0, base, s, dx = int(t[0]), str(t[1]), float(t[2]), float(t[3]), str(t[4]), t[5]
            if not (0 <= fi < len(resolved_fonts)):
                raise DisplayError("a run names a face the list does not declare")
            primary, size, backups = resolved_fonts[fi]
            chars = list(s)
            if len(dx) != len(chars) - 1:
                raise DisplayError("a run's positions do not match its text")
            xs = [x0]
            for d in dx:
                xs.append(xs[-1] + float(d) / 100)
            # each character in the first face that has it
            pieces: list[tuple[_Face, list[tuple[int, float, str]]]] = []
            for ch, cx in zip(chars, xs):
                face, gid = None, None
                for cand in ((primary,) if primary else ()) + backups:
                    gid = cand.gid(ch)
                    if gid:
                        face = cand
                        break
                if face is None or gid is None:
                    if not ch.isspace():
                        result.missing_glyphs[ch] = result.missing_glyphs.get(ch, 0) + 1
                    continue
                face.use(gid, ch)
                if pieces and pieces[-1][0] is face:
                    pieces[-1][1].append((gid, cx, ch))
                else:
                    pieces.append((face, [(gid, cx, ch)]))
            if not pieces:
                continue
            red, green, blue = _rgb(color)
            ops.append(f"BT {_n(red)} {_n(green)} {_n(blue)} rg")
            for face, glyphs in pieces:
                used_faces.add(face.ref)
                ops.append(f"/{face.ref} {_n(size)} Tf 1 0 0 -1 {_n(glyphs[0][1])} {_n(base)} Tm")
                tj: list[str] = []
                hexrun = ""
                for k, (gid, cx, _ch) in enumerate(glyphs):
                    hexrun += f"{gid:04X}"
                    if k + 1 < len(glyphs):
                        adv = face.width(gid)
                        adj = adv - (glyphs[k + 1][1] - cx) * 1000 / size
                        if abs(adj) >= 0.05:
                            tj.append(f"<{hexrun}> {_n(round(adj, 2))}")
                            hexrun = ""
                if hexrun:
                    tj.append(f"<{hexrun}>")
                ops.append("[" + " ".join(tj) + "] TJ")
            ops.append("ET")

        content = w.stream("\n".join(ops).encode("ascii"))
        page_ids.append((w.reserve(), content, used_faces, used_images))

    font_ids = {face.ref: _embed_face(w, face) for face in faces.values() if face.used}
    for pid, content, used_faces, used_images in page_ids:
        fres = " ".join(f"/{ref} {font_ids[ref]} 0 R" for ref in sorted(used_faces) if ref in font_ids)
        xres = " ".join(f"/{name} {images[key]} 0 R" for key, name in used_images.items())
        w.put(pid, (f"<< /Type /Page /Parent {pages_id} 0 R /MediaBox [0 0 {_n(width)} {_n(height)}] "
                    f"/Resources << /Font << {fres} >> /XObject << {xres} >> >> "
                    f"/Contents {content} 0 R >>").encode())
    w.put(pages_id, (f"<< /Type /Pages /Count {len(page_ids)} /Kids ["
                     + " ".join(f"{pid} 0 R" for pid, *_ in page_ids) + "] >>").encode())
    root = w.add(f"<< /Type /Catalog /Pages {pages_id} 0 R >>".encode())
    info = w.add(b"<< /Producer (UAD 3.6 Form Filler) /Creator (UAD 3.6 Form Filler) /Title "
                 + _pdf_str(title or "Appraisal Report") + b" >>")
    result.pdf = w.finish(root, info)
    result.pages = len(page_ids)
    return result


# ------------------------------------------------------------ the text check
_WS = re.compile(r"[\s﻿]+")


def page_texts(html: str) -> list[str]:
    """What each ``.page`` of a laid-out report says, white space removed."""
    from lxml import html as lhtml
    doc = lhtml.fromstring(html)
    out = []
    for page in doc.xpath("//div[contains(concat(' ', normalize-space(@class), ' '), ' page ')]"):
        parts = []
        for el in page.iter():
            if not isinstance(el.tag, str):
                continue
            if el.tag in ("script", "style"):
                if el.tail:
                    parts.append(el.tail)
                continue
            if el.text and el.getparent() is not None and el.getparent().tag in ("script", "style"):
                continue
            if el.text:
                parts.append(el.text)
            if el is not page and el.tail:
                parts.append(el.tail)
        out.append(_WS.sub("", "".join(parts)))
    return out


def check_text(display: dict, html: str) -> int:
    """Refuse a display list whose words are not the report's own.

    Page by page, everything the browser says it drew must appear in the
    server's own page, in the same order (text the page hides -- a repeated
    heading row that does not print -- may be missing, nothing may be added).
    Returns how many of the server's characters the browser did not draw."""
    server = page_texts(html)
    pages = display.get("pages") or []
    if len(server) != len(pages):
        raise DisplayError(f"the browser drew {len(pages)} pages; the report has {len(server)}")
    skipped = 0
    for n, (theirs, ours) in enumerate(zip(pages, server), start=1):
        drawn = _WS.sub("", "".join(str(t[4]) for t in (theirs.get("t") or [])))
        i = 0
        for ch in drawn:
            j = ours.find(ch, i)
            if j < 0:
                raise DisplayError(f"page {n} holds text that is not in the report")
            skipped += j - i
            i = j + 1
        skipped += len(ours) - i
    return skipped
