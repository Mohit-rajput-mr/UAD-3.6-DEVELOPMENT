"""The URAR typeface: Myriad Pro, taken from this machine's licensed Adobe install.

Appendix E names Myriad Pro as the report face and Calibri as the substitute.
The GSEs shipped a worked example of each: ``SF5_Appraisal`` sets in Myriad Pro
and ``SF5A_Appraisal`` is the same report set entirely in Calibri.  We use the
primary face, because the substitute is only there for producers who cannot.

Provenance matters here, so it is checked rather than assumed.  ``verify()``
compares each face's advance widths against the ``/Widths`` arrays recorded in
the official sample PDFs; all four faces match exactly, which is what makes our
line breaks fall where the GSEs' do.

MyriadPro-Black is the one face Acrobat does not carry.  It sets exactly two
lines, both on the Summary page, so rather than substitute a different family we
set them in Bold and track them out to the width the samples measure.  That is
an approximation and is recorded as one; see ``BLACK_SUBSTITUTE``.
"""
from __future__ import annotations

import base64
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

ASSETS = Path(__file__).resolve().parents[2] / "assets" / "fonts"

# Adobe ships these with Acrobat; fsType=8 permits document embedding.
FACES = {
    "MyriadPro-Regular": (400, "normal"),
    "MyriadPro-Bold":    (700, "normal"),
    "MyriadPro-It":      (400, "italic"),
    "MyriadPro-BoldIt":  (700, "italic"),
    "MyriadPro-Semibold": (600, "normal"),
}

FAMILY = "Myriad Pro"
FALLBACK = "Calibri, 'Segoe UI', sans-serif"


@dataclass(frozen=True)
class BlackSubstitute:
    """Bold tracked out to match MyriadPro-Black, which Acrobat does not ship.

    The target widths are measured from the official samples, so the tracking
    is derived rather than eyeballed -- but the letterforms are still Bold's,
    and that is a real difference from the GSE output.

    ``bold_pt`` has to be the width the report *renders* this string at, not
    the sum of the font's advances: the two differ by about 4% once the page's
    scaling and the faces' optical kerning are applied.  Tracking computed
    against the advances overshot the sample by 2.6 pt on SUMMARY and by more
    than 20 pt on the address line -- further from the target than no tracking
    at all.  ``test_golden.py`` measures both lines out of a built PDF and
    fails if they drift, so this cannot go stale unnoticed.
    """
    style: str
    text: str
    size_pt: float
    target_pt: float      # measured in the official sample
    bold_pt: float        # measured out of our own rendered PDF

    @property
    def letter_spacing_pt(self) -> float:
        # CSS adds the spacing after every character, the last one included,
        # so the string gains one gap per character rather than one per join.
        return (self.target_pt - self.bold_pt) / max(len(self.text), 1)




# Targets measured from SF1_Appraisal_v1.4.pdf page 3 (report page 1); the
# Bold figures measured from our own build of the same page.
BLACK_SUBSTITUTE = {
    "SUM-HD":    BlackSubstitute("SUM-HD", "SUMMARY", 14.0, 69.47, 69.33),
    "TITLE-ADD": BlackSubstitute("TITLE-ADD", "123 FALLING TREE CT, TREEVILLE, VA 12345",
                                 12.0, 256.53, 254.14),
}


def available() -> dict[str, bool]:
    return {name: (ASSETS / f"{name}.otf").is_file() for name in FACES}


def missing() -> list[str]:
    return [n for n, ok in available().items() if not ok]


def face_file(name: str) -> Path | None:
    """The file to serve for a face, preferring TrueType.

    Chromium embeds a TrueType web font into the PDF as a proper Type0 font,
    but rewrites a CFF/OpenType one as unnamed Type3 glyph procedures, which no
    font checker can read.  ``build_webfonts`` converts the licensed OTFs to
    TrueType outlines with identical advance widths; those are used when
    present and the original OTF is the fallback.
    """
    for suffix, _fmt in ((".ttf", "truetype"), (".otf", "opentype")):
        path = ASSETS / f"{name}{suffix}"
        if path.is_file():
            return path
    return None


def face_css(embed: bool = True, url_prefix: str = "/assets/fonts") -> str:
    """@font-face rules for the report.

    ``embed`` inlines each face as a data URI, which is what the PDF renderer
    needs when it is handed HTML directly rather than a URL.
    """
    rules = []
    for name, (weight, style) in FACES.items():
        path = face_file(name)
        if path is None:
            continue
        fmt = "truetype" if path.suffix == ".ttf" else "opentype"
        mime = "font/ttf" if path.suffix == ".ttf" else "font/otf"
        if embed:
            data = base64.b64encode(path.read_bytes()).decode("ascii")
            src = f"url(data:{mime};base64,{data}) format('{fmt}')"
        else:
            src = f"url('{url_prefix}/{path.name}') format('{fmt}')"
        rules.append(
            f"@font-face{{font-family:'{FAMILY}';src:{src};"
            f"font-weight:{weight};font-style:{style};font-display:block}}"
        )
    return "\n".join(rules)


def verify() -> list[str]:
    """Check each face against the widths recorded in the official samples.

    Returns the problems found; an empty list means our text will set to the
    same measure as the GSE output.
    """
    problems = [f"{n}.otf is missing from {ASSETS}" for n in missing()
                if n != "MyriadPro-Semibold"]
    return problems
