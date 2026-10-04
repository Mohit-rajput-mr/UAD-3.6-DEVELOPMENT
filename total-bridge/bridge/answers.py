"""What to put in each field TOTAL reports, for the case that is loaded.

Nothing here is measured.  A value is either the subject's own answer carried
across to a comparable of the same class, or the conventional answer for a
property of this kind, and the difference matters: the first cancels in the
grid, the second is an assumption and is listed back to the appraiser at the
end of a run.

**A case's own facts live in a Profile, and a profile has to be chosen.**
There is no default set of property facts, because the last one written here
was a 1925 two-family -- Colonial, a driveway, R3-2 -- and those answers are
false about the next property.  With no profile selected, a rule that would
assert a fact about the property answers nothing and the field is reported as
open, which is the right failure: an unanswered field is a question, a wrong
answer is a defect in a signed report.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field as _field

from .close import Answer


@dataclass(frozen=True)
class Literal:
    """A value that is true of any report, not a fact about this property."""
    value: str


@dataclass(frozen=True)
class Profile:
    """One case's own answers, and the rates its adjustments are computed at.

    ``subject`` is keyed by the short names the rules below use; ``rates`` is
    the rate card, in currency per unit of difference; ``source`` says where
    the appraiser got them, so a run can be read back to its evidence.
    """
    name: str
    source: str
    subject: dict = _field(default_factory=dict)
    rates: dict = _field(default_factory=dict)


#: Nothing chosen.  Property facts are left unanswered rather than guessed.
UNSET = Profile("unset", "no case profile selected")

#: 129-35 131st St, South Ozone Park -- the exterior-only two-family.
OZONE = Profile(
    name="ozone-two-family",
    source="the order packet, the ATTOM record and the subject's own "
           "photographs; rate card as instructed by the owner",
    subject={
        "style": "Colonial",
        "cooling": "Individual",
        "heating_detail": "Natural Gas",
        "zoning": "Legal",
        "levels": "1",
        "floors_condition": "Not Updated",
        "vehicle_storage": "Driveway",
        "occupancy": "Tenant",
        "area_source": "Assessor Record",
        "utility_impact": "Neutral",
    },
    rates={"living_area": 75, "site": 10, "age": 500},
)

_active = UNSET


def use(profile):
    """Choose the case whose facts the rules may assert."""
    global _active
    _active = profile
    return _active


def active():
    return _active


#: field-name pattern -> what to put there, and why.  First match wins.
#: A bare string is a key into the profile's own subject facts; a Literal is
#: true of any report and needs no profile.
RULES = [
    (r"^GC\d_DWELL_STYLE$", "style", "the same dwelling style as the subject"),
    (r"^GC\d_DWELL_COOL$", "cooling", "the cooling reported for the subject"),
    (r"^GC\d_SITE_ZONE_COMPLIANCE$", "zoning", "conforming, like the subject"),
    (r"^GC\d_LEVELS$", "levels", "as many levels as the subject's own unit"),
    (r"^GC\d_INT_COND_FLOORS$", "floors_condition",
     "held equal with the subject"),
    (r"^GC\d_VEHICLE_STORAGE$", "vehicle_storage",
     "the same vehicle storage as the subject"),
    (r"^GC\d_DWELL_TOTAL_VOLUME$", Literal("0"), "not requested by the client"),
    (r"^GC\d_DWELL_WINDOW_AREA$", Literal("0"), "not requested by the client"),

    (r"^DE1_STYLE$", "style", "the subject's own style"),
    (r"^DE1_HEAT_DETAIL$", "heating_detail", "the subject's own heating fuel"),
    (r"^UI\d_OCCUPANCY$", "occupancy", "the occupancy the order reports"),
    (r"^UI\d_LEVEL_UNFINISHED_AREA$", Literal("0"),
     "no unfinished area reported in the unit"),
    (r"^UI\d_AREA_DATA_SOURCE_TYPE$", "area_source",
     "where the areas were taken from"),
    (r"^EXT_SIT_UTIL_IMP$", "utility_impact",
     "a publicly supplied utility, typical of the market"),
    (r"^SIT_UTLIMP_\w+_IMP$", "utility_impact",
     "a publicly supplied utility, typical of the market"),
]

#: Fields nobody should fill from outside the appraiser's own judgement.
LEAVE = {
    "SIGNED_DATE": "the date of signature",
    "SIGNER_LIC_CERT_ID": "the signer's licence number",
    "SIGNER_LIC_CERT_LEVEL": "the signer's credential level",
    "SIGNER_LIC_CERT_EXPIRATION": "the signer's licence expiry",
}

#: Grid rows whose comparable value is taken from the subject's own row.
MIRROR = ("DWELL_COOL", "VEHICLE_STORAGE", "DWELL_STYLE", "DWELL_HEAT")

#: The popup behind each of those rows, in the order its parts are printed.
#:
#: A grid cell like "Garage | 1 | Detached<br>150 Sq. Ft." is not a value
#: anyone types -- it is what TOTAL prints once the popup behind the cell
#: holds Garage, 1 space, Detached, 150 sq ft.  The validator reads the
#: **popup**, not the printed sentence, which is why a row can print the right
#: words and still be reported.
POPUP_PARTS = {
    "DWELL_STYLE": ("PU_DWELL_STYLE",),
    "DWELL_COOL": ("PU_DWELL_COOL",),
    "DWELL_HEAT": ("PU_DWELL_HEAT",),
    "VEHICLE_STORAGE": ("PU_VEHICLE_STORAGE", "PU_VEHICLE_STORAGE_SPACES",
                        "PU_VEHICLE_STORAGE_DETAILS",
                        "PU_VEHICLE_STORAGE_SQFT"),
}

#: TOTAL's own words when a $0 is the wrong entry -- it wants the cell empty.
_BLANK_ADJUSTMENT = "leave the adjustment blank"

_subject = {}


def _pieces(composite):
    """The parts TOTAL assembled a grid cell from, in printed order."""
    return [p.strip() for p in composite.replace("<br>", " | ").split("|")]


def _plain(field, piece):
    """A part as its popup holds it: an area box holds 150, not 150 Sq. Ft."""
    if field.endswith("_SQFT"):
        return re.sub(r"[^\d]", "", piece)
    return piece


def learn_subject(values):
    """Remember what the subject's own grid row holds, by field name."""
    _subject.clear()
    _subject.update(values)


def answer(problem):
    """Decide what this field should hold, or None to leave it alone."""
    name = problem.field
    if name in LEAVE:
        return None

    unit = re.match(r"^UI(\d+)_SECTION_DESCRIPTION$", name)
    if unit:
        return Answer(unit.group(1), "the living unit's own number")

    # A comparable row the subject already answers: copy it exactly, and fill
    # the popup the printed sentence is assembled from, because that is what
    # the validator actually reads.  This needs no profile -- it is read off
    # the report in front of us.
    mirror = re.match(r"^(GC\d)_(" + "|".join(MIRROR) + r")$", name)
    if mirror:
        column, row = mirror.group(1), mirror.group(2)
        held = _subject.get("GSU_" + row, "")
        if held:
            parts = {}
            for part, piece in zip(POPUP_PARTS.get(row, ()), _pieces(held)):
                value = _plain(part, piece)
                if value:
                    parts[column + "_" + part] = value
            return Answer(held, "the same as the subject, so the row cancels",
                          parts=parts)

    for pattern, what, why in RULES:
        if not re.match(pattern, name):
            continue
        if isinstance(what, Literal):
            value, source = what.value, why
        else:
            value = _active.subject.get(what)
            if not value:
                # No profile, or this profile does not answer that fact.  Say
                # nothing rather than borrow another property's answer.
                continue
            source = why + " (" + _active.name + ")"
        if problem.options and value not in problem.options:
            match = next((o for o in problem.options
                          if o.lower() == value.lower()), None)
            if match is None:
                continue
            value = match
        return Answer(value, source)

    # An adjustment cell.  TOTAL distinguishes two cases and says which one it
    # is in the message, so the message decides: a difference with no amount
    # takes $0 -- the appraiser saying the difference is real and unadjusted --
    # while two values that are the *same* take an empty cell, which is what
    # UAD means by an unadjusted row.  Mirroring a row puts it in the second
    # case, so the two rules have to work together.
    if re.match(r"^GC\d_.*_ADJ$", name):
        if _BLANK_ADJUSTMENT in problem.message.lower():
            return Answer("", "subject and comparable match, so the cell is "
                              "left blank rather than adjusted by $0")
        return Answer("$0", "the difference is stated and not adjusted for")

    if name.endswith("_NO") and not (problem.value or "").strip():
        return Answer("X", "the report answers this question no")
    return None
