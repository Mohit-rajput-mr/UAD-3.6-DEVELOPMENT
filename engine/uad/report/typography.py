"""The URAR's type and colour, derived from the official sample PDFs.

Every value here was measured out of the Appendix D-1 samples rather than read
off a screenshot: ``engine/spec/typography.json`` lists each (face, size,
colour) combination that actually occurs in the twelve GSE reports, with the
text it was found on.  This module turns those measurements into named roles
and CSS.

Two findings from that measurement drive most of what follows.  The report body
is not black -- it is ``#231f20`` -- and the form is set entirely in Myriad Pro,
with Calibri appearing only in the specification wrapper the GSEs bind around
each sample.  ``SF5A_Appraisal`` is the same report as ``SF5`` set in Calibri,
which is what the Style Guide means by naming a substitute face.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from . import fonts

SPEC = Path(__file__).resolve().parents[2] / "spec" / "typography.json"

# Measured from the samples.  The body colour is a rich black, not #000.
INK = "#231f20"          # every field label
# The GSEs set values in the same near-black as the labels.  Commercial UAD
# software conventionally sets the *data* in blue so an appraiser can see at a
# glance what was entered versus what the form prints; this build follows that
# convention.  Set VALUE_INK to INK to return to the published sample exactly.
VALUE_INK = "#1f4e79"
PROVENANCE = "#77787b"   # "Fannie Mae | Freddie Mac" and the form date
MUTED = "#939598"        # italic placeholder captions under absent photos
PAPER = "#ffffff"
TAB_INK = "#ffffff"      # section-tab text, reversed out of black

# Appendix E's greys, quoted there as percentages of black.
BLACK_10 = "#e6e7e8"     # subsection bar, measured (E calls it 10% black)
BLACK_40 = "#939598"     # half-point rules, x19,825 strokes in the samples
BLACK_60 = "#58595b"     # emphatic subsection bar, white text
BLACK_35 = "#a7a9ac"     # shaded totals row inside a grid


@dataclass(frozen=True)
class Role:
    """One style code from Appendix E, resolved to concrete type."""
    code: str
    size_pt: float
    weight: int
    italic: bool
    colour: str
    note: str = ""

    @property
    def css(self) -> str:
        style = "italic" if self.italic else "normal"
        return (f"font-family:'{fonts.FAMILY}',{fonts.FALLBACK};"
                f"font-size:{self.size_pt}pt;font-weight:{self.weight};"
                f"font-style:{style};color:{self.colour}")


# Each role cites the sample evidence for its size and colour.  The counts are
# the number of spans measured across the twelve samples.
ROLES: dict[str, Role] = {
    "TITLE":     Role("TITLE", 32.0, 400, False, INK,
                      "cover line, MyriadPro-Regular 32pt x12"),
    "TITLE-ADD": Role("TITLE-ADD", 12.0, 700, False, INK,
                      "Summary address; sample sets MyriadPro-Black, tracked Bold here"),
    "SUM-HD":    Role("SUM-HD", 14.0, 700, False, INK,
                      "the word SUMMARY; sample sets MyriadPro-Black, tracked Bold here"),
    "TAB":       Role("TAB", 9.0, 700, False, TAB_INK,
                      "section tab, white on black, x407"),
    "TAB-C":     Role("TAB-C", 7.0, 700, True, TAB_INK,
                      "'(continued)' on a repeated tab, x163"),
    "H1":        Role("H1", 8.0, 700, False, INK, "subsection bar"),
    "H2":        Role("H2", 10.0, 700, False, INK,
                      "in-section heading such as Property Description, x957"),
    "LABEL":     Role("LABEL", 9.0, 700, False, INK, "field label, x4043"),
    "VALUE":     Role("VALUE", 9.0, 400, False, VALUE_INK, "field value, x5120"),
    "TX-B":      Role("TX-B", 9.0, 700, False, INK, "bold running text"),
    "TXR":       Role("TXR", 9.0, 400, False, INK, "running text"),
    "TXR-I":     Role("TXR-I", 9.0, 400, True, INK, "italic note, x118"),
    "TXR-B":     Role("TXR-B", 9.0, 700, False, INK, "bold label in a table"),
    "GRID":      Role("GRID", 8.0, 400, False, VALUE_INK,
                      "comparable-grid cell, the most used style at x9080"),
    "GRID-B":    Role("GRID-B", 8.0, 700, False, INK, "grid row label, x1968"),
    "GRID-HD":   Role("GRID-HD", 8.0, 700, False, TAB_INK,
                      "grid column head, white on black, x263"),
    "CAPTION":   Role("CAPTION", 9.0, 400, True, MUTED,
                      "placeholder caption under a missing photo, x508"),
    "FTR-L":     Role("FTR-L", 8.0, 700, False, INK,
                      "footer Appraisal Version line, x276"),
    "FTR-R":     Role("FTR-R", 8.0, 700, False, INK,
                      "footer reference-ID label, x704"),
    "FTR-V":     Role("FTR-V", 8.0, 400, False, INK,
                      "footer reference-ID value, right-aligned to the measure"),
    "FTR-META":  Role("FTR-META", 8.0, 700, False, PROVENANCE,
                      "'Fannie Mae | Freddie Mac' and the form date, x552"),
    "HDR-L":     Role("HDR-L", 10.0, 700, False, INK,
                      "running header title, x264 -- measured 10 pt, not 8"),
    "HDR-R":     Role("HDR-R", 9.0, 400, False, INK,
                      "running header 'Page N of M', x445 -- measured 9 pt"),
}


def measured() -> list[dict]:
    """The raw (face, size, colour) combinations counted in the samples."""
    return json.loads(SPEC.read_text(encoding="utf-8"))["combinations"]


def stylesheet(embed_fonts: bool = True) -> str:
    """The CSS the report is drawn with, roles and all."""
    lines = [fonts.face_css(embed=embed_fonts), ""]
    for name, role in ROLES.items():
        selector = f".s-{name.lower().replace('-', '_')}"
        lines.append(f"{selector}{{{role.css}}}  /* {role.note} */")

    # MyriadPro-Black is not part of the Acrobat font set, so the two lines it
    # sets are tracked out to the width measured in the sample instead.
    for code, sub in fonts.BLACK_SUBSTITUTE.items():
        selector = f".s-{code.lower().replace('-', '_')}"
        lines.append(f"{selector}{{letter-spacing:{sub.letter_spacing_pt / sub.size_pt:.4f}em}}"
                     f"  /* stands in for MyriadPro-Black; target {sub.target_pt}pt */")
    return "\n".join(lines)


def report() -> str:
    """A short account of where these numbers came from, for the record."""
    rows = measured()
    myriad = [c for c in rows if c["face"].startswith("MyriadPro")]
    calibri = [c for c in rows if c["face"].startswith("Calibri")]
    out = [f"{len(rows)} (face, size, colour) combinations measured across the "
           f"official samples",
           f"   Myriad Pro .. {len(myriad)} combinations, "
           f"{sum(c['occurrences'] for c in myriad):,} spans",
           f"   Calibri ..... {len(calibri)} combinations, "
           f"{sum(c['occurrences'] for c in calibri):,} spans "
           f"(the Calibri-set SF5A sample and the spec wrapper)",
           f"   colours ..... {sorted({c['colour'] for c in rows})}"]
    return "\n".join(out)
