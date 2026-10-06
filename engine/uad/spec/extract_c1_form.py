"""Read the URAR form itself out of Appendix C-1.

Appendix C-1 is the form: every element any URAR can carry, laid out once on
41 pages, "regardless of conditionality" (Appendix E p4).  It ships twice --
once as a clean layout whose labels are real text, and once with each field's
Report Field ID printed in red where its value goes.  The two are the same
drawing, so reading them together gives, for every element, what it is, where
it sits, how it is styled and which field fills it.

Nothing here is a transcription.  Every label, rule, bar, checkbox, table
column and field slot below comes from a primitive in those two PDFs:

* a black filled box at the margin with white 9 pt text is a section **TAB**;
* a 15 pt #e6e7e8 stroke across the measure is an **H1** subsection bar;
* a 1 pt ink rule under 9 pt bold is an **H2** subheading (45 or 22 picas);
* 9 pt text with a 0.5 pt #939598 rule at its baseline, 22 picas wide, is a
  **TXR** row -- bold at 4 pt in, regular at 12 pt (TXR-I) or 21 pt (TXR-II);
* Wingdings2 on a label's line is a **CK** checkbox row, and "Yes"/"No" in
  8 pt bold above it is its **Y/N** header;
* interior vertical rules bound a **table**; the 9 pt bold text above its first
  rule is the column heading (TCH) and 8 pt text in its first column is a
  fixed row label (TB);
* a 0.5 pt grey rectangle holding the camera glyph is a **photo** slot.

Run it to rebuild ``engine/spec/c1_form.json``.
"""
from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from pathlib import Path

import pymupdf

ROOT = Path(__file__).resolve().parents[3]
LAYOUT = ROOT / "_ref" / "layout" / "Appendix C-1 URAR without Report Field IDs v1.3.pdf"
WITH_IDS = ROOT / "_ref" / "layout" / "Appendix C-1 URAR with Report Field IDs v1.3.pdf"
OUT = ROOT / "engine" / "spec" / "c1_form.json"

INK = "#231f20"
GREY_RULE = "#939598"
BAR_FILL = "#e6e7e8"
MARGIN_L, MARGIN_R = 36.0, 576.0
COL_SPLIT = 306.0                 # the gutter's centre: 36 + 264 + 6
BODY_TOP, BODY_BOTTOM = 50.0, 930.0

FIELD_ID = re.compile(r"HF\.\d{3}|\d{1,2}\.\d{2,3}(?:\.\d{1,2}){0,2}")


def hexc(c) -> str | None:
    if not c:
        return None
    return "#%02x%02x%02x" % tuple(int(round(x * 255)) for x in c[:3])


# ---------------------------------------------------------------- primitives
@dataclass
class Text:
    text: str
    x0: float
    y0: float
    x1: float
    y1: float
    size: float
    font: str
    colour: str
    raw: str = ""

    @property
    def bold(self) -> bool:
        return "Bold" in self.font or "Black" in self.font

    @property
    def italic(self) -> bool:
        return self.font.endswith("It") or "Italic" in self.font

    @property
    def wing(self) -> bool:
        return "Wingdings" in self.font

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


@dataclass
class Rule:
    x0: float
    x1: float
    y: float
    colour: str
    width: float


@dataclass
class VRule:
    x: float
    y0: float
    y1: float
    colour: str
    width: float


@dataclass
class Box:
    x0: float
    y0: float
    x1: float
    y1: float
    fill: str | None
    stroke: str | None
    shape: str


@dataclass
class FieldMark:
    ids: list[str]
    x0: float
    y0: float
    x1: float
    y1: float

    @property
    def cy(self) -> float:
        return (self.y0 + self.y1) / 2


def _decode(text: str) -> str:
    """Some pages set the IDs in a subset font shifted 29 code points down."""
    if any(ord(c) < 0x20 for c in text):
        return "".join(chr(ord(c) + 29) if ord(c) < 0x60 else c for c in text)
    return text


ID_RANGE = re.compile(r"(\d{1,2}\.\d{2,3})\s*-\s*(\d{1,2}\.\d{2,3})")


def _spans(page) -> list[Text]:
    out: list[Text] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for s in line["spans"]:
                if not s["text"].strip():
                    continue
                x0, y0, x1, y1 = s["bbox"]
                out.append(Text(" ".join(s["text"].split()), x0, y0, x1, y1,
                                round(s["size"], 1), s["font"].split("+")[-1],
                                "#%06x" % s["color"], raw=s["text"]))
    return out


def _merge_spans(spans: list[Text]) -> list[Text]:
    """Join the spans of one run of text that the PDF split mid-line."""
    spans = sorted(spans, key=lambda s: (round(s.y0), s.x0))
    out: list[Text] = []
    for s in spans:
        prev = out[-1] if out else None
        if (prev is not None and not s.wing and not prev.wing
                and abs(prev.y0 - s.y0) < 1.2 and 0 <= s.x0 - prev.x1 < 3.5
                and prev.size == s.size and prev.bold == s.bold
                and prev.italic == s.italic and prev.colour == s.colour):
            joiner = "" if prev.raw.endswith(" ") or s.raw.startswith(" ") else ""
            gap = " " if (s.x0 - prev.x1) > 1.2 or prev.raw.endswith(" ") else joiner
            prev.text = (prev.text + gap + s.text).strip()
            prev.raw = prev.raw + (" " if gap else "") + s.raw
            prev.x1 = s.x1
            prev.y1 = max(prev.y1, s.y1)
            continue
        out.append(s)
    return out


def _drawings(page):
    rules: list[Rule] = []
    vrules: list[VRule] = []
    boxes: list[Box] = []
    for d in page.get_drawings():
        r = d["rect"]
        fill, stroke = hexc(d.get("fill")), hexc(d.get("color"))
        width = float(d.get("width") or 0)
        kinds = "".join(i[0] for i in d["items"])
        if d["type"] == "s" and kinds == "l":
            if r.height < 1:
                rules.append(Rule(r.x0, r.x1, round(r.y0, 1), stroke or "", width))
            elif r.width < 1:
                vrules.append(VRule(round(r.x0, 1), r.y0, r.y1, stroke or "", width))
            continue
        if r.width > 4 and r.height > 4:
            boxes.append(Box(r.x0, r.y0, r.x1, r.y1, fill, stroke, kinds))
    return rules, vrules, boxes


def _marks(page) -> list[FieldMark]:
    """The red field IDs, decoded and re-joined.

    An ID is often split across spans -- "4.00" in Arial then "1" in a shifted
    ArialMT subset -- so spans are decoded one at a time and joined along the
    line before the ID pattern is looked for.
    """
    raw: list[list] = []
    for block in page.get_text("dict")["blocks"]:
        for line in block.get("lines", []):
            for s in line["spans"]:
                colour = "#%06x" % s["color"]
                # decode before testing for blank: the shifted subset writes
                # "9" as \x1c, which str.strip() counts as whitespace (C-1 p13
                # lost 9.000-9.002 and 9.010-9.011 to it)
                if colour in (INK, "#ffffff", "#77787b", GREY_RULE) or not _decode(s["text"]).strip():
                    continue
                x0, y0, x1, y1 = s["bbox"]
                if y0 < BODY_TOP - 22 or x0 < 0 or x0 > 612:
                    continue
                raw.append([_decode(s["text"]), x0, y0, x1, y1])
    # group into lines by vertical position, then join along each line
    raw.sort(key=lambda r: r[2])
    lines: list[list[list]] = []
    for r in raw:
        line = next((ln for ln in lines if abs(ln[0][2] - r[2]) < 1.6), None)
        if line is None:
            lines.append([r])
        else:
            line.append(r)
    runs: list[list] = []
    for line in lines:
        line.sort(key=lambda r: r[1])
        current: list | None = None
        for r in line:
            if current is not None and -0.5 <= r[1] - current[3] < 9:
                current[0] += r[0]
                current[3] = r[3]
                current[4] = max(current[4], r[4])
                continue
            current = list(r)
            runs.append(current)
    out: list[FieldMark] = []
    for text, x0, y0, x1, y1 in runs:
        ids = FIELD_ID.findall(text)
        if not ids:
            continue
        out.append(FieldMark(ids, x0, y0, x1, y1))
    return out


# ------------------------------------------------------------------- tables
@dataclass
class TableGeom:
    x0: float
    x1: float
    top: float           # the rule under the column heads
    bottom: float
    edges: list[float]   # column boundaries, left to right
    lines: list[float]   # every horizontal rule y inside, in order
    vrules: list = field(default_factory=list)
    dark: list = field(default_factory=list)


def _tables(rules: list[Rule], vrules: list[VRule], boxes: list[Box]) -> list[TableGeom]:
    """Find tables by their interior vertical rules.

    A table in C-1 draws a vertical rule between columns for every body row.
    Vertical rules that stack one under another at the same x belong to one
    table; the horizontal rules they meet give its rows.
    """
    grey_v = [v for v in vrules if v.width <= 1.0 and BODY_TOP < v.y0 < BODY_BOTTOM
              and v.colour in (GREY_RULE, "#a7a9ac", INK)]
    grey_v.sort(key=lambda v: (v.y0, v.x))
    dark = [b for b in boxes if b.fill in ("#939598", "#a7a9ac", "#58595b")]

    def bridged(y_top: float, y_bottom: float) -> bool:
        """A dark sub-heading bar fills the gap between two runs of cells."""
        return any(b.y0 <= y_top + 1 and b.y1 >= y_bottom - 1 for b in dark)

    clusters: list[list[VRule]] = []
    for v in grey_v:
        for c in clusters:
            bottom = max(u.y1 for u in c)
            gap = v.y0 - bottom
            if v.y0 >= min(u.y0 for u in c) - 3 and (
                    gap <= 3.5 or (gap <= 14.5 and bridged(bottom, v.y0))):
                c.append(v)
                break
        else:
            clusters.append([v])
    out: list[TableGeom] = []
    for c in clusters:
        y0 = min(v.y0 for v in c)
        y1 = max(v.y1 for v in c)
        xs = sorted({round(v.x, 1) for v in c})
        inside = [r for r in rules if r.colour in (GREY_RULE, INK, "#a7a9ac")
                  and r.width <= 1.0 and y0 - 1.5 <= r.y <= y1 + 1.5
                  and r.x1 > xs[0] - 1 and r.x0 < xs[-1] + 1]
        spans_x = [(r.x0, r.x1) for r in inside]
        spans_x += [(b.x0, b.x1) for b in dark if b.y0 <= y1 and b.y1 >= y0]
        if not spans_x:
            continue
        x0 = min(a for a, _b in spans_x)
        x1 = max(b for _a, b in spans_x)
        # Rows are bounded by rules where a table draws them and by the ends of
        # its vertical rules where it does not (the DDD table has no interior
        # horizontals -- its rows are separated by sub-heading bars).
        ys = {round(r.y, 1) for r in inside}
        ys |= {round(v.y0, 1) for v in c} | {round(v.y1, 1) for v in c}
        for b in dark:
            if b.y0 >= y0 - 16 and b.y1 <= y1 + 16 and b.x1 > x0 and b.x0 < x1:
                ys |= {round(b.y0, 1), round(b.y1, 1)}
        lines: list[float] = []
        for y in sorted(ys):
            if not lines or y - lines[-1] > 1.2:
                lines.append(y)
        geom = TableGeom(x0, x1, lines[0], lines[-1],
                         [x0] + [float(x) for x in xs] + [x1], lines)
        geom.vrules = [(v.x, v.y0, v.y1) for v in c]
        geom.dark = [b for b in dark if b.y0 >= y0 - 16 and b.y1 <= y1 + 16]
        out.append(geom)
    return sorted(out, key=lambda t: t.top)


# ----------------------------------------------------------------- elements
def _column_of(x0: float, x1: float) -> str:
    if x0 < COL_SPLIT - 2 and x1 > COL_SPLIT + 12:
        return "full"
    return "left" if x0 < COL_SPLIT else "right"


def _indent_style(x0: float, bold: bool, column: str) -> str:
    base = MARGIN_L if column != "right" else 312.0
    inset = x0 - base
    if inset < 7:
        return "TXR-B" if bold else "TXR"
    if inset < 16:
        return "TXR-I"
    return "TXR-II"


def extract_page(layout_page, ids_page, number: int) -> dict:
    spans = [s for s in _merge_spans(_spans(layout_page))
             if BODY_TOP < s.y0 < BODY_BOTTOM]
    rules, vrules, boxes = _drawings(layout_page)
    rules = [r for r in rules if BODY_TOP < r.y < BODY_BOTTOM + 2]
    marks = [m for m in _marks(ids_page) if BODY_TOP - 8 < m.y0 < BODY_BOTTOM]
    tables = _tables(rules, vrules, boxes)

    used: set[int] = set()
    elements: list[dict] = []

    def claim(pred) -> list[Text]:
        got = []
        for i, s in enumerate(spans):
            if i not in used and pred(s):
                used.add(i)
                got.append(s)
        return got

    # --- the Summary page's lead: title, address and SUMMARY heading
    lead = claim(lambda s: s.size >= 11.5 and not s.wing)
    if lead:
        elements.append({"kind": "lead", "y": min(s.y0 for s in lead),
                         "y1": max(s.y1 for s in lead), "x0": 36.0, "x1": 576.0,
                         "column": "full",
                         "lines": [{"text": s.text, "size": s.size, "font": s.font}
                                   for s in sorted(lead, key=lambda s: s.y0)],
                         "ids": []})
    claim(lambda s: not s.text.strip("\x08 "))

    # --- section tabs
    for b in boxes:
        if b.fill == INK and abs(b.x0 - MARGIN_L) < 1 and 12 < b.y1 - b.y0 < 18:
            title = claim(lambda s: s.colour == "#ffffff" and b.y0 - 1 <= s.cy <= b.y1 + 1)
            elements.append({"kind": "tab", "y": b.y0, "y1": b.y1 + 0.5,
                             "x0": b.x0, "x1": b.x1, "column": "full",
                             "title": " ".join(s.text for s in sorted(title, key=lambda s: s.x0)),
                             "ids": []})

    # --- H1 bars
    for r in rules:
        if r.colour == BAR_FILL and r.width >= 10:
            y0, y1 = r.y - r.width / 2, r.y + r.width / 2
            inside = claim(lambda s: y0 - 1 <= s.cy <= y1 + 1 and not s.wing)
            elements.append({
                "kind": "h1", "y": y0, "y1": y1, "x0": r.x0, "x1": r.x1,
                "column": _column_of(r.x0, r.x1),
                "title": " ".join(s.text for s in inside if not s.italic),
                "note": " ".join(s.text for s in inside if s.italic),
                "ids": []})

    # --- H2 subheadings: a 1 pt ink rule with bold text on the line above it
    for r in rules:
        if r.colour == INK and 0.9 <= r.width <= 1.1:
            label = claim(lambda s: r.y - 16 <= s.y1 <= r.y + 0.5 and s.bold
                          and s.size >= 8.5 and r.x0 - 1 <= s.x0 <= r.x0 + 40
                          and not s.wing)
            if not label:
                continue
            yn = claim(lambda s: r.y - 16 <= s.y1 <= r.y + 0.5 and s.size < 8.5
                       and s.text in ("Yes", "No") and r.x0 <= s.x0 <= r.x1)
            checks = claim(lambda s: s.wing and r.y - 16 <= s.cy <= r.y + 12
                           and r.x0 <= s.x0 <= r.x1)
            elements.append({
                "kind": "h2", "y": min(s.y0 for s in label), "y1": r.y + 0.5,
                "x0": r.x0, "x1": r.x1, "column": _column_of(r.x0, r.x1),
                "title": " ".join(s.text for s in label),
                "yes_no": bool(yn or checks), "ids": []})

    # --- tables
    for t in tables:
        heads = [s for i, s in enumerate(spans)
                 if i not in used and t.x0 - 1 <= s.x0 <= t.x1
                 and t.top - 34 <= s.y1 <= t.top + 1.5
                 and s.bold and s.size >= 8.5 and not s.wing and s.colour == INK
                 and not any(r.colour == GREY_RULE and abs(r.y - s.y1) < 2.2
                             and r.x0 - 1 <= s.x0 and r.x1 > s.x0 + 20
                             and r.y < t.top - 3 for r in rules)]
        if heads:
            # the heading block is contiguous: stop at the first gap of a line
            heads.sort(key=lambda s: -s.y1)
            band, floor = [], max(s.y1 for s in heads)
            for s in heads:
                if floor - s.y1 < 12.5:
                    band.append(s)
                    floor = min(floor, s.y0 + 0.5)
            heads = band
        edges: list[float] = []
        for e in sorted(t.edges):
            if not edges or e - edges[-1] > 3:
                edges.append(e)
        cols = []
        for a, b in zip(edges, edges[1:]):
            words = sorted((s for s in heads if a - 1 <= s.x0 < b - 2),
                           key=lambda s: (s.y0, s.x0))
            cols.append({"x0": a, "x1": b, "head": " ".join(w.text for w in words)})
        for s in heads:
            used.add(spans.index(s))
        rows = []
        for ya, yb in zip(t.lines, t.lines[1:]):
            if yb - ya < 5:
                continue
            has_v = any(ya - 0.5 <= (vy0 + vy1) / 2 <= yb + 0.5
                        for _x, vy0, vy1 in t.vrules)
            bar = next((b.fill for b in t.dark
                        if b.y0 - 1.5 <= ya and b.y1 + 1.5 >= yb), None)
            white = [s for i, s in enumerate(spans)
                     if i not in used and s.colour == "#ffffff"
                     and ya - 1 <= s.cy <= yb + 1 and t.x0 - 1 <= s.x0 <= t.x1]
            row: dict = {"y": ya, "y1": yb}
            if bar and (not has_v or white):
                row["bar"] = bar
                for s in white:
                    used.add(spans.index(s))
                row["text"] = " ".join(s.text for s in sorted(white, key=lambda s: s.x0))
                row["align"] = ("right" if white and min(s.x0 for s in white)
                                > (t.x0 + t.x1) / 2 else "left")
                row["x0"] = min((s.x0 for s in white), default=t.x0)
                row["ids"] = []
            cells = []
            for c in cols:
                texts = [s for i, s in enumerate(spans)
                         if i not in used and ya - 1 <= s.cy <= yb + 1
                         and c["x0"] - 1 <= s.x0 < c["x1"] - 2]
                for s in texts:
                    used.add(spans.index(s))
                cells.append({"x0": c["x0"], "x1": c["x1"],
                              "text": " ".join(s.text for s in texts if not s.wing),
                              "bold": any(s.bold for s in texts if not s.wing),
                              "check": any(s.wing for s in texts), "ids": []})
            row["cells"] = cells
            rows.append(row)
        elements.append({"kind": "table", "y": min([t.top] + [s.y0 for s in heads]),
                         "y1": t.bottom, "x0": t.x0, "x1": t.x1,
                         "column": _column_of(t.x0, t.x1),
                         "columns": cols, "rows": rows})

    # --- photo slots
    for b in boxes:
        if b.stroke == GREY_RULE and b.x1 - b.x0 > 100 and b.y1 - b.y0 > 60:
            elements.append({"kind": "photo", "y": b.y0, "y1": b.y1,
                             "x0": b.x0, "x1": b.x1,
                             "column": _column_of(b.x0, b.x1), "ids": []})

    # --- the rest of the body text: rows, checkboxes, prose, notes
    free = [s for i, s in enumerate(spans) if i not in used]
    wings = [s for s in free if s.wing]
    yn_heads = [s for s in free if s.size < 8.5 and s.bold
                and s.text in ("Yes", "No", "Yes No")]
    texts = sorted((s for s in free if not s.wing and s not in yn_heads),
                   key=lambda s: (s.y0, s.x0))
    grey_rules = [r for r in rules if r.colour == GREY_RULE and r.width <= 1.0]

    def ruled_at(x0: float, y: float) -> bool:
        return any(abs(r.y - y) < 2.2 and r.x0 - 1 <= x0 and r.x1 >= x0 + 20
                   for r in grey_rules)

    joined: list[dict] = []
    for s in texts:
        prev = next((p for p in reversed(joined) if abs(p["x0"] - s.x0) < 0.8
                     and -2.5 <= s.y0 - p["last_y1"] < 3 and p["bold"] == s.bold
                     and p["italic"] == s.italic and p["size"] == s.size), None)
        if (prev is not None and not ruled_at(prev["x0"], prev["last_y1"])
                and (prev["raw"].endswith(" ") or s.text[:1].islower()
                     or prev["italic"])):
            prev["text"] = f"{prev['text']} {s.text}"
            prev["raw"] = s.raw
            prev["x1"] = max(prev["x1"], s.x1)
            prev["y1"] = s.y1
            prev["last_y1"] = s.y1
            prev["lines"] += 1
            continue
        joined.append({"text": s.text, "raw": s.raw, "x0": s.x0, "x1": s.x1,
                       "y0": s.y0, "y1": s.y1, "last_y1": s.y1, "bold": s.bold,
                       "italic": s.italic, "size": s.size, "lines": 1})

    for s in joined:
        column = _column_of(s["x0"], s["x1"])
        ruled = ruled_at(s["x0"], s["y1"])
        check = [w for w in wings if s["y0"] - 3 <= w.cy <= s["y0"] + 13
                 and w.x0 > s["x0"]
                 and ((w.x0 < COL_SPLIT) == (s["x0"] < COL_SPLIT) or s["x1"] > COL_SPLIT)]
        el = {"y": s["y0"], "y1": s["y1"], "x0": s["x0"], "x1": s["x1"],
              "column": column, "text": s["text"], "bold": s["bold"],
              "italic": s["italic"], "size": s["size"], "lines": s["lines"], "ids": []}
        if s["italic"]:
            el["kind"] = "italic"
        elif check:
            box = min(check, key=lambda w: abs(w.cy - s["y0"]))
            wings.remove(box)
            base = MARGIN_L if s["x0"] < COL_SPLIT else 312.0
            el["kind"] = "check"
            el["style"] = ("CK" if box.x0 > COL_SPLIT + 150 and s["x0"] < COL_SPLIT
                           else "CK-1I" if s["x0"] - base > 7 else "CK1")
            el["box_x"] = box.x0
            el["yes_no"] = any(h.y1 <= box.y0 + 3 and box.y0 - h.y1 < 12
                               and abs(h.x0 - box.x0) < 8 for h in yn_heads)
            el["y"] = min(el["y"], box.y0)
        elif ruled:
            el["kind"] = "row"
            el["style"] = _indent_style(s["x0"], s["bold"], column)
        else:
            el["kind"] = "head"
            el["style"] = "TX-B" if s["bold"] else "TXR"
        elements.append(el)

    # --- attach each field ID to the element it belongs to
    tabs = [e for e in elements if e["kind"] == "table"]
    photos = [e for e in elements if e["kind"] == "photo"]
    labelled = [e for e in elements if e["kind"] in
                ("row", "check", "head", "italic", "h2", "tab", "h1", "lead")]
    for m in marks:
        mx, my = (m.x0 + m.x1) / 2, m.cy
        target = None
        for t in tabs:
            if not (t["x0"] - 2 <= mx <= t["x1"] + 2):
                continue
            for row in t["rows"]:
                if not (row["y"] - 2.5 <= my <= row["y1"] + 2.5):
                    continue
                if row.get("bar") and (row.get("text") or not any(
                        c["x0"] - 2 <= mx <= c["x1"] + 2 and not row.get("bar")
                        for c in row["cells"])):
                    target = row
                else:
                    target = next((c for c in row["cells"]
                                   if c["x0"] - 2 <= mx <= c["x1"] + 2), None)
                break
            if target is not None:
                break
        if target is None:
            target = next((p for p in photos if p["x0"] <= mx <= p["x1"]
                           and p["y"] <= my <= p["y1"]), None)
        if target is None:
            best_x = -1.0
            for e in labelled:
                top = e["y"] - (13 if e["kind"] == "check" else 4)
                if not (top <= my <= e["y1"] + 3) or e.get("x0", 0) > m.x0 + 2:
                    continue
                side_e = e.get("column", "full")
                if side_e in ("left", "right"):
                    side_m = "left" if m.x0 < COL_SPLIT else "right"
                    if side_m != side_e and e.get("x1", 0) < COL_SPLIT:
                        continue
                if e.get("x0", 0) > best_x:
                    target, best_x = e, e.get("x0", 0)
            inside = next((e for e in labelled if e["kind"] == "check" and not e.get("ids")
                           and e["y"] <= m.y0 <= e["y1"] and e.get("x0", 0) <= m.x0 < COL_SPLIT), None)
            if inside is not None:
                # a mark that starts inside a question's own box is the
                # question's, not the commentary heading's below it (20.002
                # "arm's length" went to "Non-Arm's Length Commentary")
                target = inside
        if target is None and m.x0 > 540:
            # the Yes / No column: a question's ID can sit just under its
            # line (9.007 modifications, 16.004 highest and best use)
            target = next((e for e in labelled if e["kind"] == "check" and not e.get("ids")
                           and e["y1"] - 2 <= m.y0 <= e["y1"] + 14), None)
        if target is not None:
            target.setdefault("ids", [])
            target["ids"] += m.ids
            continue
        elements.append({"kind": "slot", "y": m.y0, "y1": m.y1, "x0": m.x0,
                         "x1": m.x1,
                         "column": "full" if m.x0 < 60 else _column_of(m.x0, m.x1),
                         "ids": list(m.ids)})

    for e in elements:
        if e["kind"] == "head" and e["ids"]:
            e["kind"] = "prose"
            e["style"] = "TXC-B"
    elements.sort(key=lambda e: (round(e["y"], 0), e.get("x0", 0)))
    return {"page": number, "elements": elements}


def extract() -> dict:
    layout = pymupdf.open(LAYOUT)
    with_ids = pymupdf.open(WITH_IDS)
    pages = []
    for n in range(2, layout.page_count):
        pages.append(extract_page(layout[n], with_ids[n], n + 1))
    return {
        "source": [LAYOUT.name, WITH_IDS.name],
        "note": "Every element of the URAR as drawn in Appendix C-1, with the "
                "Report Field IDs from the annotated copy attached by position.",
        "pages": pages,
    }


def main() -> None:
    data = extract()
    OUT.write_text(json.dumps(data, indent=1), encoding="utf-8")
    ids = [i for p in data["pages"] for e in p["elements"] for i in e.get("ids", [])]
    for t in (e for p in data["pages"] for e in p["elements"] if e["kind"] == "table"):
        for r in t["rows"]:
            for c in r["cells"]:
                ids += c["ids"]
    kinds = defaultdict(int)
    for p in data["pages"]:
        for e in p["elements"]:
            kinds[e["kind"]] += 1
    print(f"{len(data['pages'])} pages, {sum(kinds.values())} elements "
          f"{dict(kinds)}, {len(set(ids))} distinct field IDs placed")


if __name__ == "__main__":
    sys.exit(main())
