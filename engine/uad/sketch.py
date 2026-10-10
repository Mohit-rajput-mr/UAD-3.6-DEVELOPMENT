"""The built-in sketch: geometry, the area table, and "Save to report" (DR §9).

The drawing itself is done in the editor's sketch panel
(``engine/app/ui/sketch``). This module is the half that has to be right:

* the area of every shape. Straight walls use the shoelace formula; a curved
  wall (a bay, a rounded end) is a circular arc stored as its *bulge* -- the
  tangent of a quarter of the arc's angle, the DXF convention -- and adds or
  removes its circular segment;
* the area table: per floor and per unit, finished / unfinished, above /
  below grade, standard / nonstandard, with deductions (open-to-below,
  atrium) taken from the shape they sit in;
* what "Save to report" writes, for each living unit of the subject:
  - ``PROPERTY_UNIT_AREA``: the six area measures, A-1's Unit... measures;
  - ``LEVELS/LEVEL``: LevelType, GradeLevelType, LevelFinishedAreaMeasure and
    LevelUnfinishedAreaMeasure;
  - the rooms the sketch names, as ``ROOM``s on their level, with Levels in
    Unit, Bedrooms and Baths re-counted by ``rooms.recount``.
  The sketch picture itself goes in as the Sketch exhibit
  (``SubjectPropertyImprovementSketch``); a re-save replaces it, never adds a
  second.

A sketch JSON (version 1)::

    {"version": 1, "units": "ft",
     "pages": [{"id": "p1", "name": "Sketch 1",
                "floorTitles": {"LevelOne": "First Floor"},
                "areas": [{"id": "a1", "name": "First Floor", "floor": "LevelOne", "unit": 1,
                           "kind": "living", "gla": true, "finished": true,
                           "nonstandard": false, "subtract": false,
                           "grade": "FullyBelowGrade",       # basements only
                           "points": [{"x": 0, "y": 0, "b": 0}, ...]}],
                "labels": [{"id": "l1", "text": "Bedroom", "x": 4, "y": 5}],
                "symbols": [...], "doors": [...]}]}

Coordinates are feet, y downwards (as drawn). Bulge ``b`` belongs to the wall
from that point to the next: 0 is straight; otherwise the arc's middle sits at
``chord middle + (b / 2) * (-dy, dx)`` for the wall's (dx, dy) -- the sketch
panel draws it with the same formula.
"""
from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any

from lxml import etree

from . import bind, edit

M = f"{{{bind.MISMO}}}"

# A-1 LevelType (10.029) and how the sketch names them.
ABOVE = ["LevelOne", "LevelTwo", "LevelThree", "LevelFour", "LevelFive",
         "LevelSix", "LevelSeven", "LevelEight", "LevelNine", "LevelTen"]
BELOW = ["BelowGradeOne", "BelowGradeTwo", "BelowGradeThree", "BelowGradeFour", "BelowGradeFive"]
FLOOR_TITLES = {"LevelOne": "First Floor", "LevelTwo": "Second Floor", "LevelThree": "Third Floor",
                "LevelFour": "Fourth Floor", "LevelFive": "Fifth Floor", "LevelSix": "Sixth Floor",
                "LevelSeven": "Seventh Floor", "LevelEight": "Eighth Floor", "LevelNine": "Ninth Floor",
                "LevelTen": "Tenth Floor", "BelowGradeOne": "Basement", "BelowGradeTwo": "Lower Level 2",
                "BelowGradeThree": "Lower Level 3", "BelowGradeFour": "Lower Level 4",
                "BelowGradeFive": "Lower Level 5"}
GRADES = ("PartiallyBelowGrade", "FullyBelowGrade")
#: shapes that are not living area: never in a unit's areas (a garage's area is vehicle storage)
NOT_LIVING = {"garage", "carport", "porch", "deck", "patio", "balcony", "breezeway", "shed", "other"}

# room labels -> A-1 RoomType (10.033); a label naming none of these is not a room
ROOM_WORDS = [
    (("half bath", "half-bath", "powder", "1/2 bath", "½ bath"), "HalfBathroom"),
    (("bath", "bathroom"), "FullBathroom"),
    (("bed", "bedroom", "br"), "Bedroom"),
    (("breakfast",), "BreakfastRoom"),
    (("den", "office", "study"), "Den"),
    (("dining",), "DiningRoom"),
    (("family", "great room"), "FamilyRoom"),
    (("kitchen", "kit"), "Kitchen"),
    (("laundry", "washer", "w/d"), "LaundryRoom"),
    (("living",), "LivingRoom"),
    (("loft",), "Loft"),
    (("media", "theater"), "MediaRoom"),
    (("mudroom", "mud room"), "Mudroom"),
    (("recreation", "rec room", "game room", "bonus"), "RecreationRoom"),
    (("sunroom", "sun room", "florida room"), "Sunroom"),
    (("utility", "boiler", "mechanical"), "UtilityRoom"),
    (("pantry",), "WalkInPantry"),
    (("workshop",), "Workshop"),
]


def room_type(label: str) -> str | None:
    t = " " + " ".join((label or "").lower().replace(".", " ").split()) + " "
    for words, kind in ROOM_WORDS:
        for w in words:
            if f" {w} " in t or t.strip().startswith(w + " ") or t.strip() == w:
                return kind
    return None


# ------------------------------------------------------------------ geometry
def _seg(p: dict, q: dict) -> tuple[float, float, float]:
    """(chord, arc length, signed circular-segment area) of the wall p -> q."""
    dx, dy = q["x"] - p["x"], q["y"] - p["y"]
    c = math.hypot(dx, dy)
    b = float(p.get("b") or 0)
    if not b or not c:
        return c, c, 0.0
    theta = 4 * math.atan(abs(b))                    # the arc's angle
    r = c / (2 * math.sin(theta / 2))
    seg = r * r / 2 * (theta - math.sin(theta))
    return c, r * theta, math.copysign(seg, b)


def polygon_area(points: list[dict]) -> float:
    """The area enclosed, arcs included (always positive)."""
    n = len(points)
    if n < 2:
        return 0.0
    s = 0.0
    arcs = 0.0
    for i in range(n):
        p, q = points[i], points[(i + 1) % n]
        s += p["x"] * q["y"] - q["x"] * p["y"]
        arcs += _seg(p, q)[2]
    # Walking an arc instead of its chord adds the loop arc-then-chord-back to
    # the boundary integral. With the arc's middle on the (-dy, dx) side of the
    # wall (positive bulge) that loop runs the negative way round: its segment
    # comes off the signed area, whichever way the shape was drawn.
    return abs(s / 2 - arcs)


def wall_lengths(points: list[dict]) -> list[float]:
    return [_seg(points[i], points[(i + 1) % len(points)])[1] for i in range(len(points))]


def centroid(points: list[dict]) -> tuple[float, float]:
    n = len(points)
    return (sum(p["x"] for p in points) / n, sum(p["y"] for p in points) / n) if n else (0.0, 0.0)


def contains(points: list[dict], x: float, y: float) -> bool:
    """Point in polygon (straight walls; good enough to place a label)."""
    inside = False
    n = len(points)
    for i in range(n):
        a, b = points[i], points[(i + 1) % n]
        if (a["y"] > y) != (b["y"] > y):
            xi = a["x"] + (y - a["y"]) * (b["x"] - a["x"]) / ((b["y"] - a["y"]) or 1e-12)
            if x < xi:
                inside = not inside
    return inside


def _int(text) -> int:
    try:
        return int(round(float(str(text or "0").replace(",", ""))))
    except ValueError:
        return 0


def round_area(a: float) -> int:
    return int(math.floor(a + 0.5))


# ----------------------------------------------------------------- the table
@dataclass
class UnitAreas:
    unit: int
    standard_above: float = 0.0
    nonstandard_above: float = 0.0
    unfinished_above: float = 0.0
    standard_below: float = 0.0
    nonstandard_below: float = 0.0
    unfinished_below: float = 0.0
    levels: dict[str, dict[str, Any]] = field(default_factory=dict)   # LevelType -> {finished, unfinished, grade}
    rooms: dict[str, list[str]] = field(default_factory=dict)          # LevelType -> [RoomType]

    @property
    def total_finished(self) -> float:
        return self.standard_above + self.nonstandard_above + self.standard_below + self.nonstandard_below

    def to_json(self) -> dict[str, Any]:
        return {"unit": self.unit,
                "standard_above": round_area(self.standard_above),
                "nonstandard_above": round_area(self.nonstandard_above),
                "unfinished_above": round_area(self.unfinished_above),
                "standard_below": round_area(self.standard_below),
                "nonstandard_below": round_area(self.nonstandard_below),
                "unfinished_below": round_area(self.unfinished_below),
                "total_finished": round_area(self.total_finished),
                "levels": {k: {**v, "finished": round_area(v["finished"]),
                               "unfinished": round_area(v["unfinished"])} for k, v in self.levels.items()},
                "rooms": self.rooms,
                "bedrooms": sum(r.count("Bedroom") for r in self.rooms.values()),
                "full_baths": sum(r.count("FullBathroom") for r in self.rooms.values()),
                "half_baths": sum(r.count("HalfBathroom") for r in self.rooms.values())}


def _areas(sketch: dict) -> list[dict]:
    out = []
    for page in sketch.get("pages") or []:
        for a in page.get("areas") or []:
            pts = [{"x": float(p.get("x", 0)), "y": float(p.get("y", 0)), "b": float(p.get("b") or 0)}
                   for p in a.get("points") or []]
            if len(pts) >= 3:
                out.append({**a, "points": pts, "_page": page.get("id")})
    return out


def _host(a: dict, areas: list[dict]) -> dict | None:
    """The smallest non-deduction shape on the same floor and page that holds
    this one's centre -- where a deduction (open to below) comes off."""
    cx, cy = centroid(a["points"])
    best = None
    for h in areas:
        if h is a or h.get("subtract") or h.get("floor") != a.get("floor") or h.get("_page") != a.get("_page"):
            continue
        if contains(h["points"], cx, cy):
            if best is None or polygon_area(h["points"]) < polygon_area(best["points"]):
                best = h
    return best


def table(sketch: dict) -> dict:
    """Areas per shape, per floor and per unit, and the rooms the labels name."""
    areas = _areas(sketch)
    shapes, units = [], {}
    for a in areas:
        area = polygon_area(a["points"])
        flags = a
        if a.get("subtract"):
            host = _host(a, areas)
            flags = host or a
            area = -area
        floor = a.get("floor") or "LevelOne"
        kind = (flags.get("kind") or "living").lower()
        unit = int(flags.get("unit") or 1)
        finished = bool(flags.get("finished", kind not in NOT_LIVING))
        gla = bool(flags.get("gla", kind not in NOT_LIVING))
        nonstd = bool(flags.get("nonstandard", False))
        below = floor in BELOW
        living = kind not in NOT_LIVING
        shapes.append({"id": a.get("id"), "name": a.get("name") or "", "floor": floor, "unit": unit,
                       "kind": kind, "area": round_area(area), "exact": area,
                       "walls": [round(w, 2) for w in wall_lengths(a["points"])],
                       "gla": gla and finished and not nonstd and not below and living,
                       "finished": finished, "nonstandard": nonstd, "below": below,
                       "subtract": bool(a.get("subtract")), "living": living})
        if not living:
            # a garage or porch drawn inside a living outline is not living
            # area: it comes off the outline it sits in
            host = _host(a, areas) if not a.get("subtract") else None
            if host is None or (host.get("kind") or "living").lower() in NOT_LIVING:
                continue
            flags, area = host, -area
            unit = int(host.get("unit") or 1)
            finished = bool(host.get("finished", True))
            gla = bool(host.get("gla", True))
            nonstd = bool(host.get("nonstandard", False))
        u = units.setdefault(unit, UnitAreas(unit))
        lvl = u.levels.setdefault(floor, {"finished": 0.0, "unfinished": 0.0,
                                          "grade": (a.get("grade") if a.get("grade") in GRADES else
                                                    (flags.get("grade") if flags.get("grade") in GRADES
                                                     else "FullyBelowGrade")) if below else "AboveGrade",
                                          "title": ""})
        if finished:
            lvl["finished"] += area
            if below:
                if nonstd:
                    u.nonstandard_below += area
                else:
                    u.standard_below += area
            else:
                if nonstd or not gla:
                    u.nonstandard_above += area
                else:
                    u.standard_above += area
        else:
            lvl["unfinished"] += area
            if below:
                u.unfinished_below += area
            else:
                u.unfinished_above += area
    # rooms: a label inside a living shape is a room of that shape's unit and floor
    for page in sketch.get("pages") or []:
        page_areas = [a for a in areas if a.get("_page") == page.get("id") and not a.get("subtract")
                      and (a.get("kind") or "living").lower() not in NOT_LIVING]
        for lab in page.get("labels") or []:
            kind = room_type(str(lab.get("text") or ""))
            if not kind:
                continue
            x, y = float(lab.get("x", 0)), float(lab.get("y", 0))
            hosts = [a for a in page_areas if contains(a["points"], x, y)]
            if not hosts:
                continue
            host = min(hosts, key=lambda a: polygon_area(a["points"]))
            u = units.setdefault(int(host.get("unit") or 1), UnitAreas(int(host.get("unit") or 1)))
            u.rooms.setdefault(host.get("floor") or "LevelOne", []).append(kind)
    for page in sketch.get("pages") or []:
        for fl, title in (page.get("floorTitles") or {}).items():
            for u in units.values():
                if fl in u.levels and title:
                    u.levels[fl]["title"] = str(title)
    return {"shapes": shapes, "units": [units[k].to_json() for k in sorted(units)]}


# -------------------------------------------------------------- the report
AREA_POINTS = [("standard_above", "UnitStandardAboveGradeFinishedAreaMeasure"),
               ("nonstandard_above", "UnitNonStandardAboveGradeFinishedAreaMeasure"),
               ("unfinished_above", "UnitAboveGradeUnfinishedAreaMeasure"),
               ("standard_below", "UnitStandardBelowGradeFinishedAreaMeasure"),
               ("nonstandard_below", "UnitNonStandardBelowGradeFinishedAreaMeasure"),
               ("unfinished_below", "UnitBelowGradeUnfinishedAreaMeasure")]


def _set_measure(parent: etree._Element, name: str, value: int, changes: list, where: str) -> None:
    node = parent.find(f"{M}{name}")
    if node is None:
        node = edit.insert_ordered(parent, name)
    old = (node.text or "").strip()
    node.set("AreaUnitOfMeasureType", "SquareFeet")
    if old != str(value):
        node.text = str(value)
        changes.append({"where": where, "what": name, "old": old, "new": str(value)})


def _set_text(parent: etree._Element, name: str, value: str, changes: list, where: str) -> None:
    node = parent.find(f"{M}{name}")
    if node is None:
        node = edit.insert_ordered(parent, name)
    old = (node.text or "").strip()
    if old != value:
        node.text = value
        changes.append({"where": where, "what": name, "old": old, "new": value})


def subject_units(root: etree._Element) -> list[etree._Element]:
    from . import structure
    subj = next((p for p in root.iter(f"{M}PROPERTY") if p.get("ValuationUseType") == "SubjectProperty"), None)
    if subj is None:
        return []
    return [u for u in structure.all_units(subj) if not structure.is_adu(u)] + \
           [u for u in structure.all_units(subj) if structure.is_adu(u)]


def apply(tree, sketch: dict) -> dict:
    """Write the sketch's areas, levels and rooms into the subject's units."""
    from . import rooms as rooms_mod
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    t = table(sketch)
    units = subject_units(root)
    changes: list[dict] = []
    skipped: list[str] = []
    kept: list[str] = []
    for ua in t["units"]:
        n = ua["unit"]
        if not 1 <= n <= len(units):
            skipped.append(f"Unit {n} is not in this report (it has {len(units)} unit(s))")
            continue
        unit = units[n - 1]
        where = f"Unit {n}"
        # a floor the sketch does not draw keeps its level, and counts in the
        # unit's totals as it stands (finished as standard area)
        totals = {key: ua[key] for key, _point in AREA_POINTS}
        for level in unit.findall(f"{M}LEVELS/{M}LEVEL"):
            floor = (level.findtext(f"{M}LevelType") or "").strip()
            if not floor or floor in ua["levels"]:
                continue
            below = floor in BELOW or (level.findtext(f"{M}GradeLevelType") or "").strip() in GRADES
            fin = _int(level.findtext(f"{M}LevelFinishedAreaMeasure"))
            unf = _int(level.findtext(f"{M}LevelUnfinishedAreaMeasure"))
            totals["standard_below" if below else "standard_above"] += fin
            totals["unfinished_below" if below else "unfinished_above"] += unf
            kept.append(f"{where} {FLOOR_TITLES.get(floor, floor)}: {fin:,} sq ft finished, "
                        f"{unf:,} unfinished, as the report had it")
        area = unit.find(f"{M}PROPERTY_UNIT_AREA")
        if area is None:
            area = edit.insert_ordered(unit, "PROPERTY_UNIT_AREA")
        for key, point in AREA_POINTS:
            _set_measure(area, point, totals[key], changes, where)
        total = area.find(f"{M}UnitTotalFinishedAreaMeasure")
        if total is not None:          # carried by some report types only (Condo2, 2-4 unit)
            _set_measure(area, "UnitTotalFinishedAreaMeasure",
                         sum(totals[k] for k in ("standard_above", "nonstandard_above",
                                                 "standard_below", "nonstandard_below")), changes, where)
        holder = unit.find(f"{M}LEVELS")
        if holder is None:
            holder = edit.insert_ordered(unit, "LEVELS")
        for floor, lv in ua["levels"].items():
            level = next((x for x in holder.findall(f"{M}LEVEL")
                          if (x.findtext(f"{M}LevelType") or "").strip() == floor), None)
            if level is None:
                level = edit.insert_ordered(holder, "LEVEL")
            lw = f"{where} {FLOOR_TITLES.get(floor, floor)}"
            _set_text(level, "GradeLevelType", lv["grade"], changes, lw)
            _set_measure(level, "LevelFinishedAreaMeasure", lv["finished"], changes, lw)
            _set_text(level, "LevelType", floor, changes, lw)
            _set_measure(level, "LevelUnfinishedAreaMeasure", lv["unfinished"], changes, lw)
        if ua["rooms"]:
            # the rooms on the floors the sketch draws are the sketch's; rooms on
            # floors it does not draw stay as they were
            existing = unit.findall(f"{M}ROOMS/{M}ROOM")
            for room in existing:
                if (room.findtext(f"{M}ROOM_DETAIL/{M}LevelType") or "").strip() in ua["rooms"]:
                    room.getparent().remove(room)
            for floor, kinds in ua["rooms"].items():
                level = next((x for x in holder.findall(f"{M}LEVEL")
                              if (x.findtext(f"{M}LevelType") or "").strip() == floor), None)
                if level is None:
                    continue
                for kind in kinds:
                    rooms_mod.add_room(level, kind)
            for k, v in rooms_mod.recount(unit).items():
                changes.append({"where": where, "what": k, "old": "", "new": v})
    return {"table": t, "changes": changes, "skipped": skipped, "kept": kept}


def check(sketch: Any) -> dict:
    """A sketch from the browser, checked and normalised (raises ValueError)."""
    if not isinstance(sketch, dict) or not isinstance(sketch.get("pages"), list):
        raise ValueError("a sketch has pages")
    if len(sketch["pages"]) > 40:
        raise ValueError("too many sketch pages")
    count = 0
    for page in sketch["pages"]:
        if not isinstance(page, dict):
            raise ValueError("a sketch page is not an object")
        for a in page.get("areas") or []:
            count += 1
            if a.get("floor") and a["floor"] not in ABOVE + BELOW:
                raise ValueError(f"unknown floor {a['floor']!r}")
            for p in a.get("points") or []:
                for k in ("x", "y"):
                    v = float(p.get(k, 0))
                    if not math.isfinite(v) or abs(v) > 100_000:
                        raise ValueError("a point is out of range")
    if count > 2000:
        raise ValueError("too many shapes")
    return {**sketch, "version": 1, "units": "ft"}
