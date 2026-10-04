"""Sales comparison adjustments on a rate profile, written the way TOTAL keeps them.

The owner's standing profile is **18 North** (2026-09-29): the delivered 18 North
report states no rate paragraph, so each rate was read out of its grid -- the
adjustment amount divided by the subject/comparable difference it rests on
(`_work/reference/urar_18_north/mismo.xml`):

    GLA              $75 / sq ft      325 sq ft -> +24,375
    site             $10 / sq ft      -12,197 sq ft -> -121,830; an 871 sq ft
                                      difference was left unadjusted
    age              $250 / year      33 years -> +8,250; 4-5 years -> 0
    bedroom          $10,000          4 vs 3 -> +10,000
    bathroom         $5,000 per half  1.5 vs 1.0 -> +5,000
    finished basement $10,000         present vs none, both ways
    garage           $10,000 / space  2 vs 1 -> -10,000; driveway vs 1 -> +10,000
    outdoor living   $10,000          none vs porch -> +10,000; deck/patio -> 0
    market exposure  2 % of list      on a listing (or a pending sale carried
                                      at its list price)

Not in the profile and therefore not adjusted: cooling, condition, quality,
style, location.  A rate the profile does not carry is the appraiser's to set.

The owner's **multi-family** profile (2026-10-02, every 2-4 unit report):

    GLA              $150 / sq ft     only when the difference exceeds 100 sq ft
    site             $20 / sq ft      only when the difference exceeds 1,000 sq ft
    age              $250 / year      only when the difference exceeds 30 years
    bedroom          $20,000          full bath $20,000; half bath $10,000
    design           $20,000          semi-detached vs attached / detached
    cooling          $20,000          an HVAC cooling system vs none
    garage           $20,000 / space
    finished basement $40,000         a full finished basement (the owner's
                                      list also names $20,000 -- read as a
                                      partially finished one; not modelled
                                      until a case has one)
    outdoor living   $20,000          deck / patio / porch / balcony / pool
    market exposure  2 % of list      on a listing

A threshold gates the whole difference: past it, all of it is adjusted.

Writing: amounts go in as "$(5,100)" / "$7,750" / "$0" (a raw number never
reaches the export), then the rows holding values are re-shown and TOTAL's own
calculation re-sums the nets -- its net silently omits rows that are hidden
(E-038).  Returns each comparable's net as TOTAL computed it, so a mismatch with
the line sum is visible, not assumed away.
"""
from __future__ import annotations

from dataclasses import dataclass, field

from . import reconcile, rtv
from .formkit import money


@dataclass
class Profile:
    name: str = "18 North"
    gla: float = 75
    gla_threshold: float = 0
    site: float = 10
    site_threshold: float = 1000
    age: float = 250
    age_threshold: float = 5
    bedroom: float = 10_000
    half_bath: float = 5_000
    basement: float = 10_000
    garage: float = 10_000
    outdoor: float = 10_000
    exposure: float = 0.02
    design: float = 0                 # 0 = not in the profile: no row written
    cooling: float = 0
    source: str = "_work/reference/urar_18_north (rates read from its grid)"


EIGHTEEN_NORTH = Profile()

MULTI_FAMILY = Profile(
    name="multi-family", gla=150, gla_threshold=100, site=20, site_threshold=1000,
    age=250, age_threshold=30, bedroom=20_000, half_bath=10_000, basement=40_000,
    garage=20_000, outdoor=20_000, exposure=0.02, design=20_000, cooling=20_000,
    source="owner's multi-family rates, 2026-10-02")

PROFILES = {p.name: p for p in (EIGHTEEN_NORTH, MULTI_FAMILY)}

#: semi-detached sits between attached and detached; one step = one design rate
DESIGN_RANK = {"Attached": 0, "Semi-Detached": 1, "Detached": 2}


@dataclass
class Property:
    """What the profile compares.  `listing` = priced at a list price
    (active listing, or a pending sale whose contract price is not disclosed)."""
    gla: float
    site: float
    year: int
    beds: int
    baths: float                      # full + 0.5 * half
    basement_finished: bool
    garage: int                       # spaces; 0 for driveway / none
    outdoor: bool                     # deck, patio or porch
    price: float = 0
    listing: bool = False
    design: str = ""                  # Attached / Semi-Detached / Detached
    cooling: bool = False             # an HVAC cooling system is present


def lines(subject: Property, comp: Property, p: Profile = EIGHTEEN_NORTH) -> dict[str, int]:
    """TOTAL grid row -> signed amount for one comparable."""
    s, c = subject, comp
    dsite = s.site - c.site
    dage = s.year - c.year
    dgla = s.gla - c.gla
    out = {
        "UNITS_SF_GLA_ADJ": round(dgla * p.gla) if abs(dgla) > p.gla_threshold else 0,
        "ST_SITSIZE_ADJ": round(dsite * p.site) if abs(dsite) > p.site_threshold else 0,
        "YR_BLT_ADJ": round(dage * p.age) if abs(dage) > p.age_threshold else 0,
        "BEDS_ADJ": round((s.beds - c.beds) * p.bedroom),
        "BATHS_ADJ": round(round((s.baths - c.baths) / 0.5) * p.half_bath),
        "UNITS_SF_GLA_BELOW_GRD_ADJ": round((int(s.basement_finished) - int(c.basement_finished)) * p.basement),
        "VEHICLE_STORAGE_ADJ": round((s.garage - c.garage) * p.garage),
        "AMENITY_OUTDOOR_LIVING_ADJ": round((int(s.outdoor) - int(c.outdoor)) * p.outdoor),
        "SP_TO_LP_RATIO_ADJ": -round(c.price * p.exposure) if c.listing else 0,
    }
    if p.design:
        rs, rc = DESIGN_RANK.get(s.design), DESIGN_RANK.get(c.design)
        out["DWELL_DESIGN_ADJ"] = round((rs - rc) * p.design) if None not in (rs, rc) else 0
    if p.cooling:
        out["DWELL_COOL_ADJ"] = round((int(s.cooling) - int(c.cooling)) * p.cooling)
    return out


@dataclass
class Unit:
    """One living unit, for a 2-4 unit grid (TOTAL rows instance = unit - 1)."""
    gla: float
    beds: int
    baths: float                      # full + 0.5 * half
    basement_finished: bool = False   # finished below-grade area carried on this unit's row


#: grid rows that a 2-4 unit report keeps per unit (instance = unit - 1)
UNIT_ROWS = ("UNITS_SF_GLA_ADJ", "BEDS_ADJ", "BATHS_ADJ", "UNITS_SF_GLA_BELOW_GRD_ADJ")


def unit_lines(subject: list[Unit], comp: list[Unit], p: Profile = EIGHTEEN_NORTH,
               gla_gate: bool = True) -> dict[str, int]:
    """The profile's GLA / bedroom / bath / finished-basement lines unit by unit
    ("ROW#i").  Summed over the units they equal `lines()` on the totals, so a
    multi-unit grid carries the same adjustment as the building would.
    `gla_gate`: the building's GLA difference passed the profile's threshold
    (the threshold is the building's, not each unit's)."""
    out = {}
    for i, (s, c) in enumerate(zip(subject, comp)):
        out[f"UNITS_SF_GLA_ADJ#{i}"] = round((s.gla - c.gla) * p.gla) if gla_gate else 0
        out[f"BEDS_ADJ#{i}"] = round((s.beds - c.beds) * p.bedroom)
        out[f"BATHS_ADJ#{i}"] = round(round((s.baths - c.baths) / 0.5) * p.half_bath)
        out[f"UNITS_SF_GLA_BELOW_GRD_ADJ#{i}"] = round((int(s.basement_finished) - int(c.basement_finished)) * p.basement)
    return out


def multi_lines(subject: Property, comp: Property, su: list[Unit], cu: list[Unit],
                p: Profile = EIGHTEEN_NORTH) -> dict[str, int]:
    """Building rows from `lines()`, the unit rows replaced by `unit_lines()`."""
    base = {k: v for k, v in lines(subject, comp, p).items() if k not in UNIT_ROWS}
    gate = abs(sum(u.gla for u in su) - sum(u.gla for u in cu)) > p.gla_threshold
    return {**base, **unit_lines(su, cu, p, gate)}


@dataclass
class Result:
    table: dict[int, dict[str, int]] = field(default_factory=dict)
    nets_by_total: dict[int, str] = field(default_factory=dict)

    def net(self, n: int) -> int:
        return sum(self.table[n].values())

    def gross(self, n: int) -> int:
        return sum(abs(v) for v in self.table[n].values())


def compute(subject: Property, comps: dict[int, Property], p: Profile = EIGHTEEN_NORTH) -> Result:
    return Result(table={n: lines(subject, c, p) for n, c in comps.items()})


def write(report, result: Result) -> Result:
    """Write every line, re-show rows with data, re-sum through TOTAL."""
    def cell(n, row, v):
        name, _, inst = row.partition("#")          # "BEDS_ADJ#2" -> unit 3's row
        return {"field": f"GC{n}_{name}", "instance": int(inst or 0), "value": money(v)}
    writes = [cell(n, row, v) for n, t in result.table.items() for row, v in t.items()]
    rtv.put(report, writes)
    report.goto("sales-comp", settle=1.2)
    reconcile.show_rows_with_data(report)
    recalc = reconcile.recalculate(report)
    for row in recalc.get("net_adjustments") or []:
        result.nets_by_total[int(row["comp"])] = row["after"]
    return result


def weighted(adjusted: dict[int, float], weights: dict[int, float], round_to: int = 5000) -> tuple[float, int]:
    """Weighted indication and the value rounded to `round_to`."""
    total = sum(weights.values())
    ind = sum(adjusted[n] * w for n, w in weights.items()) / total
    return ind, int(round(ind / round_to) * round_to)
