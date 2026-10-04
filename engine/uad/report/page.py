"""The URAR page: its size, margins, columns and furniture.

Every number here was measured off the thirteen Appendix D-1 sample reports by
``engine/uad/spec/measure_geometry.py`` and ``measure_rules.py``, which write
``engine/spec/page_geometry.json`` and ``engine/spec/page_rules.json``.  Each
constant carries the evidence that fixed it, so a disagreement with the drawn
output can always be traced back to a sample rather than to an opinion.

Three findings are worth stating plainly, because each contradicts something
that looked obvious:

* The URAR is **8.5 x 14 inch** (Legal, 612 x 1008 pt) -- 296 of 296 sample
  pages.  It is not Letter.
* The running header is **absent from report page 1** in 13 of 13 samples.  The
  Summary opens with the 32 pt title instead.
* The body is a **two-column** grid of 22 picas with a 1-pica gutter, and each
  column carries its own label/value split at a fixed 145 pt.  The comparable
  grids ignore that grid entirely and run the full 45-pica measure.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

SPEC = Path(__file__).resolve().parents[2] / "spec"

PT_PER_PICA = 12.0
PT_PER_IN = 72.0


def pica(n: float) -> float:
    return n * PT_PER_PICA


# --------------------------------------------------------------------------
# Sheet
# --------------------------------------------------------------------------
PAGE_W = 612.0          # 8.5 in   -- 296/296 sample pages
PAGE_H = 1008.0         # 14 in    -- 296/296 sample pages
MARGIN_X = 36.0         # 3 picas  -- text extents run 36.0..576.0 on every page
MEASURE = PAGE_W - 2 * MARGIN_X          # 540 pt = 45 picas
CONTENT_L, CONTENT_R = MARGIN_X, PAGE_W - MARGIN_X

# --------------------------------------------------------------------------
# Running header -- suppressed on report page 1
# --------------------------------------------------------------------------
HEADER = {
    "suppressed_on_pages": (1,),     # 13/13 samples have no header on page 1
    "left_text_top": 32.6,           # MyriadPro-Bold 10 pt #231f20, x0 = 36.0
    "left_x": CONTENT_L,
    "left_size_pt": 10.0,            # x264 spans; the 8 pt in the old spec was wrong
    "left_weight": 700,
    "right_text_top": 33.9,          # MyriadPro-Regular 9 pt #231f20, x1 = 576.0
    "right_x": CONTENT_R,            # right-aligned
    "right_size_pt": 9.0,            # x445 spans
    "right_weight": 400,
    "title": "Uniform Residential Appraisal Report",   # HF.001
}

# --------------------------------------------------------------------------
# Running footer -- present on every page including the Summary
# --------------------------------------------------------------------------
# The left block is anchored at both ends: the version line sits at the top of
# the band and the provenance pair at the bottom, with a blank slot between.
# The right block stacks only the reference IDs that apply, at a 9 pt pitch.
FOOTER = {
    "band_top": 940.0,
    "left_x": CONTENT_L,
    "left_lines": (
        {"y": 945.1, "role": "FTR-L",    "field": "HF.002"},   # Appraisal Version #N
        {"y": 963.1, "role": "FTR-META", "field": "HF.003"},   # Fannie Mae | Freddie Mac
        {"y": 972.1, "role": "FTR-META", "field": "HF.004"},   # form date
    ),
    "right_x": CONTENT_R,            # values right-aligned to the measure
    "right_first_y": 945.1,
    "right_pitch": 9.0,
    "right_value_gap": 10.0,         # label right edge to value left edge
    "size_pt": 8.0,
}

# The four footer reference IDs, in the order C-1 lists them.  Only those that
# apply are drawn, and the block closes up -- the samples show Appraiser,
# Client and AMC contiguous at 945.1 / 954.1 / 963.1 with no gap where an
# Agency Case File ID would have gone.
FOOTER_IDS = (
    {"field": "HF.005", "label": "Appraiser Reference ID", "when": "always"},
    {"field": "HF.006", "label": "Agency Case File ID",
     "when": "assignment is FHA or VA"},
    {"field": "HF.007", "label": "Client Reference ID", "when": "if provided"},
    {"field": "HF.008", "label": "AMC Reference ID", "when": "if provided"},
)

# --------------------------------------------------------------------------
# Body band
# --------------------------------------------------------------------------
BODY_TOP = 62.4          # first section tab begins here on a headed page
BODY_TOP_SUMMARY = 55.9  # the 32 pt title's text top on page 1
# The footer band begins at 940 pt.  Body content is stopped a row short of it
# so that a row which measures a little taller once re-laid out on its own page
# still clears the footer rather than printing over it.
BODY_BOTTOM = 927.0

# --------------------------------------------------------------------------
# Two-column grid -- 22 picas, 1-pica gutter, 22 picas
# --------------------------------------------------------------------------
COL_W = pica(22)         # 264 pt
GUTTER = pica(1)         # 12 pt
COLUMNS = (CONTENT_L, CONTENT_L + COL_W + GUTTER)   # 36.0, 312.0

# Inside a column, measured identically in both: a label starts 4 pt in and a
# value starts 145 pt in.  Left column 40 / 181, right column 316 / 457.
LABEL_INSET = 4.0
VALUE_INSET = 145.0
INDENT_STEP = 8.0        # 40 -> 48 -> 57 and 316 -> 324 in the samples

ROW_PITCH = 13.0         # every field row and every grid row

# --------------------------------------------------------------------------
# Section tab (style code TAB) and subsection bar (H1)
# --------------------------------------------------------------------------
# The tab's right end is a rounded cap, not a square edge: the samples draw it
# with eight Bezier segments sweeping from x 137.2 to 144.0 over a 15 pt height,
# which is a 7.5 pt radius on both right corners.
TAB = {
    "x": CONTENT_L,
    "height": 14.8,
    "radius": 7.5,
    "fill": "#231f20",
    "text_x": CONTENT_L + 6.0,      # label x0 = 42.0
    "text_top_offset": 1.7,         # tab top 62.4 -> text top 64.1
    "size_pt": 9.0,
    "weight": 700,
    "colour": "#ffffff",
    "pad_right": 20.0,              # fitted width; 144 pt is the commonest
    "continued_size_pt": 7.0,       # TAB-C, italic, on a repeated tab
    "continued_baseline_drop": 2.0,  # 64.1 -> 66.1
    "continued_text": "(continued)",
}

# The subsection bar is drawn in the samples as a 15 pt *stroke* across the
# full measure, not as a filled rectangle -- which is why a fill-only survey
# found only a handful of them and measured those at 13 pt.  Counting the
# strokes finds 54 in one sample, all 15.0 pt by 540.0 pt.
BAR = {                             # subsection bar, style code H1
    "x": CONTENT_L,
    "width": MEASURE,               # 36.0 .. 576.0
    "height": 15.0,
    "fill": "#e6e7e8",              # measured; Appendix E calls it 10% black
    "text_inset": 4.0,
    "size_pt": 8.0,
    "weight": 700,
}

BAR_EMPHATIC = {**BAR, "fill": "#58595b", "colour": "#ffffff"}
BAR_TOTAL = {**BAR, "fill": "#a7a9ac"}     # shaded totals row inside a grid

RULE = {"colour": "#939598", "width": 0.5}          # x19,825 strokes
RULE_HEAVY = {"colour": "#939598", "width": 1.0}    # x1,884
RULE_INK = {"colour": "#231f20", "width": 0.5}      # x4,690

PHOTO_PLACEHOLDER = {"fill": "#e6e7e8", "caption_role": "CAPTION"}

# --------------------------------------------------------------------------
# Comparable grid -- full measure, ignores the two-column body grid
# --------------------------------------------------------------------------
# Measured column set with adjustments:
#   36.0 142.0 250.5 316.5 359.0 425.0 467.5 533.5 576.0
# and without:
#   36.0 144.0 252.0 360.0 468.0 576.0
GRID = {
    "label_x0": 36.0,
    "label_x1": 142.0,
    "subject_x0": 142.0,
    "subject_x1": 250.5,
    "comp_x0": 250.5,
    "comp_width": 108.5,
    "desc_width": 66.0,
    "adj_width": 42.5,
    "comps_per_block": 3,
    "cell_inset": 4.0,          # labels left +4, values right -4
    "row_pitch": ROW_PITCH,
    "head_size_pt": 9.0,        # "Subject Property", "Comparable #1", centred
    "cell_size_pt": 8.0,
    "subhead_fill": "#231f20",  # grid section heading, white on black
    "subhead_colour": "#ffffff",
    "not_applicable": "—",  # em dash
}
# The plain five-column variant, used by rows that carry no adjustment.
GRID_PLAIN = {"x": (36.0, 144.0, 252.0, 360.0, 468.0, 576.0), "width": 108.0}


@dataclass(frozen=True)
class Column:
    """One of the two body columns."""
    index: int
    x0: float

    @property
    def x1(self) -> float:
        return self.x0 + COL_W

    @property
    def label_x(self) -> float:
        return self.x0 + LABEL_INSET

    @property
    def value_x(self) -> float:
        return self.x0 + VALUE_INSET

    @property
    def label_width(self) -> float:
        return VALUE_INSET - LABEL_INSET

    @property
    def value_width(self) -> float:
        return COL_W - VALUE_INSET

    def indent(self, level: int) -> float:
        return self.label_x + level * INDENT_STEP


LEFT = Column(0, COLUMNS[0])
RIGHT = Column(1, COLUMNS[1])
BOTH = (LEFT, RIGHT)


def comp_columns(n: int = 3) -> list[dict]:
    """The x-extents of each comparable column, description and adjustment."""
    out = []
    for i in range(n):
        x0 = GRID["comp_x0"] + i * GRID["comp_width"]
        out.append({
            "index": i + 1,
            "x0": x0,
            "x1": x0 + GRID["comp_width"],
            "desc_x0": x0,
            "desc_x1": x0 + GRID["desc_width"],
            "adj_x0": x0 + GRID["desc_width"],
            "adj_x1": x0 + GRID["comp_width"],
        })
    return out


def measured() -> dict:
    """The raw measurement files these constants were derived from."""
    out = {}
    for name in ("page_geometry", "page_rules"):
        path = SPEC / f"{name}.json"
        if path.exists():
            out[name] = json.loads(path.read_text(encoding="utf-8"))
    return out


def verify() -> list[str]:
    """Check the constants still agree with the measurement files."""
    problems: list[str] = []
    data = measured().get("page_geometry")
    if not data:
        return ["engine/spec/page_geometry.json is missing -- run measure_geometry.py"]
    sizes = data["page_size_pt"]
    if not sizes or sizes[0]["w"] != PAGE_W or sizes[0]["h"] != PAGE_H:
        problems.append(f"page size {sizes[:1]} does not match {PAGE_W}x{PAGE_H}")
    left = data["header"]["left"][0]
    if left["size"] != HEADER["left_size_pt"]:
        problems.append(f"header left is {left['size']}pt, not {HEADER['left_size_pt']}")
    right = data["header"]["right"][0]
    if right["size"] != HEADER["right_size_pt"]:
        problems.append(f"header right is {right['size']}pt, not {HEADER['right_size_pt']}")
    without = dict(data["header"]["pages_without_header"])
    if 1 not in without:
        problems.append("page 1 is not header-free in the samples")
    tabs = data["tabs"]
    if tabs["heights"] and tabs["heights"][0][0] != TAB["height"]:
        problems.append(f"tab height {tabs['heights'][0][0]} != {TAB['height']}")
    if tabs["colours"] and tabs["colours"][0][0] != TAB["fill"]:
        problems.append(f"tab fill {tabs['colours'][0][0]} != {TAB['fill']}")
    return problems


def summary() -> str:
    lines = [
        f"page ............ {PAGE_W:.0f} x {PAGE_H:.0f} pt "
        f"({PAGE_W / PT_PER_IN:g} x {PAGE_H / PT_PER_IN:g} in)",
        f"margins ......... {MARGIN_X:.0f} pt ({MARGIN_X / PT_PER_PICA:g} picas) "
        f"each side, measure {MEASURE:.0f} pt ({MEASURE / PT_PER_PICA:g} picas)",
        f"columns ......... {COL_W:.0f} pt + {GUTTER:.0f} pt gutter + {COL_W:.0f} pt "
        f"at x {COLUMNS[0]:.0f} and {COLUMNS[1]:.0f}",
        f"label / value ... +{LABEL_INSET:g} / +{VALUE_INSET:g} pt within a column "
        f"(left {LEFT.label_x:.0f}/{LEFT.value_x:.0f}, "
        f"right {RIGHT.label_x:.0f}/{RIGHT.value_x:.0f})",
        f"row pitch ....... {ROW_PITCH:g} pt",
        f"header .......... {HEADER['left_size_pt']:g} pt bold left, "
        f"{HEADER['right_size_pt']:g} pt right, suppressed on page "
        f"{HEADER['suppressed_on_pages'][0]}",
        f"tab ............. {TAB['height']:g} pt {TAB['fill']}, label "
        f"{TAB['size_pt']:g} pt at x {TAB['text_x']:.0f}",
        f"bar ............. {BAR['height']:g} pt {BAR['fill']} full measure",
        f"grid ............ label {GRID['label_x1'] - GRID['label_x0']:.0f} pt, "
        f"subject {GRID['subject_x1'] - GRID['subject_x0']:.1f} pt, "
        f"{GRID['comps_per_block']} comps of {GRID['comp_width']:.1f} pt "
        f"({GRID['desc_width']:.0f} + {GRID['adj_width']:.1f})",
    ]
    return "\n".join(lines)


if __name__ == "__main__":
    print(summary())
    issues = verify()
    print("\nverify:", "clean" if not issues else "")
    for p in issues:
        print("   !", p)
