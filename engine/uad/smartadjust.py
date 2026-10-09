"""SmartAdjust: sales grid adjustments suggested from the owner's rate profile.

WinTOTAL suggests adjustments from rates ("SmartAdjust").  Here the rates are
the owner's own standing profiles (``_work/GOAL.md``, "Adjustments use the 18
North parameters"; the multi-family profile of 2026-10-02).  The 18 North rates
were read out of the delivered 18 North report's grid -- each adjustment
divided by the difference it rests on:

    GLA               $75 / sq ft      325 sq ft -> +24,375
    site              $10 / sq ft      past a 1,000 sq ft difference (871 -> 0)
    age               $250 / year      past a 5 year difference (33 -> +8,250)
    bedroom           $10,000
    bathroom          $5,000 per half bath (1.5 vs 1.0 -> +5,000)
    finished basement $10,000          present vs none, both ways
    garage            $10,000 / space  driveway or none counts 0 spaces
    outdoor living    $10,000          a deck, patio or porch vs none
    market exposure   2 % of list      on a listing (or a pending sale
                                       carried at its list price)

A rate a profile does not carry (condition, quality, location, ...) is the
appraiser's to set, and nothing is suggested for it.

What is compared is what the grid prints (``report/comparables.build``): the
subject's value and each comparable's, row by row, so every suggestion can
show its own arithmetic.  A row repeated per unit (2-4 units) is summed over
the units, because the property carries one adjustment of each type.

Suggestions are never written by themselves: the appraiser sees each one
beside the adjustment already in the grid and accepts it or not
(``POST /api/cases/{id}/smartadjust``).  Sign convention as on the form: the
adjustment is applied to the comparable, so a comparable inferior to the
subject is adjusted upward.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field, replace
from typing import Any

from .report import comparables

SQFT_PER_ACRE = 43_560


@dataclass
class Profile:
    name: str
    gla: float = 75                  # $ per sq ft of finished area above grade
    gla_threshold: float = 0         # adjust only past this difference (sq ft)
    site: float = 10                 # $ per sq ft of site
    site_threshold: float = 1000
    age: float = 250                 # $ per year built
    age_threshold: float = 5
    bedroom: float = 10_000
    half_bath: float = 5_000         # a full bath is two halves
    basement: float = 10_000         # finished area below grade, present vs none
    garage: float = 10_000           # per garage space
    outdoor: float = 10_000          # deck / patio / porch vs none
    exposure: float = 0.02           # of list price, on a listing
    design: float = 0                # attached / semi-detached / detached step (0: not in profile)
    cooling: float = 0               # a cooling system vs none (0: not in profile)
    source: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


EIGHTEEN_NORTH = Profile(
    name="18 North",
    source="_work/GOAL.md: the owner's standing rates, read from the delivered 18 North grid (2026-09-29)")

MULTI_FAMILY = Profile(
    name="Multi-family", gla=150, gla_threshold=100, site=20, site_threshold=1000,
    age=250, age_threshold=30, bedroom=20_000, half_bath=10_000, basement=40_000,
    garage=20_000, outdoor=20_000, exposure=0.02, design=20_000, cooling=20_000,
    source="the owner's multi-family rates for every 2-4 unit report (2026-10-02)")

PROFILES = {p.name: p for p in (EIGHTEEN_NORTH, MULTI_FAMILY)}
RATE_KEYS = [k for k in Profile.__dataclass_fields__ if k not in ("name", "source")]

#: semi-detached sits between attached and detached: one step is one design rate
DESIGN_RANK = {"attached": 0, "semi-detached": 1, "semidetached": 1, "detached": 2}
_NUM = re.compile(r"-?\d[\d,]*(?:\.\d+)?|-?\.\d+")


def profile_for(tree, name: str = "", rates: dict | None = None) -> Profile:
    """The named profile, else the one the report's kind takes: multi-family
    on a 2-4 unit report, 18 North otherwise.  ``rates`` overrides single
    rates for this calculation (the appraiser's own, for this report)."""
    p = PROFILES.get(name) or (MULTI_FAMILY if _units(tree) > 1 else EIGHTEEN_NORTH)
    if rates:
        clean = {}
        for k, v in rates.items():
            if k in RATE_KEYS:
                try:
                    clean[k] = float(v)
                except (TypeError, ValueError):
                    continue
        p = replace(p, **clean)
    return p


def _units(tree) -> int:
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    for prop in root.iter("{*}PROPERTY"):
        if prop.get("ValuationUseType") == "SubjectProperty":
            n = prop.findtext(".//{*}LivingUnitExcludingADUCount")
            try:
                return int(float(n)) if n else 1
            except ValueError:
                return 1
    return 1


def _num(text: str) -> float | None:
    m = _NUM.search(text or "")
    return float(m.group().replace(",", "")) if m else None


def _area(text: str) -> float | None:
    """'14,950 Sq. Ft.' -> 14950; '2.5 Acres' -> 108900."""
    n = _num(text)
    if n is None:
        return None
    return n * SQFT_PER_ACRE if re.search(r"\bac(re)?s?\b", text or "", re.I) else n


def _baths(text: str) -> float | None:
    """'3 | 1' (full | half) -> 3.5."""
    parts = [p.strip() for p in (text or "").split("|")]
    full = _num(parts[0]) if parts and parts[0] else None
    half = _num(parts[1]) if len(parts) > 1 and parts[1] else None
    if full is None and half is None:
        return None
    return (full or 0) + 0.5 * (half or 0)


def _garage_spaces(text: str) -> float:
    """Garage spaces in a vehicle storage cell ('Garage | 2 | Attached',
    one line per item); a driveway or carport adds none."""
    total = 0.0
    for line in re.split(r"[\n;]+", text or ""):
        cells = [c.strip() for c in line.split("|")]
        if cells and "garage" in cells[0].lower() and len(cells) > 1:
            total += _num(cells[1]) or 0
    return total


def _has(text: str) -> bool:
    t = (text or "").strip().lower()
    return bool(t) and t not in ("none", "no", "—", "-", "n/a")


@dataclass
class Line:
    adjust_type: str
    label: str
    subject: str
    comparable: str
    amount: int
    basis: str
    current: str = ""

    def to_json(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Column:
    number: int
    name: str
    lines: list[Line] = field(default_factory=list)

    @property
    def net(self) -> int:
        return sum(ln.amount for ln in self.lines)

    def to_json(self) -> dict[str, Any]:
        return {"number": self.number, "name": self.name, "net": self.net,
                "gross": sum(abs(ln.amount) for ln in self.lines),
                "lines": [ln.to_json() for ln in self.lines]}


def _rows(tree):
    grids = comparables.build(tree, "sales", per_block=99, every_row=True)
    return grids[0] if grids else None


def suggest(tree, profile: Profile) -> list[Column]:
    """Each sales comparable's suggested adjustments under this profile."""
    grid = _rows(tree)
    if grid is None:
        return []
    n = len(grid.comparables)
    by_type: dict[str, list] = {}
    by_label: dict[str, list] = {}
    for r in grid.rows:
        if r.adjust_type:
            by_type.setdefault(r.adjust_type, []).append(r)
        by_label.setdefault(r.label.strip(), []).append(r)
    cols = [Column(i + 1, name) for i, name in enumerate(grid.comparables)]

    def texts(rows, i):
        """(subject texts, comparable i texts) over every instance of a row."""
        return ([r.subject for r in rows], [r.cells[i].text if i < len(r.cells) else "" for r in rows])

    def current(adjust_type, i):
        for r in by_type.get(adjust_type, []):
            if r.adjustable and i < len(r.cells) and r.cells[i].adjustment:
                return r.cells[i].adjustment
        return ""

    def add(i, adjust_type, label, s, c, amount, basis):
        if adjust_type not in by_type:
            return                      # the grid has no such row to carry it
        cols[i].lines.append(Line(adjust_type, label, s, c, int(round(amount)), basis,
                                  current(adjust_type, i)))

    p = profile
    for i in range(n):
        # finished area above grade (summed over units)
        rows_ = by_type.get("LivingUnitStandardFinishedAreaAboveGrade", [])
        s_t, c_t = texts(rows_, i)
        s_v = [_area(t) for t in s_t if _area(t) is not None]
        c_v = [_area(t) for t in c_t if _area(t) is not None]
        if s_v and c_v and p.gla:
            d = sum(s_v) - sum(c_v)
            amt = d * p.gla if abs(d) > p.gla_threshold else 0
            add(i, "LivingUnitStandardFinishedAreaAboveGrade", "Finished Area Above Grade",
                f"{sum(s_v):,.0f} sq ft", f"{sum(c_v):,.0f} sq ft", amt,
                f"{d:+,.0f} sq ft × ${p.gla:,.0f}" if amt else "no difference" if not d else
                f"{d:+,.0f} sq ft is within the {p.gla_threshold:,.0f} sq ft threshold")
        # site
        s_t, c_t = texts(by_type.get("SiteSize", []), i)
        s_a = next((_area(t) for t in s_t if _area(t) is not None), None)
        c_a = next((_area(t) for t in c_t if _area(t) is not None), None)
        if s_a is not None and c_a is not None and p.site:
            d = s_a - c_a
            amt = d * p.site if abs(d) > p.site_threshold else 0
            add(i, "SiteSize", "Site Size", f"{s_a:,.0f} sq ft", f"{c_a:,.0f} sq ft", amt,
                f"{d:+,.0f} sq ft × ${p.site:,.2f}" if amt else "no difference" if not d else
                f"{d:+,.0f} sq ft is within the {p.site_threshold:,.0f} sq ft threshold")
        # age
        s_t, c_t = texts(by_type.get("YearBuilt", []), i)
        s_y = next((_num(t) for t in s_t if _num(t)), None)
        c_y = next((_num(t) for t in c_t if _num(t)), None)
        if s_y and c_y and p.age:
            d = s_y - c_y
            amt = d * p.age if abs(d) > p.age_threshold else 0
            add(i, "YearBuilt", "Year Built", f"{s_y:.0f}", f"{c_y:.0f}", amt,
                f"{d:+.0f} years × ${p.age:,.0f}" if amt else "no difference" if not d else
                f"{d:+.0f} years is within the {p.age_threshold:.0f} year threshold")
        # bedrooms (summed over units)
        s_t, c_t = texts(by_type.get("LivingUnitBedroomCount", []), i)
        s_b = [_num(t) for t in s_t if _num(t) is not None]
        c_b = [_num(t) for t in c_t if _num(t) is not None]
        if s_b and c_b and p.bedroom:
            d = sum(s_b) - sum(c_b)
            add(i, "LivingUnitBedroomCount", "Bedrooms", f"{sum(s_b):.0f}", f"{sum(c_b):.0f}",
                d * p.bedroom, f"{d:+.0f} × ${p.bedroom:,.0f}" if d else "no difference")
        # bathrooms, in half baths (summed over units)
        s_t, c_t = texts(by_type.get("LivingUnitBathroomCount", []), i)
        s_h = [_baths(t) for t in s_t if _baths(t) is not None]
        c_h = [_baths(t) for t in c_t if _baths(t) is not None]
        if s_h and c_h and p.half_bath:
            halves = round((sum(s_h) - sum(c_h)) / 0.5)
            add(i, "LivingUnitBathroomCount", "Baths", f"{sum(s_h):g}", f"{sum(c_h):g}",
                halves * p.half_bath, f"{halves:+d} half baths × ${p.half_bath:,.0f}" if halves else "no difference")
        # finished area below grade: present vs none
        s_t, c_t = texts(by_type.get("LivingUnitStandardFinishedAreaBelowGrade", []), i)
        s_f = [_area(t) for t in s_t if _area(t) is not None]
        c_f = [_area(t) for t in c_t if _area(t) is not None]
        if s_f and c_f and p.basement:
            s_has, c_has = sum(s_f) > 0, sum(c_f) > 0
            add(i, "LivingUnitStandardFinishedAreaBelowGrade", "Finished Area Below Grade",
                "finished" if s_has else "none", "finished" if c_has else "none",
                (int(s_has) - int(c_has)) * p.basement,
                "same" if s_has == c_has else f"{'+' if s_has else '−'}${p.basement:,.0f} for a finished basement")
        # vehicle storage: garage spaces
        spaces = by_label.get("Type| Spaces | Detail", [])
        if spaces and p.garage:
            s_t, c_t = texts(spaces, i)
            s_g, c_g = sum(_garage_spaces(t) for t in s_t), sum(_garage_spaces(t) for t in c_t)
            if any(s_t) and any(c_t):
                d = s_g - c_g
                add(i, "VehicleStorage", "Vehicle Storage", f"{s_g:g} garage", f"{c_g:g} garage",
                    d * p.garage, f"{d:+g} spaces × ${p.garage:,.0f}" if d else "no difference")
        # outdoor living: any vs none
        s_t, c_t = texts(by_type.get("OutdoorLivingAmenity", []), i)
        if (s_t or c_t) and p.outdoor:
            s_o, c_o = any(_has(t) for t in s_t), any(_has(t) for t in c_t)
            add(i, "OutdoorLivingAmenity", "Outdoor Living", s_t[0] if s_t else "", c_t[0] if c_t else "",
                (int(s_o) - int(c_o)) * p.outdoor,
                "both or neither have one" if s_o == c_o else
                f"{'+' if s_o else '−'}${p.outdoor:,.0f} for a deck, patio or porch")
        # market exposure on a listing
        status = (texts(by_label.get("Listing Status", []), i)[1] or [""])[0].lower()
        sale = _num((texts(by_label.get("Sale Price", []), i)[1] or [""])[0])
        listed = _num((texts(by_label.get("List Price", []), i)[1] or [""])[0])
        if p.exposure and listed and ("active" in status or ("pending" in status and not sale)):
            add(i, "SaleToListPriceRatio", "Sale to List Price Ratio", "", f"listed ${listed:,.0f}",
                -listed * p.exposure, f"−{p.exposure * 100:g}% of the list price (market exposure)")
        # multi-family only: design and cooling
        if p.design:
            s_t, c_t = texts(by_type.get("AttachedOrDetached", []), i)
            rs = DESIGN_RANK.get((s_t[0] if s_t else "").strip().lower())
            rc = DESIGN_RANK.get((c_t[0] if c_t else "").strip().lower())
            if rs is not None and rc is not None:
                add(i, "AttachedOrDetached", "Attached/Detached", s_t[0], c_t[0],
                    (rs - rc) * p.design, f"{rs - rc:+d} steps × ${p.design:,.0f}" if rs != rc else "no difference")
        if p.cooling:
            s_t, c_t = texts(by_type.get("CoolingSystem", []), i)
            if s_t or c_t:
                s_c, c_c = any(_has(t) for t in s_t), any(_has(t) for t in c_t)
                add(i, "CoolingSystem", "Cooling", s_t[0] if s_t else "", c_t[0] if c_t else "",
                    (int(s_c) - int(c_c)) * p.cooling,
                    "same" if s_c == c_c else f"{'+' if s_c else '−'}${p.cooling:,.0f} for cooling")
    return cols

