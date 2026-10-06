"""Rooms and levels of a living unit, edited where the report shows them.

A-1 keeps a unit's rooms as one ``ROOM`` each under ``PROPERTY_UNIT/ROOMS``,
tied to a level by ``ROOM_DETAIL/LevelType`` (the ``LEVEL`` it is on,
``PROPERTY_UNIT/LEVELS/LEVEL``); B-1's Level and Room Detail table (10.029 -
10.033) prints each level with a "Room Summary" of "<count> - <room type>".
So adding a room is adding a ROOM on that level, and a summary line's count is
the number of ROOMs of that type there.

The counts B-1 prints beside the table -- Levels in Unit (10.017), Total
Bedrooms (10.023), Total Bathrooms Full / Half (10.024 / 10.025) -- are the
same facts counted, and the D-1 samples keep them equal (SF1: three levels,
five bedrooms, three full and one half bath, exactly its rooms).  B-1's
Usability guidance (item 8) asks for one source of entry, so a change made
here re-counts them for the unit; a count typed by hand stays until the rooms
or levels next change.
"""
from __future__ import annotations

from lxml import etree

from . import bind, edit

M = f"{{{bind.MISMO}}}"

#: the counts that follow the rooms: data point -> the RoomType it counts
COUNTED = {"BedroomCount": "Bedroom", "FullBathroomCount": "FullBathroom",
           "HalfBathroomCount": "HalfBathroom"}


def _local(node) -> str:
    return etree.QName(node).localname


def level_at(root: etree._Element, key: str) -> etree._Element:
    """The LEVEL a report row stands for (its path, or a path inside it)."""
    node = bind.find_path(root, key) if key else None
    if node is None:
        try:
            hit = root.getroottree().xpath(key)
            node = hit[0] if hit else None
        except etree.XPathError:
            node = None
    while node is not None and _local(node) != "LEVEL":
        node = node.getparent()
    if node is None:
        raise KeyError("that level is no longer in the report; reload it")
    return node


def unit_of(level: etree._Element) -> etree._Element:
    unit = level.getparent()
    while unit is not None and _local(unit) != "PROPERTY_UNIT":
        unit = unit.getparent()
    if unit is None:
        raise KeyError("the level is not inside a living unit")
    return unit


def rooms_on(level: etree._Element) -> list[etree._Element]:
    kind = (level.findtext(f"{M}LevelType") or "").strip()
    unit = unit_of(level)
    return [r for r in unit.findall(f"{M}ROOMS/{M}ROOM")
            if (r.findtext(f"{M}ROOM_DETAIL/{M}LevelType") or "").strip() == kind]


def _matches(room: etree._Element, room_type: str, other: str) -> bool:
    d = room.find(f"{M}ROOM_DETAIL")
    if d is None or (d.findtext(f"{M}RoomType") or "").strip() != room_type:
        return False
    if room_type == "Other":
        return (d.findtext(f"{M}RoomTypeOtherDescription") or "").strip().casefold() == other.strip().casefold()
    return True


def add_room(level: etree._Element, room_type: str, other: str = "") -> etree._Element:
    """One more room of this type on this level."""
    kind = (level.findtext(f"{M}LevelType") or "").strip()
    if not kind:
        raise ValueError("choose the level (Level in Unit) before adding its rooms")
    if not room_type:
        raise ValueError("choose a room type")
    if room_type == "Other" and not other.strip():
        raise ValueError("describe the room: with Other, only the description prints")
    unit = unit_of(level)
    holder = unit.find(f"{M}ROOMS")
    if holder is None:
        holder = edit.insert_ordered(unit, "ROOMS")
    room = etree.SubElement(holder, f"{M}ROOM")
    detail = edit.insert_ordered(room, "ROOM_DETAIL")
    edit.insert_ordered(detail, "LevelType").text = kind
    edit.insert_ordered(detail, "RoomType").text = room_type
    if room_type == "Other":
        edit.insert_ordered(detail, "RoomTypeOtherDescription").text = other.strip()
    recount(unit)
    return room


def remove_room(level: etree._Element, room_type: str, other: str = "") -> bool:
    """One room of this type off this level -- the one holding least (no
    photo, no condition or update answers) goes first, so the answered
    kitchen survives when one of two kitchens is removed."""
    matching = [r for r in rooms_on(level) if _matches(r, room_type, other)]
    if not matching:
        return False
    victim = min(matching, key=lambda r: (sum(1 for _ in r.iter()), -matching.index(r)))
    holder = victim.getparent()
    holder.remove(victim)
    if not len(holder):
        holder.getparent().remove(holder)
    recount(unit_of(level))
    return True


def remove_level(level: etree._Element) -> int:
    """A level and every room on it.  Returns how many rooms went with it."""
    unit = unit_of(level)
    rooms = rooms_on(level)
    for r in rooms:
        holder = r.getparent()
        holder.remove(r)
        if not len(holder):
            holder.getparent().remove(holder)
    holder = level.getparent()
    holder.remove(level)
    if not len(holder):
        holder.getparent().remove(holder)
    recount(unit)
    return len(rooms)


def recount(unit: etree._Element) -> dict[str, str]:
    """Levels in Unit, Total Bedrooms and Total Bathrooms from the unit's own
    levels and rooms (only when it lists any: a unit with no rooms keeps the
    counts typed for it).  Returns what changed."""
    changed: dict[str, str] = {}
    detail = unit.find(f"{M}PROPERTY_UNIT_DETAIL")
    levels = unit.findall(f"{M}LEVELS/{M}LEVEL")
    rooms = unit.findall(f"{M}ROOMS/{M}ROOM")
    wanted: dict[str, int] = {}
    if levels:
        wanted["LevelCount"] = len(levels)
    if rooms:
        for name, kind in COUNTED.items():
            wanted[name] = sum(1 for r in rooms
                               if (r.findtext(f"{M}ROOM_DETAIL/{M}RoomType") or "").strip() == kind)
    if not wanted:
        return changed
    if detail is None:
        detail = edit.insert_ordered(unit, "PROPERTY_UNIT_DETAIL")
    for name, n in wanted.items():
        node = detail.find(f"{M}{name}")
        if node is None:
            node = edit.insert_ordered(detail, name)
        if (node.text or "").strip() != str(n):
            node.text = str(n)
            changed[name] = str(n)
    return changed


def room_types() -> list[tuple[str, str]]:
    """The room types A-1 allows on a level (10.033), as (value, shown)."""
    from .report import form
    return list(form.choices_for("10.033"))


# ---------------------------------------------------------------- flooring
# B-1 10.044-10.049: Interior Features has a row for each flooring type in the
# unit ("When there are multiple types of flooring in the unit, each flooring
# type displays on a separate row"), each a FLOOR_COVERING inside the unit's
# INTERIOR_COMPONENT whose ImprovementComponentType is "Flooring".
def flooring_component(unit: etree._Element, *, create: bool = False) -> etree._Element | None:
    for comp in unit.findall(f"{M}INTERIOR_COMPONENTS/{M}INTERIOR_COMPONENT"):
        if (comp.findtext(f"{M}INTERIOR_COMPONENT_DETAIL/{M}ImprovementComponentType") or "").strip() == "Flooring":
            return comp
    if not create:
        return None
    holder = unit.find(f"{M}INTERIOR_COMPONENTS")
    if holder is None:
        holder = edit.insert_ordered(unit, "INTERIOR_COMPONENTS")
    comp = etree.SubElement(holder, f"{M}INTERIOR_COMPONENT")
    detail = edit.insert_ordered(comp, "INTERIOR_COMPONENT_DETAIL")
    edit.insert_ordered(detail, "ImprovementComponentType").text = "Flooring"
    return comp


def add_flooring(unit: etree._Element, flooring_type: str, other: str = "") -> etree._Element:
    if not flooring_type:
        raise ValueError("choose a flooring type")
    if flooring_type == "Other" and not other.strip():
        raise ValueError("describe the flooring: with Other, only the description prints")
    comp = flooring_component(unit, create=True)
    holder = comp.find(f"{M}FLOOR_COVERINGS")
    if holder is None:
        holder = edit.insert_ordered(comp, "FLOOR_COVERINGS")
    for fc in holder.findall(f"{M}FLOOR_COVERING"):
        same = (fc.findtext(f"{M}FlooringType") or "").strip() == flooring_type and (
            flooring_type != "Other"
            or (fc.findtext(f"{M}FlooringTypeOtherDescription") or "").strip().casefold() == other.strip().casefold())
        if same:
            raise ValueError("that flooring is already listed for this unit")
    fc = etree.SubElement(holder, f"{M}FLOOR_COVERING")
    edit.insert_ordered(fc, "FlooringType").text = flooring_type
    if flooring_type == "Other":
        edit.insert_ordered(fc, "FlooringTypeOtherDescription").text = other.strip()
    return fc


def remove_block(root: etree._Element, key: str, tag: str) -> None:
    """Remove one repeated block (a FLOOR_COVERING row) and any holder it
    leaves empty."""
    node = bind.find_path(root, key)
    if node is None:
        try:
            hit = root.getroottree().xpath(key)
            node = hit[0] if hit else None
        except etree.XPathError:
            node = None
    while node is not None and _local(node) != tag:
        node = node.getparent()
    if node is None:
        raise KeyError("that row is no longer in the report; reload it")
    holder = node.getparent()
    holder.remove(node)
    if not len(holder):
        holder.getparent().remove(holder)


def unit_at(root: etree._Element, key: str) -> etree._Element:
    node = bind.find_path(root, key) if key else None
    if node is None and key:
        try:
            hit = root.getroottree().xpath(key)
            node = hit[0] if hit else None
        except etree.XPathError:
            node = None
    while node is not None and _local(node) != "PROPERTY_UNIT":
        node = node.getparent()
    if node is None:
        subject = bind.subject(root)
        node = subject.find(f".//{M}PROPERTY_UNIT") if subject is not None else None
    if node is None:
        raise KeyError("the report has no living unit yet")
    return node
