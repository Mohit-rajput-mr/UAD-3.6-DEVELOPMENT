"""Build ``engine/spec/uad_map.json`` -- the canonical UAD 3.6 mapping.

``field_index.json`` answers "what does the appraiser type into field 4.009".
That question only has an answer for data points A-1 gives a *display*
location, so the 44 data points marked "Does Not Display" -- the Scope of
Work's approach indicators, the coordinates behind the map, the software that
produced the file -- were absent from the model altogether, and the XML we
delivered did not carry them even though A-1 marks most of them Required.

This map answers the delivery question instead: for every MISMO data point
A-1 names, where does it live, what may it hold, which property roles carry
it, and is it required.  It is generated from A-1's own sheets, never typed:

    python engine/uad/spec/build_uad_map.py

Sources (both already extracted from the published workbooks):
  * ``delivery_spec.json``  -- A-1's delivery sheet, one row per data point
    per report location: xPath, parent container, format, conditionality and
    which of the six property roles may carry it.
  * ``enumerations.json``   -- A-1's enumeration sheet, one row per supported
    value per report location, with the display text the report prints.

The two sheets disagree about scope on purpose.  A data point's enumeration
rows are written per *report location*: "Water Features" offers only water
amenities, and that restriction is the specification working as intended.
But the same mechanism also means a list is only ever as complete as the one
row A-1 happened to write it against -- which is why the editor offered eight
party roles where A-1 defines thirteen, and why an image could not be filed
as a Sales Comparable Map.  So both are kept: ``values`` is the union A-1
defines for the data point, ``slots`` is the per-location restriction, and a
caller that knows its slot gets the narrow list while a caller that does not
gets the complete one.
"""
from __future__ import annotations

import json
import re
from collections import defaultdict
from pathlib import Path

SPEC = Path(__file__).resolve().parents[2] / "spec"

DP = "MISMO Data Point Name"
ATTR = "MISMO Attribute Name"
XPATH = "MISMO xPath"
PARENT = "MISMO Parent Container"
LOC = "Report Location"
CONTEXT = "Additional Context"
DEFN = "MISMO Data Point / Attribute Definition"
FMT = "UAD Data Point Format Type"
FMT_D = "UAD Data Point Format Details"
COND = "Conditionality"
COND_D = "Conditionality Details"
CARD = "Cardinality"
SORT = "XML Sort Number"
DP_ENUM = "Supported Data Point Enumerations\n\n(Reference the MISMO Data Point Name column)"
AT_ENUM = "Supported Attribute Enumerations\n\n(Reference the MISMO Attribute Name column)"

ROLES = ("Subject Property", "Land Comparable", "Property Analyzed Not Used",
         "Rental Comparable", "Gross Rent Multiplier Comparable", "Sales Comparable")

E_NAME = "MISMO Data Point / Attribute Name"
E_VALUE = "Supported Enumerations"
E_LOC = "Report Location"
E_TEXT = ("Output Report Display Text\n\n(Not to be Included in the XML File)\n"
          "(Refer to the Implementation Guide for further details)")

NOT_SHOWN = "Does Not Display"


def _text(v) -> str:
    return "" if v is None else str(v).strip()


def _fids(location: str) -> list[str]:
    """Every Report Field ID a packed Report Location names.

    A-1 writes several locations into one cell.  Taking only the first means
    an enumeration row restricts one field and silently widens every other
    field that shared the cell -- which is how the Water Features amenity row
    came to offer all fifty-six amenities.  ``build_index`` already solved
    this for the field model; the same parser decides slots here, so the two
    cannot drift apart.
    """
    try:
        from .build_index import parse_locations
    except ImportError:                      # run as a script, not a module
        from build_index import parse_locations

    return [fid for fid, _section, _subsection, _label in parse_locations(location)]


def _values(raw: str) -> list[str]:
    return [v.strip() for v in (raw or "").split("|") if v.strip()]


def build() -> dict:
    delivery = json.loads((SPEC / "delivery_spec.json").read_text(encoding="utf-8"))
    enums = json.loads((SPEC / "enumerations.json").read_text(encoding="utf-8"))

    points: dict[str, dict] = {}
    for row in delivery:
        name = _text(row.get(DP))
        if not name:
            continue
        loc = _text(row.get(LOC))
        entry = points.setdefault(name, {
            "mismo": name, "xpath": "", "container": "", "attribute": "",
            "format_type": "", "format_details": "", "definition": "",
            "values": [], "attribute_values": [], "slots": {}, "contexts": [],
            "locations": [], "displays": False, "conditionality": {},
            "cardinality": "", "sort": None, "placements": [],
        })
        # A data point is not in one place.  LatitudeIdentifier is on the
        # property and on every geotagged image; AddressLineText is on the
        # subject, each comparable and every party.  Keeping only the first
        # container made the map claim the coordinates behind the map live
        # inside an IMAGE.  So every distinct placement is recorded, and the
        # lowest XML sort number -- A-1's own document order -- is the
        # primary one a caller gets when it does not say which it means.
        sort = _text(row.get(SORT))
        rank = int(sort) if sort.isdigit() else 10 ** 9
        xpath, parent = _text(row.get(XPATH)), _text(row.get(PARENT))
        place = {"xpath": xpath, "container": parent,
                 "context": _text(row.get(CONTEXT)), "sort": rank,
                 "displays": bool(loc and loc != NOT_SHOWN)}
        if not any(p["xpath"] == xpath and p["context"] == place["context"]
                   for p in entry["placements"]):
            entry["placements"].append(place)
        if entry["sort"] is None or rank < entry["sort"]:
            entry["sort"] = rank
            entry["xpath"] = xpath
            entry["container"] = parent
        entry["attribute"] = entry["attribute"] or _text(row.get(ATTR))
        entry["format_type"] = entry["format_type"] or _text(row.get(FMT))
        entry["format_details"] = entry["format_details"] or _text(row.get(FMT_D))
        entry["definition"] = entry["definition"] or _text(row.get(DEFN))
        entry["cardinality"] = entry["cardinality"] or _text(row.get(CARD))

        for v in _values(_text(row.get(DP_ENUM))):
            if v not in entry["values"]:
                entry["values"].append(v)
        for v in _values(_text(row.get(AT_ENUM))):
            if v not in entry["attribute_values"]:
                entry["attribute_values"].append(v)

        ctx = _text(row.get(CONTEXT))
        if ctx and ctx not in entry["contexts"]:
            entry["contexts"].append(ctx)
        if loc and loc != NOT_SHOWN:
            entry["displays"] = True
            if loc not in entry["locations"]:
                entry["locations"].append(loc)

        # conditionality is stated per property role
        cond = _text(row.get(COND))
        if cond:
            for role in ROLES:
                if _text(row.get(role)):
                    prior = entry["conditionality"].get(role)
                    # Required outranks Conditionally Required
                    if prior != "R":
                        entry["conditionality"][role] = cond
            if not any(_text(row.get(r)) for r in ROLES):
                entry["conditionality"].setdefault("Subject Property", cond)
        detail = _text(row.get(COND_D))
        if detail and not entry.get("conditionality_details"):
            entry["conditionality_details"] = detail

    # A-1's enumeration sheet: the union per data point, and the restriction
    # each report location puts on it
    display_text: dict[tuple[str, str], str] = {}
    for row in enums:
        name = _text(row.get(E_NAME))
        value = _text(row.get(E_VALUE))
        if not name or not value:
            continue
        entry = points.get(name)
        if entry is None:
            continue
        if value not in entry["values"]:
            entry["values"].append(value)
        for slot in _fids(_text(row.get(E_LOC))):
            entry["slots"].setdefault(slot, [])
            if value not in entry["slots"][slot]:
                entry["slots"][slot].append(value)
        shown = _text(row.get(E_TEXT))
        if shown:
            display_text.setdefault((name, value), shown)

    for entry in points.values():
        entry["values"].sort()
        entry["attribute_values"].sort()
        for slot in entry["slots"].values():
            slot.sort()
        entry["placements"].sort(key=lambda p: p["sort"])

    labels = defaultdict(dict)
    for (name, value), shown in display_text.items():
        labels[name][value] = shown

    return {
        "generated_from": ["delivery_spec.json", "enumerations.json"],
        "data_points": dict(sorted(points.items())),
        "display_text": {k: dict(sorted(v.items())) for k, v in sorted(labels.items())},
    }


def main() -> None:
    out = build()
    path = SPEC / "uad_map.json"
    path.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    pts = out["data_points"]
    shown = sum(1 for p in pts.values() if p["displays"])
    print(f"{path.name}: {len(pts)} data points "
          f"({shown} displaying, {len(pts) - shown} delivery-only), "
          f"{len(out['display_text'])} with report display text")


if __name__ == "__main__":
    main()
