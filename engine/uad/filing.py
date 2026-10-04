"""Where a photograph is filed, derived rather than remembered.

A picture's UAD ``ImageCategoryType`` decides which section of the report it
displays in, and A-1 publishes that: every category carries a Report Location
naming its section, and the section list gives that name a number.  So the
number can be looked up, and a build never has to state one.

This module exists because a build did state one.  Section 8 is Dwelling
Exterior and section 9 is Manufactured Home; a rear photograph filed under 9
came out of a Queens duplex as a manufactured-home exhibit.  The schema guard
could not catch it -- the value was valid, it was simply in the wrong place.
Deriving it removes the class of mistake rather than that one instance, and it
works the same for a driveby, a single family, a condominium or a 2-4 unit,
because the mapping comes from the standard and not from the form.
"""
from __future__ import annotations

from functools import lru_cache

from . import bind
from .report import form


@lru_cache(maxsize=1)
def _sections_by_name() -> dict[str, int]:
    return {name: number for number, name in bind.SECTIONS}


@lru_cache(maxsize=1)
def filing() -> dict[str, tuple[int, str]]:
    """``ImageCategoryType`` -> (section number, the caption A-1 prints).

    A category A-1 gives no section is placed by role rather than by section --
    the dwelling's front photograph and the grid's own pictures -- and comes
    back with section 0 for the caller to place.
    """
    numbers = _sections_by_name()
    out: dict[str, tuple[int, str]] = {}
    for category, (section_name, caption) in form.image_categories().items():
        out[category] = (numbers.get(section_name, 0), caption)
    return out


def section_of(category: str) -> int:
    """The section a picture of this category displays in, or 0 if by role."""
    return filing().get(category, (0, ""))[0]


def caption_of(category: str) -> str:
    """The caption the report prints for this category, which may be empty."""
    return filing().get(category, (0, ""))[1]


def place(category: str) -> dict:
    """Everything a media upload needs in order to file a picture correctly.

    Returned as the upload route's own arguments so a caller cannot put the
    section and the caption out of step with each other.
    """
    section, caption = filing().get(category, (0, ""))
    return {"section": section, "caption": caption}


def unknown(categories) -> list[str]:
    """Which of these categories the standard does not define.

    Worth asking before a build rather than after: a category that is not in
    A-1 will not display anywhere, and a picture that does not display is a
    picture the reader never sees.
    """
    known = filing()
    return sorted({c for c in categories if c and c not in known})
