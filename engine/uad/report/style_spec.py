"""Typographic specification, transcribed from Appendix E: Report Style Guide v1.5.

Every value here has a citation to the page it came from, so the renderer can
be audited against the source rather than trusted.  Measurements are given in
the Style Guide's own units (points and picas) and converted once, here.

  1 point = 1/72 inch, 1 pica = 12 points = 1/6 inch.
  "9/13" means 9pt type on 13pt line spacing.
"""
from __future__ import annotations

PT = 1 / 72          # inch
PICA = 1 / 6         # inch


def picas(p: float, points: float = 0) -> float:
    """Convert the guide's `NpM` notation to inches."""
    return p * PICA + points * PT


# ---------------------------------------------------------------- page (p16)
PAGE_WIDTH_IN = 8.5
PAGE_HEIGHT_IN = 14.0          # Legal
MARGIN_TOP_IN = 0.5
MARGIN_LEFT_IN = 0.5
MARGIN_RIGHT_IN = 0.5
MARGIN_BOTTOM_IN = 0.5         # guide allows 0.375-0.5

COLUMN_WIDTH_PICAS = 22        # 3.66in
GUTTER_PICAS = 1               # 0.17in
FULL_WIDTH_PICAS = 45          # 7.5in

FONT_STACK = '"Myriad Pro", "Myriad Pro Regular", Calibri, "Segoe UI", sans-serif'

# --------------------------------------------------------------- rules (p14)
# The guide specifies rule weights in points and tints as percentages of black.
RULE_HAIRLINE = 0.5            # 1/2 point
RULE_THIN = 1.0
RULE_MEDIUM = 2.0
RULE_H1_BAR = 15.0             # the grey H1 bar is a 15pt rule

BLACK = "#000000"
BLACK_50 = "#808080"           # 50% black
BLACK_40 = "#999999"           # 40% black - TB_sub-H1 fill
BLACK_80 = "#333333"           # 80% black - TB-SCA_sub-H1 fill
BLACK_10 = "#e6e6e6"           # 10% black - H1 bar, TB-SCA_H2, grayed cells


# ------------------------------------------------------- header/footer (p16-17)
HEADER = {
    "rule_weight_pt": RULE_HAIRLINE,
    "rule_color": BLACK_50,
    "rule_width_picas": FULL_WIDTH_PICAS,
    "rule_offset_pt": 6,           # rule sits 6pt below the text
    "left_text": "Uniform Residential Appraisal Report",
    "left_size_pt": 9,
    "left_weight": "bold",
    "right_format": "Page {page} of {total}",
    "right_size_pt": 9,
    "right_weight": "normal",
    "suppress_on_summary": True,   # header displays on all pages EXCEPT Summary
}

FOOTER = {
    "rule_weight_pt": RULE_MEDIUM,
    "rule_color": BLACK,
    "rule_width_picas": FULL_WIDTH_PICAS,
    "space_below_rule_pt": 6,
    "left_line1": "Appraisal Version #",
    "left_line1_size_pt": 8,
    "left_line1_weight": "bold",
    "left_line2": "Fannie Mae | Freddie Mac",
    "left_line2_color": BLACK_50,
    "left_line2_size_pt": 8,
    "right_size_pt": 8,
    "baseline_on_bottom_margin": True,
}


# ------------------------------------------------------- section headings (p19-21)
STYLES: dict[str, dict] = {
    # code: {size, leading, weight, style, transform, rule..., page}
    "TITLE": {
        "size_pt": 32, "weight": "normal", "align": "left",
        "space_above_picas": (2, 2), "space_below_pt": 6, "page": 19,
    },
    "TITLE-ADD": {
        "size_pt": 12, "leading_pt": 13, "weight": "900", "transform": "uppercase",
        "space_below_picas": (3, 0), "page": 19,
    },
    "SUM-HD": {
        "size_pt": 14, "weight": "900", "transform": "uppercase",
        "rule_weight_pt": RULE_MEDIUM, "rule_width_picas": FULL_WIDTH_PICAS,
        "rule_offset_picas": (0, 5), "page": 19,
    },
    "TAB": {
        "size_pt": 9, "leading_pt": 13, "weight": "bold", "color": "#ffffff",
        "fill": BLACK, "indent_picas": (0, 4),
        "tab_width_picas": 12, "tab_height_picas": (1, 3),
        "corner_radius_picas": 1,
        "rule_weight_pt": RULE_HAIRLINE, "rule_width_picas": FULL_WIDTH_PICAS,
        "rule_offset_picas": (0, 3),
        "space_above_picas": (1, 7.5), "page": 19,
    },
    "TAB-C": {
        "inherits": "TAB", "suffix": " (continued)", "suffix_size_pt": 7,
        "suffix_style": "italic", "page": 20,
    },
    "H1": {
        "size_pt": 10, "leading_pt": 13, "weight": "bold",
        "fill": BLACK_10, "bar_height_pt": RULE_H1_BAR,
        "indent_picas": (0, 4), "space_above_picas": (1, 3), "page": 20,
    },
    "H1-TX": {
        "size_pt": 9, "leading_pt": 11, "style": "italic",
        "align": "right", "width_picas": FULL_WIDTH_PICAS, "page": 20,
    },
    "H2": {
        "size_pt": 9, "leading_pt": 13, "weight": "bold", "indent_picas": (0, 4),
        "rule_weight_pt": RULE_THIN, "rule_width_picas": FULL_WIDTH_PICAS,
        "rule_offset_picas": (0, 4), "space_above_picas": (1, 3), "page": 20,
    },
    "H2-1": {
        "inherits": "H2", "rule_width_picas": COLUMN_WIDTH_PICAS, "page": 21,
    },
    "TX-B": {
        "size_pt": 9, "leading_pt": 13, "weight": "bold",
        "width_picas": COLUMN_WIDTH_PICAS, "indent_pt": 4, "page": 21,
    },

    # ------------------------------------------------- main report text (p22-25)
    "TXR-B": {
        "size_pt": 9, "leading_pt": 13, "weight": "bold", "indent_pt": 4,
        "tab_picas": 11, "rule_weight_pt": RULE_HAIRLINE, "rule_color": BLACK_50,
        "rule_width_picas": COLUMN_WIDTH_PICAS, "rule_offset_picas": (0, 2),
        "page": 22,
    },
    "TXR": {
        "size_pt": 9, "leading_pt": 13, "weight": "normal", "indent_pt": 4,
        "tab_picas": 11, "rule_weight_pt": RULE_HAIRLINE, "rule_color": BLACK_50,
        "rule_width_picas": COLUMN_WIDTH_PICAS, "rule_offset_picas": (0, 2),
        "page": 22,
    },
    "TXR-I": {"inherits": "TXR", "indent_picas": (0, 12), "page": 22},
    "TXR-II": {"inherits": "TXR", "indent_pt": 21, "page": 23},
    "TX-BI": {
        "size_pt": 9, "leading_pt": 13, "weight": "bold", "style": "italic",
        "indent_pt": 4, "page": 23,
    },
    "TAB-TX": {
        "size_pt": 9, "leading_pt": 13, "style": "italic",
        "width_picas": FULL_WIDTH_PICAS, "tab_picas": (12, 4), "page": 23,
    },
    "TXC": {
        "size_pt": 9, "leading_pt": 11, "width_picas": FULL_WIDTH_PICAS,
        "space_above_pt": 5.5, "indent_pt": 4, "case": "sentence", "page": 23,
    },
    "TXC-B": {"inherits": "TXC", "bold_intro": True, "page": 24},
    "TXC-B1": {
        "inherits": "TXC", "bold_intro": True,
        "width_picas": COLUMN_WIDTH_PICAS, "page": 24,
    },
    "TXC-I": {"inherits": "TXC", "style": "italic", "page": 24},
    "TXC-I1": {
        "inherits": "TXC", "style": "italic",
        "width_picas": COLUMN_WIDTH_PICAS, "page": 24,
    },
    "TXC-NP": {"inherits": "TXC", "numbered": True, "page": 25},
    "TXC-NPI-B": {
        "inherits": "TXC", "numbered": True, "bold_intro": True,
        "indent_picas": (1, 6), "page": 25,
    },
    "FN": {
        "size_pt": 8, "leading_pt": 10, "width_picas": FULL_WIDTH_PICAS,
        "space_above_pt": 5, "page": 25,
    },
    "SIG": {
        "size_pt": 9, "leading_pt": 13, "width_picas": COLUMN_WIDTH_PICAS,
        "indent_pt": 4, "tab_picas": 11,
        "rule_weight_pt": RULE_HAIRLINE, "rule_color": BLACK,
        "rule_width_picas": COLUMN_WIDTH_PICAS, "rule_offset_picas": (0, 2),
        "page": 25,
    },
    "SIG-B": {
        "size_pt": 9, "leading_pt": 13, "width_picas": COLUMN_WIDTH_PICAS,
        "indent_pt": 4, "tab_picas": 11, "page": 26,
    },

    # ------------------------------------------------------ checkboxes (p26-28)
    "Y/N": {
        "size_pt": 8, "leading_pt": 9, "weight": "bold",
        "width_picas": COLUMN_WIDTH_PICAS, "indent_picas": (19, 6), "page": 26,
    },
    "CK": {
        "size_pt": 9, "leading_pt": 11, "weight": "bold",
        "width_picas": FULL_WIDTH_PICAS, "indent_pt": 4,
        "box_size_pt": 12, "box_gap_pt": 7, "page": 26,
    },
    "CK1": {
        "inherits": "CK", "width_picas": (19, 3),
        "align_boxes_right_at_picas": COLUMN_WIDTH_PICAS, "page": 26,
    },
    "CK-H2": {"inherits": "CK", "with_h2": True, "page": 27},
    "CK-TAB": {"inherits": "CK", "on_tab": True, "gap_picas": (1, 6), "page": 27},
    "CK-1I": {
        "size_pt": 9, "leading_pt": 11, "weight": "normal",
        "width_picas": COLUMN_WIDTH_PICAS, "indent_picas": (1, 0), "page": 28,
    },

    # ---------------------------------------------------- table elements (p29-31)
    "TB": {
        "size_pt": 8, "leading_pt": 9, "align": "left",
        "inset_top_pt": 3, "inset_bottom_pt": 3.2, "inset_side_pt": 4,
        "rule_weight_pt": RULE_HAIRLINE, "rule_color": BLACK_50,
        "case": "initial", "page": 29,
    },
    "TB-I": {"inherits": "TB", "indent_pt": 8, "page": 29},
    "TB-B": {"inherits": "TB", "weight": "bold", "page": 29},
    "TCH": {
        "size_pt": 9, "leading_pt": 10, "weight": "bold", "indent_pt": 4,
        "rule_below_only": True, "rule_weight_pt": RULE_HAIRLINE,
        "rule_color": BLACK_50, "rule_offset_pt": 4, "page": 29,
    },
    "TB_sub-H1": {
        "size_pt": 8, "leading_pt": 9, "weight": "bold",
        "color": "#ffffff", "fill": BLACK_40, "indent_pt": 4, "page": 30,
    },
    "TB_sub-H1-R": {
        "inherits": "TB_sub-H1", "align": "right", "page": 30,
    },
    "TB-SCA_sub-H1": {
        "size_pt": 8, "leading_pt": 9, "weight": "bold",
        "color": "#ffffff", "fill": BLACK_80, "indent_pt": 4, "page": 30,
    },
    "TB-SCA_sub-H1-ADJ": {
        "inherits": "TB-SCA_sub-H1", "adjustment_cells_show_dollar": True,
        "cells_divided_by_white_rules": True, "page": 31,
    },
    "TB-SCA_H2": {
        "size_pt": 8, "leading_pt": 9, "weight": "bold",
        "color": BLACK, "fill": BLACK_10, "indent_pt": 4, "page": 31,
    },
    "CAP": {
        "size_pt": 9, "leading_pt": 10, "weight": "bold",
        "width_picas": (21, 6), "indent_pt": 4, "page": 31,
    },
}


# ------------------------------------------- table general rules (p28)
TABLE_RULES = {
    "break_only_before_major_heading": True,
    "column_heads_repeat_on_break": True,
    "all_rules_weight_pt": RULE_HAIRLINE,
    "all_rules_color": BLACK_50,
    "rules_top_bottom_and_interior_verticals_only": True,
    "outermost_cells_no_vertical_rule": True,
    "empty_cell_when_no_content": True,
}


# --------------------------- sales comparison grid cell types (p61-62)
# Five cell types make up the body of the grid.
SCA_CELL_TYPES = {
    1: {"width_picas": (9, 0), "fill": BLACK_10, "content": False,
        "note": "Subject column, rows that never apply"},
    2: {"width_picas": (9, 0), "fill": None, "content": True},
    3: {"width_picas": (5, 3), "fill": None, "content": True},
    4: {"width_picas": (3, 6), "fill": None, "content": "adjustment",
        "note": "adjustment cell on an adjustable row"},
    5: {"width_picas": (3, 6), "fill": BLACK_10, "content": False,
        "note": "adjustment cell on a non-adjustable row"},
}

# Rows where the Subject column is grayed out with no content (p61).
SCA_SUBJECT_GRAYED_ROWS = {
    "Data Source", "Proximity to Subject", "Sale Price", "Transfer Terms",
    "Financing Type", "Sale Date", "Sale to List Price Ratio",
    "Same Builder as Subject", "Net Adjustment Total", "Adjusted Price Per Unit",
    "Adjusted Price Per Bedroom", "Price Per Gross Building Finished Area",
    "Price Per Finished Area Above Grade", "Adjusted Price", "Comparable Weight",
}

# Rows where the comparable's adjustment cell is grayed out (p62).
SCA_COMPARABLE_GRAYED_ADJUSTMENT_ROWS = {
    "Days on Market", "Annual Ground Rent", "Rights Not Included",
    "Same Builder as Subject",
}

# Line types within the grid (p62).
SCA_LINES = {
    "A": {"weight_pt": RULE_HAIRLINE, "color": BLACK,
          "note": "vertical between Subject and each Comparable"},
    "B": {"weight_pt": RULE_HAIRLINE, "color": BLACK_50,
          "note": "vertical between a comparable's value and its adjustment"},
    "C": {"weight_pt": RULE_HAIRLINE, "color": BLACK_50,
          "note": "horizontal rules throughout"},
}

# The grid prints three comparables per block; beyond that the label and
# subject columns repeat on a following block (p62).
SCA_COMPARABLES_PER_BLOCK = 3
SCA_PHOTO_HEIGHT_PICAS = 7

# Which band style each group heading uses (p63-65).
SCA_GROUP_BAND_STYLE = {
    "General Information": "TB-SCA_sub-H1",
    "Project Information": "TB-SCA_sub-H1-ADJ",
    "Site": "TB-SCA_sub-H1",
    "Water Frontage with Private Access": "TB-SCA_sub-H1-ADJ",
    "Dwelling(s)": "TB-SCA_sub-H1",
    "Energy Efficient and Green Features": "TB-SCA_sub-H1-ADJ",
    "Unit(s)": "TB-SCA_sub-H1",
    "Quality and Condition": "TB-SCA_sub-H1",
    "Exterior Quality and Condition": "TB-SCA_H2",
    "Interior Quality and Condition": "TB-SCA_H2",
    "ADU Interior Quality and Condition": "TB-SCA_H2",
    "Overall Quality and Condition": "TB-SCA_sub-H1",
    "Property Amenities": "TB-SCA_sub-H1",
    "Vehicle Storage": "TB-SCA_sub-H1-ADJ",
    "Outbuilding": "TB-SCA_sub-H1",
    "Summary": "TB-SCA_sub-H1",
    "Indicated Value by Sales Comparison Approach": "TB-SCA_H2",
}


# ------------------------------------------------------------- images (p31)
IMAGES = {
    "photos_per_page_max": 8,
    "graphs_per_page": (2, 3),
    "graph_frame_picas": (45, 20),
    "full_page_frame_picas": (45, 48),
    "frame_inset_pt": 6,
}


# --------------------------------------------- the 29 URAR sections (p33, TOC)
# Order is the order they print in the report.
URAR_SECTIONS = [
    "Summary",
    "Assignment Information",
    "Subject Property",
    "Site",
    "Disaster Mitigation",
    "Energy Efficient and Green Features",
    "Sketch",
    "Dwelling Exterior",
    "Manufactured Home",
    "Unit Interior",
    "Functional Obsolescence",
    "Outbuilding",
    "Vehicle Storage",
    "Subject Property Amenities",
    "Overall Quality and Condition",
    "Highest and Best Use",
    "Market",
    "Project Information",
    "Subject Listing Information",
    "Sales Contract",
    "Prior Sale and Transfer History",
    "Sales Comparison Approach",
    "Rental Information",
    "Income Approach",
    "Cost Approach",
    "Reconciliation",
    "Revision History",
    "Supplemental Information",
    "Certifications and Scope of Work",
]

# Sections the guide says begin on a new page.
SECTIONS_STARTING_NEW_PAGE = {
    "Assignment Information",
    "Sales Comparison Approach",
    "Supplemental Information",
}


def resolve(code: str) -> dict:
    """A style with its inherited values folded in."""
    style = dict(STYLES[code])
    parent = style.pop("inherits", None)
    if parent:
        base = resolve(parent)
        base.update(style)
        return base
    return style
