"""What an appraiser types, turned into what the document stores.

Appraisers type the way they speak: "2352", "2,352 sf", "1.5 acres",
"$515k", "8/17/19".  A-1 says what each data point holds -- its format type
(Amount, Numeric, Date), its precision (``+6.0``, ``+9.2``) and, for measures,
the unit attribute and the units it may carry (``@AreaUnitOfMeasureType``:
SquareFeet, Acres ...).  So the typing is accepted as it comes and stored as
the specification defines it; the report then prints the unit and the symbols
("2,352 Sq. Ft.", "$515,000", "08/17/2019") from the stored value, and nobody
types "Sq. Ft." again.
"""
from __future__ import annotations

import re
from datetime import date

# words an appraiser uses for a unit -> the A-1 enumeration value
UNIT_WORDS = [
    (r"sq\.?\s*ft\.?|square\s*f(ee|oo)t|sqft|sf|ft2|ft²", "SquareFeet"),
    (r"sq\.?\s*m\.?|square\s*met(er|re)s?|sqm|m2|m²", "SquareMeters"),
    (r"acres?|ac\.?", "Acres"),
    (r"hectares?|ha\.?", "Hectares"),
    (r"cu\.?\s*ft\.?|cubic\s*f(ee|oo)t|cf|ft3", "CubicFeet"),
    (r"miles?|mi\.?", "Miles"),
    (r"kilomet(er|re)s?|km\.?", "Kilometers"),
    (r"feet|foot|ft\.?|'", "Feet"),
    (r"met(er|re)s?|m\.?", "Meters"),
]
# B-1 p350: Total Depreciation is delivered "as a positive number" and only
# printed negative -- "$(9,000)" typed back from the report stays 9000
POSITIVE_ONLY = {"DepreciationTotalAmount"}
# when nothing is typed and A-1 allows several units, the one US appraisals use
PREFERRED = ("SquareFeet", "Miles", "Feet", "CubicFeet")


def _unit_in(text: str, allowed: list[str]) -> tuple[str, str]:
    """(the text without its unit word, the A-1 unit it named or '')."""
    for pattern, value in UNIT_WORDS:
        if allowed and value not in allowed:
            continue
        m = re.search(rf"(?<![A-Za-z])({pattern})\s*$", text, re.I)
        if m:
            return text[:m.start()].strip(), value
    return text, ""


def _number(text: str, places: int | None) -> str | None:
    t = text.strip().replace(",", "").replace("$", "").replace(" ", "")
    negative = t.startswith("(") and t.endswith(")")
    t = t.strip("()")
    scale = 1
    if re.fullmatch(r"-?\d+(\.\d+)?[kK]", t):
        scale, t = 1000, t[:-1]
    elif re.fullmatch(r"-?\d+(\.\d+)?[mM]", t):
        scale, t = 1_000_000, t[:-1]
    t = t.rstrip("%")
    if not re.fullmatch(r"[+-]?\d+(\.\d+)?|[+-]?\.\d+", t):
        return None
    value = float(t) * scale * (-1 if negative else 1)
    # A-1's precision is the most decimals allowed, not a fixed width: the
    # samples store 491000 and 121.25, never 491000.00
    value = round(value, places if places is not None else 10)
    shown = f"{value:.{places if places is not None else 10}f}"
    return shown.rstrip("0").rstrip(".") if "." in shown else shown


def _places(details: str) -> int | None:
    m = re.search(r"\.(\d+)", details or "")
    return int(m.group(1)) if m else None


def _precision(details: str) -> str:
    """A-1 states a date's precision in its format details: YYYY-MM-DD for a
    day, YYYY-MM for a month (a lease start), YYYY for a year (Year Built)."""
    d = (details or "").upper().replace(" ", "")
    if "DD" in d:
        return "day"
    if "MM" in d:
        return "month"
    if "YYYY" in d:
        return "year"
    return "day"


def _century(yr: int) -> int:
    if yr >= 100:
        return yr
    return yr + (2000 if yr <= (date.today().year % 100) + 1 else 1900)


def _date(text: str, details: str) -> str | None:
    """A typed date, stored at exactly the precision A-1 gives the data point.

    The parts are read first and the stored form is chosen by precision after.
    Before, a bare "1998" was never a date -- so Year Built, on the subject and
    on every comparable, could not be saved -- and a full date typed into a
    month-only field was stored as typed, which the schema rejects.
    """
    t = text.strip()
    want = _precision(details)
    yr = mo = dy = None

    if m := re.fullmatch(r"(\d{4})-(\d{1,2})-(\d{1,2})", t):
        yr, mo, dy = int(m.group(1)), int(m.group(2)), int(m.group(3))
    elif m := re.fullmatch(r"(\d{4})-(\d{1,2})", t):
        yr, mo = int(m.group(1)), int(m.group(2))
    elif m := re.fullmatch(r"(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2}|\d{4})", t):
        mo, dy, yr = int(m.group(1)), int(m.group(2)), _century(int(m.group(3)))
    elif m := re.fullmatch(r"(\d{1,2})[/\-.](\d{4})", t):
        mo, yr = int(m.group(1)), int(m.group(2))
    elif m := re.fullmatch(r"(\d{4})", t):
        yr = int(m.group(1))
    else:
        return None

    if not 1600 <= yr <= date.today().year + 50:
        return None
    if mo is not None and not 1 <= mo <= 12:
        return None
    if dy is not None:
        try:
            date(yr, mo, dy)
        except (TypeError, ValueError):
            return None

    if want == "year":
        return f"{yr:04d}"
    if want == "month":
        return f"{yr:04d}-{mo:02d}" if mo is not None else None
    return f"{yr:04d}-{mo:02d}-{dy:02d}" if dy is not None else None


def date_example(details: str) -> str:
    return {"year": "1998", "month": "09/2026"}.get(_precision(details), "09/20/2026")


def unit_attribute(dp: dict) -> str:
    """The attribute a value's unit of measure is stored in, or ''.

    A-1's attribute column carries two different things.  Seventy-three data
    points name a unit -- @AreaUnitOfMeasureType, @LinearUnitOfMeasureType,
    @VolumeUnitOfMeasureType -- which is where "2,352 sq ft" keeps its unit.
    Three Boolean indicators name @xlink:label, which is their container's link
    identity, not a unit.  Treating that as a unit crashed the write (lxml
    rejects a prefixed attribute name) on questions as basic as Prior Sales or
    Transfers, and a Yes could otherwise have relabelled the container and
    broken the relationships that point at it.
    """
    name = (dp.get("attribute") or "").lstrip("@")
    return name if name.endswith("UnitOfMeasureType") else ""


def normalize(dp: dict, value: str, current_unit: str = "") -> tuple[str, str]:
    """(the value to store, the unit attribute to set or '').

    A number or a date that cannot be read is refused with a message saying
    what was expected: stored as typed it would make the document invalid
    against the schema ("$" in an amount), which is a fatal finding the
    appraiser would only meet at delivery.
    """
    text = (value or "").strip()
    if not text:
        return "", ""
    kind = (dp.get("format_type") or "").strip().casefold()
    details = dp.get("format_details") or ""
    unit = ""
    attribute = unit_attribute(dp)
    allowed = [e.get("value") for e in dp.get("enumerations") or [] if attribute and e.get("value")]

    if attribute:
        text, unit = _unit_in(text, allowed)
        if not unit:
            if current_unit and (not allowed or current_unit in allowed):
                unit = current_unit
            elif len(allowed) == 1:
                unit = allowed[0]
            else:
                unit = next((u for u in PREFERRED if u in allowed), allowed[0] if allowed else "")

    if kind in ("amount", "numeric"):
        number = _number(text, _places(details))
        if number is None:
            what = "an amount, e.g. 1,250" if kind == "amount" else "a number, e.g. 1,250"
            raise ValueError(f"\"{value.strip()}\" is not {what}. No changes were saved.")
        if dp.get("mismo") in POSITIVE_ONLY:
            number = number.lstrip("-")
        return number, unit
    if kind == "date":
        date = _date(text, details)
        if not date:
            what = {"year": "a year", "month": "a month and year"}.get(_precision(details), "a date")
            raise ValueError(f"\"{value.strip()}\" is not {what}, e.g. {date_example(details)}. "
                             "No changes were saved.")
        return date, unit
    if kind == "boolean":
        low = text.casefold()
        if low in ("y", "yes", "true", "t", "1", "x"):
            return "true", unit
        if low in ("n", "no", "false", "f", "0"):
            return "false", unit
    return text, unit
