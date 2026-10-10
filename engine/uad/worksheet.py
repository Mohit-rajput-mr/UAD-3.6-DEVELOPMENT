"""Adjustment worksheets for the sales grid: one per adjustable row (DR §11).

The owner's brief (2026-10-10) replaces SmartAdjust with worksheets.
WinTOTAL / ACI behave like this: a marker beside an adjustable grid row opens
its worksheet. The appraiser sets $ per unit, a threshold and a rounding step.
For every comparable the worksheet shows the difference, the $ adjustment, the
line % and the adjusted price, and OK fills all comparables at once.

The logic is ported -- not imported, the products stay separate
(``_work/GOAL.md``) -- from the owner's WinTOTAL mod:

* ``total-bridge/bridge/worksheet.py`` (repo kech-3.6-wintotal-mod-autofill-agent):
  the worksheet kinds and their defaults;
* ``total-bridge/bridge/adjust.py``: the arithmetic and the owner's two
  standing rate profiles.

Arithmetic, as there: ``adjustment = (subject - comparable) x rate``, ``0``
when ``|difference| <= threshold`` (the threshold gates the whole
difference), rounded half up to the step (JavaScript's ``Math.round``, which
the mod's worksheet uses -- Python's ``round`` is half to even). A 2-4 unit
report carries one line per unit for the unit rows. There the threshold gates
the building's difference, not each unit's (adjust.multi_lines).

Where a value comes from: what the grid prints (``report/comparables.build``),
so the worksheet shows the same subject and comparable values the appraiser
sees, unit by unit.

Where it goes: one ``COMPARABLE_ADJUSTMENT`` per ``ComparableAdjustmentType``
per comparable. A row repeated per unit carries one per unit, in unit order,
which is how both official 2-4 unit samples (D-1) record them and how the grid
reads them back (``comparables._nth_adjustment``). The totals are re-summed by
the store on save (``grid_math``).
"""
from __future__ import annotations

import math
import re
from dataclasses import asdict, dataclass, field
from typing import Any

from lxml import etree

from . import bind
from .report import comparables

SQFT_PER_ACRE = 43_560
_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?|-?\.\d+")


# ------------------------------------------------------------------ profiles
@dataclass
class Profile:
    """A set of rates. ``0`` means "not in the profile": that worksheet opens
    at $0 and nothing is applied by Adjust all."""
    name: str
    gla: float = 75
    gla_threshold: float = 100
    site: float = 10
    site_threshold: float = 1000
    age: float = 250
    age_threshold: float = 5
    bedroom: float = 10_000
    full_bath: float = 10_000          # a half bath is half of it
    garage: float = 10_000             # per garage space; driveway / carport count 0
    basement: float = 10_000           # a finished area below grade, present vs none
    outdoor: float = 10_000            # deck / patio / porch / balcony vs none
    exposure: float = 2.0              # % of list price, on a listing or pending sale
    design: float = 0                  # one step attached -> semi-detached -> detached
    cooling: float = 0                 # a cooling system vs none
    gla_nonstd: float = 0
    gla_unfin: float = 0
    below_fin: float = 0               # $ per sq ft of finished area below grade
    below_nonstd: float = 0
    below_unfin: float = 0
    rounding: float = 100
    source: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


# The owner's standing profiles (_work/GOAL.md; total-bridge/bridge/adjust.py).
# 18 North's GLA threshold is the owner's 2026-10-07 instruction carried in the
# mod ("no GLA adjustment for a difference under 100 sq ft").
EIGHTEEN_NORTH = Profile(
    name="Single family (18 North)",
    source="_work/GOAL.md and the WinTOTAL mod's adjust.py: rates read from the delivered 18 North grid "
           "(2026-09-29); GLA threshold 100 sq ft (owner 2026-10-07)")
MULTI_FAMILY = Profile(
    name="Multi-family", gla=150, gla_threshold=100, site=20, site_threshold=1000,
    age=250, age_threshold=30, bedroom=20_000, full_bath=20_000, garage=20_000,
    basement=40_000, outdoor=20_000, exposure=2.0, design=20_000, cooling=20_000,
    source="the owner's multi-family rates for every 2-4 unit report (2026-10-02)")
PROFILES = {p.name: p for p in (EIGHTEEN_NORTH, MULTI_FAMILY)}
RATE_KEYS = [k for k in Profile.__dataclass_fields__ if k not in ("name", "source")]


def default_profile(tree) -> Profile:
    return MULTI_FAMILY if subject_units(tree) > 1 else EIGHTEEN_NORTH


def profile_from(data: dict | None, tree=None) -> Profile:
    """A profile from JSON (a built-in by name, overridden key by key)."""
    data = data or {}
    base = PROFILES.get(str(data.get("name", ""))) or (default_profile(tree) if tree is not None
                                                       else EIGHTEEN_NORTH)
    values = base.to_json()
    for k in RATE_KEYS:
        if k in data:
            try:
                values[k] = float(data[k])
            except (TypeError, ValueError):
                pass
    if data.get("name"):
        values["name"] = str(data["name"])[:80]
    return Profile(**values)


# --------------------------------------------------------------------- kinds
@dataclass(frozen=True)
class Kind:
    key: str
    title: str
    adjust_type: str           # the grid row (A-1 ComparableAdjustmentType)
    unit: str                  # what one rate pays for
    parse: str                 # how a printed cell is read
    rate: str                  # the Profile field holding its rate
    threshold: str = ""        # the Profile field holding its threshold
    per_unit: bool = False     # one line per living unit on a 2-4 unit report
    percent: bool = False      # the rate is a % of the comparable's list price
    note: str = ""


KINDS: dict[str, Kind] = {k.key: k for k in (
    Kind("gla", "Finished Area Above Grade", "LivingUnitStandardFinishedAreaAboveGrade",
         "sq ft", "area", "gla", "gla_threshold", per_unit=True),
    Kind("gla_nonstd", "Finished Area Above Grade (Nonstandard)", "LivingUnitNonStandardFinishedAreaAboveGrade",
         "sq ft", "area", "gla_nonstd", per_unit=True),
    Kind("gla_unfin", "Unfinished Area Above Grade", "LivingUnitUnfinishedAreaAboveGrade",
         "sq ft", "area", "gla_unfin", per_unit=True),
    Kind("below_fin", "Finished Area Below Grade", "LivingUnitStandardFinishedAreaBelowGrade",
         "sq ft", "area", "below_fin", per_unit=True),
    Kind("basement", "Finished Area Below Grade (present vs none)", "LivingUnitStandardFinishedAreaBelowGrade",
         "basement", "present", "basement", per_unit=True,
         note="A flat amount for having finished area below grade. It writes the same grid row as "
              "'Finished Area Below Grade' per sq ft: use one or the other."),
    Kind("below_nonstd", "Finished Area Below Grade (Nonstandard)", "LivingUnitNonStandardFinishedAreaBelowGrade",
         "sq ft", "area", "below_nonstd", per_unit=True),
    Kind("below_unfin", "Unfinished Area Below Grade", "LivingUnitUnfinishedAreaBelowGrade",
         "sq ft", "area", "below_unfin", per_unit=True),
    Kind("site", "Site Size", "SiteSize", "sq ft", "area", "site", "site_threshold"),
    Kind("age", "Year Built", "YearBuilt", "year", "num", "age", "age_threshold",
         note="Year built: a newer subject is adjusted upward against an older comparable."),
    Kind("beds", "Bedrooms", "LivingUnitBedroomCount", "bedroom", "num", "bedroom", per_unit=True),
    Kind("baths", "Baths", "LivingUnitBathroomCount", "full bath", "baths", "full_bath", per_unit=True,
         note="Full + half: a half bath counts half of the rate."),
    Kind("garage", "Vehicle Storage (garage spaces)", "VehicleStorage", "space", "garage", "garage",
         note="Garage spaces only: a driveway or carport counts 0."),
    Kind("outdoor", "Outdoor Living", "OutdoorLivingAmenity", "present", "has", "outdoor",
         note="Any deck, patio, porch or balcony against none."),
    Kind("cooling", "Cooling", "CoolingSystem", "present", "has", "cooling",
         note="A cooling system against none."),
    Kind("design", "Attached/Detached", "AttachedOrDetached", "step", "design", "design",
         note="One step: attached -> semi-detached -> detached."),
    Kind("exposure", "Sale to List Price Ratio (market exposure)", "SaleToListPriceRatio",
         "% of list", "exposure", "exposure", percent=True,
         note="Applied to a listing, or a pending sale whose price is its list price: "
              "minus the rate % of the list price."),
)}

DESIGN_RANK = {"attached": 0, "semi-detached": 1, "semidetached": 1, "detached": 2}


def _num(text: str) -> float | None:
    m = _NUM.search(str(text or ""))
    return float(m.group().replace(",", "")) if m else None


def _parse(kind: Kind, text: str) -> float | None:
    t = str(text or "").strip()
    if kind.parse == "area":
        n = _num(t)
        if n is None:
            return None
        return n * SQFT_PER_ACRE if re.search(r"\bac(re)?s?\b", t, re.I) else n
    if kind.parse == "num":
        return _num(t)
    if kind.parse == "baths":
        parts = [p.strip() for p in t.split("|")]
        full = _num(parts[0]) if parts and parts[0] else None
        half = _num(parts[1]) if len(parts) > 1 and parts[1] else None
        if full is None and half is None:
            return None
        return (full or 0) + 0.5 * (half or 0)
    if kind.parse == "garage":
        if not t:
            return None
        total = 0.0
        for line in re.split(r"[\n;]+", t):
            cells = [c.strip() for c in line.split("|")]
            if cells and "garage" in cells[0].lower() and len(cells) > 1:
                total += _num(cells[1]) or 0
        return total
    if kind.parse == "present":
        n = _num(t)
        return None if n is None else (1.0 if n > 0 else 0.0)
    if kind.parse == "has":
        if not t:
            return None
        return 0.0 if t.lower() in ("none", "no", "—", "-", "n/a") else 1.0
    if kind.parse == "design":
        return DESIGN_RANK.get(t.lower())
    return None


def _round(x: float, step: float) -> int:
    step = step or 1
    return int(math.floor(x / step + 0.5) * step)


def line_amount(kind: "Kind", diff: float, p: "Params", building: float | None = None) -> tuple[int | None, str]:
    """One line's adjustment and its arithmetic, as words.

    ``(subject - comparable) x rate``; ``0`` when the difference is at or
    under the threshold (the building's difference on a 2-4 unit report);
    ``None`` -- nothing to write -- when there is no difference at all."""
    if not diff:
        return None, "no difference"
    gate = abs(building) if building is not None else abs(diff)
    if p.threshold and gate <= p.threshold:
        return 0, f"within the {p.threshold:,.10g} {kind.unit} threshold"
    basis = f"{diff:+,.10g} {kind.unit} \u00d7 ${p.rate:,.10g}"
    if p.rounding and p.rounding != 1:
        basis += f", rounded to {p.rounding:g}"
    return _round(diff * p.rate, p.rounding), basis


# ------------------------------------------------------------------ the grid
def subject_units(tree) -> int:
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    for prop in root.iter(f"{{{bind.MISMO}}}PROPERTY"):
        if prop.get("ValuationUseType") == "SubjectProperty":
            n = prop.findtext(f".//{{{bind.MISMO}}}LivingUnitExcludingADUCount")
            try:
                return max(1, int(float(n))) if n else 1
            except ValueError:
                return 1
    return 1


@dataclass
class _Grid:
    names: list[str]
    rows: dict[str, list]            # adjust_type -> its row instances, in unit order
    by_label: dict[str, list]
    props: list[etree._Element]


def _grid(tree) -> _Grid | None:
    grids = comparables.build(tree, "sales", per_block=99, every_row=True)
    if not grids:
        return None
    g = grids[0]
    rows: dict[str, list] = {}
    by_label: dict[str, list] = {}
    for r in g.rows:
        if r.adjust_type:
            rows.setdefault(r.adjust_type, []).append(r)
        by_label.setdefault(r.label.strip(), []).append(r)
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    props = comparables.properties(root, "SalesComparable")
    return _Grid(list(g.comparables), rows, by_label, props)


def _cell(row, i: int) -> str:
    return row.cells[i].text if i < len(row.cells) else ""


def _label_value(grid: _Grid, label: str, i: int) -> str:
    rows = grid.by_label.get(label) or []
    return _cell(rows[0], i) if rows else ""


def _price(grid: _Grid, i: int) -> tuple[float | None, float | None, bool]:
    """(sale price, list price, priced at list) for comparable i."""
    status = _label_value(grid, "Listing Status", i).lower()
    sale = _num(_label_value(grid, "Sale Price", i))
    listed = _num(_label_value(grid, "List Price", i))
    at_list = "active" in status or ("pending" in status and not sale)
    return sale, listed, at_list


def _amounts(prop, adjust_type: str) -> list[str]:
    return [(n.findtext(f"{{{bind.MISMO}}}ComparableAdjustmentAmount") or "").strip()
            for n in prop.iter(f"{{{bind.MISMO}}}COMPARABLE_ADJUSTMENT")
            if (n.findtext(f"{{{bind.MISMO}}}ComparableAdjustmentType") or "").strip() == adjust_type]


def _net(prop) -> float:
    total = 0.0
    for n in prop.iter(f"{{{bind.MISMO}}}COMPARABLE_ADJUSTMENT"):
        v = _num(n.findtext(f"{{{bind.MISMO}}}ComparableAdjustmentAmount") or "")
        total += v or 0
    return total


def available(tree) -> list[dict]:
    """The worksheets this report's grid can carry (its row is in the grid)."""
    grid = _grid(tree)
    if grid is None:
        return []
    out = []
    for k in KINDS.values():
        if k.adjust_type in grid.rows:
            out.append({"key": k.key, "title": k.title, "adjust_type": k.adjust_type,
                        "unit": k.unit, "per_unit": k.per_unit, "percent": k.percent, "note": k.note})
    return out


# --------------------------------------------------------------- the sheet
@dataclass
class Params:
    rate: float
    threshold: float = 0
    rounding: float = 100

    @classmethod
    def of(cls, kind: Kind, profile: Profile, given: dict | None = None) -> "Params":
        given = given or {}
        base = cls(getattr(profile, kind.rate, 0) or 0,
                   getattr(profile, kind.threshold, 0) if kind.threshold else 0,
                   profile.rounding or 1)

        def f(name, default):
            try:
                return float(given[name]) if name in given and given[name] not in ("", None) else default
            except (TypeError, ValueError):
                return default
        return cls(f("rate", base.rate), f("threshold", base.threshold), f("rounding", base.rounding) or 1)


#: what one rate pays for, short, for the ticked icon ("$75/sf")
SHORT = {"sq ft": "sf", "year": "yr", "bedroom": "bed", "full bath": "bath", "space": "space",
         "present": "", "basement": "", "step": "step", "% of list": "% of list"}


def rate_label(kind: Kind, rate: float) -> str:
    if kind.percent:
        return f"{rate:g}% of list"
    unit = SHORT.get(kind.unit, kind.unit)
    return f"${rate:,.10g}" + (f"/{unit}" if unit else "")


def _group_label(row, units: int) -> str:
    kind, _, n = (row.group or "").partition(" ")
    if not kind:
        return ""
    return {"unit": "Unit", "adu": "ADU", "ob": "Outbuilding", "dwelling": "Building"}.get(kind, kind.title()) + f" {n}"


def comp_key(prop) -> str:
    """A comparable told apart by its own label, not its column: a manual mark
    stays with the comparable when the comparables are reordered."""
    return prop.get("{http://www.w3.org/1999/xlink}label") or ""


def manual_key(adjust_type: str, prop, instance: int) -> str:
    return f"{adjust_type}|{comp_key(prop)}|{max(instance, 0)}"


def sheet(tree, kind_key: str, params: dict | None = None, profile: Profile | None = None,
          overrides: dict | None = None, state: dict | None = None, grid: "_Grid | None" = None) -> dict:
    """The worksheet for one grid row: subject, every comparable, the arithmetic.

    Each line carries the numbers it rests on (``s_val`` / ``c_val``) so the
    editor can preview a new rate as it is typed, and ``manual`` when the
    appraiser typed that adjustment by hand (it is never overwritten)."""
    kind = KINDS.get(kind_key)
    if kind is None:
        raise KeyError(kind_key)
    profile = profile or default_profile(tree)
    p = Params.of(kind, profile, params)
    grid = grid or _grid(tree)
    if grid is None or kind.adjust_type not in grid.rows:
        raise LookupError(f"this report's sales grid has no {kind.title} row")
    rows = grid.rows[kind.adjust_type]
    if not kind.per_unit:
        rows = rows[:1]
    units = len(rows)
    overrides = overrides or {}
    manual = (state or {}).get("manual") or {}
    subject = [{"unit": u + 1, "label": _group_label(rows[u], units), "value": rows[u].subject,
                "s_val": _parse(kind, rows[u].subject)} for u in range(units)]
    comps = []
    for i, name in enumerate(grid.names):
        prop = grid.props[i] if i < len(grid.props) else None
        sale, listed, at_list = _price(grid, i)
        price = listed if at_list else (sale or listed)
        comp = Comp(i + 1, name, price, at_list)
        diffs = []
        for u in range(units):
            s_v = _parse(kind, rows[u].subject)
            c_v = _parse(kind, _cell(rows[u], i))
            diffs.append(None if s_v is None or c_v is None else s_v - c_v)
        building = sum(d for d in diffs if d is not None)
        # the building's difference gates a 2-4 unit report's unit lines; a
        # dwelling and its ADU are gated line by line
        whole = units > 1 and all((r.group or "").startswith("unit") for r in rows)
        mine_old = 0.0
        mine_gross_old = 0.0
        for u in range(units):
            d = diffs[u]
            inst = max(rows[u].instance, 0) if kind.per_unit else 0
            cur = comparables.nth_adjustment_value(prop, kind.adjust_type, inst) if prop is not None else ""
            mine_old += _num(cur) or 0
            mine_gross_old += abs(_num(cur) or 0)
            is_manual = bool(prop is not None and manual.get(manual_key(kind.adjust_type, prop, inst)))
            label = _group_label(rows[u], units)
            s_v, c_v = _parse(kind, rows[u].subject), _parse(kind, _cell(rows[u], i))
            if kind.percent:
                amount = -_round((listed or 0) * p.rate / 100, 1) if at_list and listed else None
                basis = (f"-{p.rate:g}% of the list price ${listed:,.0f}" if at_list and listed
                         else "a settled sale: no market exposure adjustment")
                line = Line(u + 1, "", f"${listed:,.0f}" if listed else "", None, amount, cur, basis)
            elif d is None:
                line = Line(u + 1, rows[u].subject, _cell(rows[u], i), None, None, cur, "no value to compare")
            else:
                # a 2-4 unit report gates on the building's difference (adjust.multi_lines)
                amount, basis = line_amount(kind, d, p, building if whole else None)
                if amount is None and (_num(cur) or 0):
                    amount = 0                  # a stale amount is cleared; an empty row stays empty
                line = Line(u + 1, rows[u].subject, _cell(rows[u], i), d, amount, cur, basis)
            key = f"{i + 1}_{u + 1}"
            if key in overrides:
                try:
                    line.amount = int(round(float(overrides[key])))
                    line.basis = "typed by the appraiser"
                    is_manual = True
                except (TypeError, ValueError):
                    pass
            elif is_manual:
                line.amount = int(round(_num(cur) or 0)) if cur else None
                line.basis = "typed by the appraiser (manual: the worksheet leaves it as it is)"
            line_d = asdict(line)
            line_d.update(manual=is_manual, label=label, instance=inst, s_val=s_v, c_val=c_v,
                          listed=listed if kind.percent else None, at_list=at_list)
            comp.lines.append(line_d)
        new = sum(ln["amount"] for ln in comp.lines if ln["amount"] is not None)
        old_written = sum(_num(ln["current"]) or 0 for ln in comp.lines if ln["amount"] is not None)
        if prop is not None:
            others_net = _net(prop) - mine_old
            others_gross = _gross(prop) - mine_gross_old
            comp.others_net, comp.others_gross = others_net, others_gross
            comp.net_after = _net(prop) - old_written + new
            comp.gross_after = others_gross + sum(abs(ln["amount"]) if ln["amount"] is not None
                                                  else abs(_num(ln["current"]) or 0) for ln in comp.lines)
            if price:
                comp.line_pct = round(new / price * 100, 1)
                comp.adjusted = price + comp.net_after
        comps.append(comp)
    applied = ((state or {}).get("kinds") or {}).get(kind_key)
    return {"kind": asdict(kind), "params": asdict(p), "profile": profile.name,
            "rate_label": rate_label(kind, p.rate), "applied": applied,
            "subject": subject, "units": units, "comparables": [asdict(c) for c in comps],
            # the building's difference gates every line (a 2-4 unit report)
            "whole": units > 1 and all((r.group or "").startswith("unit") for r in rows)}


@dataclass
class Line:
    unit: int                       # 1-based line within the row
    subject: str
    comparable: str
    diff: float | None
    amount: int | None              # None: no comparable value, the row is left alone
    current: str                    # what the grid holds now
    basis: str


@dataclass
class Comp:
    number: int
    name: str
    price: float | None
    at_list: bool
    lines: list = field(default_factory=list)
    line_pct: float | None = None
    adjusted: float | None = None
    net_after: float | None = None
    gross_after: float | None = None
    others_net: float | None = None
    others_gross: float | None = None


def _gross(prop) -> float:
    return sum(abs(_num(n.findtext(f"{{{bind.MISMO}}}ComparableAdjustmentAmount") or "") or 0)
               for n in prop.iter(f"{{{bind.MISMO}}}COMPARABLE_ADJUSTMENT"))


# ----------------------------------------------------------------- state
# What the appraiser applied, kept with the case (worksheets.json in the case
# folder, so it travels with the bundle): per worksheet the rate, threshold and
# rounding last applied; the adjustments typed by hand; the last profile used.
STATE_FILE = "worksheets.json"


def load_state(folder) -> dict:
    import json
    from pathlib import Path
    path = Path(folder) / STATE_FILE
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save_state(folder, state: dict) -> None:
    import json
    from pathlib import Path
    (Path(folder) / STATE_FILE).write_text(json.dumps(state, indent=1, sort_keys=True), encoding="utf-8")


def mark_manual(folder, root, adjust_type: str, number: int, instance: int, on: bool) -> bool:
    """An adjustment typed by hand on a worksheet's row: kept as the
    appraiser's (cleared, the worksheet may fill it again)."""
    if adjust_type not in {k.adjust_type for k in KINDS.values()}:
        return False
    props = comparables.properties(root, "SalesComparable")
    if not 1 <= number <= len(props):
        return False
    state = load_state(folder)
    manual = state.setdefault("manual", {})
    key = manual_key(adjust_type, props[number - 1], instance)
    if on:
        manual[key] = True
    else:
        manual.pop(key, None)
    save_state(folder, state)
    return True


def release_manual(folder, root, kind_key: str, number: int, unit_instance: int) -> None:
    kind = KINDS[kind_key]
    mark_manual(folder, root, kind.adjust_type, number, unit_instance, False)


# --------------------------------------------------------------- writing
def _write_lines(tree, out: dict, adjust_type: str, state: dict, overrides: dict) -> int:
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    props = comparables.properties(root, "SalesComparable")
    manual = state.setdefault("manual", {})
    written = 0
    for comp in out["comparables"]:
        prop = props[comp["number"] - 1] if comp["number"] - 1 < len(props) else None
        if prop is None:
            continue
        for ln in comp["lines"]:
            key = f"{comp['number']}_{ln['unit']}"
            mkey = manual_key(adjust_type, prop, ln["instance"])
            if key in overrides:
                manual[mkey] = True           # typed in the panel: the appraiser's
            elif ln["manual"]:
                continue                       # never overwritten
            if ln["amount"] is None:
                continue
            new = str(int(ln["amount"]))
            if comparables.nth_adjustment_value(prop, adjust_type, ln["instance"]) != new:
                comparables.write_nth_adjustment(prop, adjust_type, ln["instance"], new)
            written += 1
    return written


def apply(tree, kind_key: str, params: dict | None = None, profile: Profile | None = None,
          overrides: dict | None = None, folder=None) -> dict:
    """What OK does: every comparable's line(s) of this row written at once.
    A line with no comparable value, or one typed by hand, is left as it is.
    With ``folder`` the worksheet is remembered, so the row recalculates when
    a subject or comparable value changes later (``recalc``)."""
    import datetime
    state = load_state(folder) if folder is not None else {}
    overrides = overrides or {}
    out = sheet(tree, kind_key, params, profile, overrides, state)
    kind = KINDS[kind_key]
    out["written"] = _write_lines(tree, out, kind.adjust_type, state, overrides)
    if folder is not None:
        kinds = state.setdefault("kinds", {})
        # one grid row, one worksheet: the other worksheet writing the same row
        # (finished area below grade per sq ft vs present / none) stops
        for other in list(kinds):
            if other != kind_key and KINDS.get(other) and KINDS[other].adjust_type == kind.adjust_type:
                kinds.pop(other)
        kinds[kind_key] = {"rate": out["params"]["rate"], "threshold": out["params"]["threshold"],
                           "rounding": out["params"]["rounding"], "profile": out["profile"],
                           "label": out["rate_label"],
                           "at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds")}
        if profile is not None:
            state["profile"] = profile.to_json()
        save_state(folder, state)
        out["applied"] = kinds[kind_key]
    return out


def adjust_all(tree, profile: Profile, folder=None) -> dict:
    """Every worksheet whose rate the profile carries, applied in one go."""
    done, skipped = [], []
    for k in available(tree):
        kind = KINDS[k["key"]]
        if kind.key == "below_fin" and profile.basement and not profile.below_fin:
            skipped.append({"key": kind.key, "why": "the profile adjusts finished basements as present/none"})
            continue
        if kind.key == "basement" and profile.below_fin:
            skipped.append({"key": kind.key, "why": "the profile adjusts finished basements per sq ft"})
            continue
        if not getattr(profile, kind.rate, 0):
            skipped.append({"key": kind.key, "why": "not in the profile"})
            continue
        res = apply(tree, kind.key, None, profile, folder=folder)
        done.append({"key": kind.key, "written": res["written"]})
    return {"profile": profile.name, "applied": done, "skipped": skipped}


def recalc(tree, folder) -> list[dict]:
    """Every applied worksheet worked out again on the document as it now
    stands -- after a subject or comparable value changed -- and its lines
    rewritten, except the ones typed by hand. Returns the cells that moved."""
    import datetime
    state = load_state(folder)
    kinds = state.get("kinds") or {}
    if not kinds:
        return []
    grid = _grid(tree)
    if grid is None:
        return []
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    props = comparables.properties(root, "SalesComparable")
    moved = []
    for key, saved in kinds.items():
        kind = KINDS.get(key)
        if kind is None or kind.adjust_type not in grid.rows:
            continue
        prof = profile_from(state.get("profile") or {"name": saved.get("profile", "")}, tree)
        out = sheet(tree, key, {"rate": saved.get("rate"), "threshold": saved.get("threshold"),
                                "rounding": saved.get("rounding")}, prof, None, state, grid)
        for comp in out["comparables"]:
            prop = props[comp["number"] - 1] if comp["number"] - 1 < len(props) else None
            if prop is None:
                continue
            for ln in comp["lines"]:
                if ln["manual"] or ln["amount"] is None:
                    continue
                new = str(int(ln["amount"]))
                old = comparables.nth_adjustment_value(prop, kind.adjust_type, ln["instance"])
                if old != new:
                    comparables.write_nth_adjustment(prop, kind.adjust_type, ln["instance"], new)
                    moved.append({"kind": key, "adjust_type": kind.adjust_type, "comp": comp["number"],
                                  "instance": ln["instance"], "old": old, "new": new})
    if moved:
        state["recalc"] = {"at": datetime.datetime.now(datetime.timezone.utc).isoformat(timespec="seconds"),
                           "cells": [{k: m[k] for k in ("adjust_type", "comp", "instance")} for m in moved]}
        save_state(folder, state)
    return moved


def marks(tree, folder) -> dict:
    """What the report's grid shows beside its rows: which rows have a
    worksheet, which are applied and at what rate, and per adjustment cell its
    arithmetic (the hover) and whether it was typed by hand."""
    state = load_state(folder)
    grid = _grid(tree)
    rows, cells = {}, {}
    if grid is None:
        return {"rows": rows, "cells": cells, "recalc": state.get("recalc")}
    for kind in KINDS.values():
        if kind.adjust_type not in grid.rows:
            continue
        applied = (state.get("kinds") or {}).get(kind.key)
        cur = rows.get(kind.adjust_type)
        if cur is None or applied:
            rows[kind.adjust_type] = {"kind": kind.key, "title": kind.title,
                                      "applied": bool(applied),
                                      "label": (applied or {}).get("label", "")}
        if not applied:
            continue
        prof = profile_from(state.get("profile") or {"name": applied.get("profile", "")}, tree)
        out = sheet(tree, kind.key, {"rate": applied.get("rate"), "threshold": applied.get("threshold"),
                                     "rounding": applied.get("rounding")}, prof, None, state, grid)
        for comp in out["comparables"]:
            for ln in comp["lines"]:
                cells[f"{kind.adjust_type}|{comp['number']}|{ln['instance']}"] = {
                    "basis": ln["basis"], "manual": ln["manual"], "kind": kind.key}
    # a value typed by hand on a row no worksheet has filled yet is still the
    # appraiser's: marked, so the worksheet leaves it when it is applied
    by_label = {comp_key(p): n for n, p in enumerate(grid.props, 1) if p is not None}
    for key, on in (state.get("manual") or {}).items():
        adjust_type, _, rest = key.partition("|")
        label, _, inst = rest.rpartition("|")
        number = by_label.get(label)
        if on and number and adjust_type in rows:
            cells.setdefault(f"{adjust_type}|{number}|{inst}", {
                "basis": "typed by the appraiser", "manual": True, "kind": rows[adjust_type]["kind"]})
    return {"rows": rows, "cells": cells, "recalc": state.get("recalc"),
            "profile": (state.get("profile") or {}).get("name")}
