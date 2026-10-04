"""The canonical UAD 3.6 mapping: one authority for what the standard calls things.

Every other module used to carry a little of this knowledge of its own.
``bind`` knew a field's enumerations from the row A-1 wrote them against,
``delivery`` knew which image categories it was willing to file, ``edit`` knew
which containers are picked by a type rather than a position.  Each was right
about the case in front of it and none of them was complete, so the same class
of defect kept coming back in a new place: a party role the editor would not
offer, an image category that could not be chosen, a Required data point the
delivered XML simply did not carry.

This module is generated from A-1 (``engine/uad/spec/build_uad_map.py``) and
answers those questions once, for all 678 data points the standard defines --
including the 44 it marks "Does Not Display", which have to be delivered even
though they never print.

    >>> options("PartyRoleType", slot="2.011")     # the client's second role
    ['Attorney', 'Investor', 'Lender', 'ManagementCompany']
    >>> len(options("PartyRoleType"))              # every role A-1 defines
    13

The distinction matters.  A slot is a restriction the specification puts on a
particular place in the report -- the Water Features row offers water
amenities and nothing else -- so a caller that knows its slot must get the
narrow list.  A caller that does not know, or is writing a block the report
never displays, must get the complete one; giving it the first slot's list is
how the editor came to offer eight of thirteen party roles.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

SPEC = Path(__file__).resolve().parent.parent / "spec"

# A-1 states conditionality per property role, in these words.
REQUIRED = "R"
CONDITIONAL = "CR"

ROLES = ("Subject Property", "Land Comparable", "Property Analyzed Not Used",
         "Rental Comparable", "Gross Rent Multiplier Comparable", "Sales Comparable")


@lru_cache(maxsize=1)
def load() -> dict:
    path = SPEC / "uad_map.json"
    if not path.exists():                       # generated; build it on demand
        from .spec import build_uad_map
        build_uad_map.main()
    return json.loads(path.read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _points() -> dict:
    return load()["data_points"]


def point(mismo: str) -> dict:
    """A-1's record for one MISMO data point, or {} if the standard has none."""
    return _points().get(mismo, {})


def known(mismo: str) -> bool:
    return mismo in _points()


def names() -> list[str]:
    return list(_points())


def options(mismo: str, slot: str = "") -> list[str]:
    """The values this data point may hold, narrowed to a slot when given.

    ``slot`` is a Report Field ID.  When A-1 wrote an enumeration list against
    that location, that list is the answer -- it is the specification
    restricting the choice on purpose.  Otherwise the answer is every value
    A-1 defines for the data point.
    """
    entry = point(mismo)
    if not entry:
        return []
    if slot:
        narrowed = entry.get("slots", {}).get(slot)
        if narrowed:
            return list(narrowed)
    return list(entry.get("values", ()))


def label(mismo: str, value: str) -> str:
    """What the report prints for a stored value ('SettledSale' -> 'Settled Sale').

    A-1 keeps this text out of the XML on purpose; it is display only.
    """
    return load().get("display_text", {}).get(mismo, {}).get(value, "")


def labels(mismo: str) -> dict:
    return dict(load().get("display_text", {}).get(mismo, {}))


def placements(mismo: str) -> list[dict]:
    """Every container A-1 places this data point in, in the sheet's own order."""
    return list(point(mismo).get("placements", ()))


def containers(mismo: str) -> list[str]:
    seen: list[str] = []
    for place in placements(mismo):
        if place["container"] and place["container"] not in seen:
            seen.append(place["container"])
    return seen


def displays(mismo: str) -> bool:
    """Does this data point appear anywhere on the printed report?"""
    return bool(point(mismo).get("displays"))


def delivery_only() -> list[str]:
    """Data points A-1 requires in the file but never prints.

    The Scope of Work's approach indicators, the coordinates behind the map,
    the software that wrote the file.  They have no field on the page, so
    nothing in a display-driven model ever created them.
    """
    return sorted(n for n, e in _points().items() if not e.get("displays"))


def conditionality(mismo: str, role: str = "Subject Property") -> str:
    """'R', 'CR' or '' for this data point against one property role."""
    return point(mismo).get("conditionality", {}).get(role, "")


def is_required(mismo: str, role: str = "Subject Property") -> bool:
    return conditionality(mismo, role) == REQUIRED


def format_of(mismo: str) -> tuple[str, str]:
    """(format type, format details) -- 'Amount'/'+9.0', 'Date'/'YYYY-MM-DD'."""
    entry = point(mismo)
    return entry.get("format_type", ""), entry.get("format_details", "")


def unit_values(mismo: str) -> list[str]:
    """The unit-of-measure values the data point's attribute may carry."""
    return list(point(mismo).get("attribute_values", ()))


def attribute(mismo: str) -> str:
    return point(mismo).get("attribute", "")


# ------------------------------------------------------------------ images
# A-1 gives every ImageCategoryType a Report Location, which is the section the
# picture belongs to.  Nothing used it: an imported file's images were filed
# under a three-entry table and everything else became "other" with no section
# at all, so thirty-four of the forty-two pictures in a real report had no
# exhibit slot to appear in.
@lru_cache(maxsize=1)
def _image_sections() -> dict[str, tuple[str, str]]:
    from .report import form                      # late: form imports this module

    return form.image_categories()


def image_section_name(category: str) -> str:
    """The report section an image of this category belongs to ('Site')."""
    return _image_sections().get(category, ("", ""))[0]


def image_caption(category: str) -> str:
    """The caption the report prints for this category, where A-1 gives one."""
    return _image_sections().get(category, ("", ""))[1]


@lru_cache(maxsize=1)
def _section_numbers() -> dict[str, int]:
    from . import bind

    return {name: number for number, name in bind.SECTIONS}


def image_section(category: str) -> int:
    """The section number an image of this category belongs to, or 0.

    0 means A-1 does not tie the category to one section -- a supplemental
    exhibit, say -- not that the category is unknown.
    """
    return _section_numbers().get(image_section_name(category), 0)
