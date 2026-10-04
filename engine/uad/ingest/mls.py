"""Parser for OneKey MLS residential listing sheets."""
from __future__ import annotations

import re
from dataclasses import dataclass, field, asdict
from typing import Any

from .labeled_text import LabeledText, baths, date, integer, money, number

# First line of a sheet: "<street>, <city>, <state> <zip>, <county> County"
_HEADER = re.compile(
    r"^\s*(?P<street>[^,]+),\s*(?P<city>[^,]+),\s*(?P<state>[A-Za-z ]+)\s+"
    r"(?P<zip>\d{5}(?:-\d{4})?),\s*(?P<county>[^,]+?)(?:\s+County)?\s*$"
)

STATE_CODES = {"new york": "NY", "connecticut": "CT", "new jersey": "NJ"}


@dataclass
class Listing:
    """One MLS listing: the subject or a comparable."""

    source_page: int | None = None
    mls_number: str | None = None
    street: str | None = None
    city: str | None = None
    state: str | None = None
    postal_code: str | None = None
    county: str | None = None
    village: str | None = None
    township: str | None = None

    status: str | None = None
    list_price: float | None = None
    sale_price: float | None = None
    days_on_market: int | None = None

    property_subtype: str | None = None
    architectural_style: str | None = None
    year_built: int | None = None
    gla_reported: float | None = None
    gla_source: str | None = None
    building_area_total: float | None = None

    bedrooms: int | None = None
    baths_full: int | None = None
    baths_half: int | None = None
    rooms_total: int | None = None
    levels: str | None = None

    lot_acres: float | None = None
    lot_sqft: float | None = None
    waterfront: str | None = None

    basement: str | None = None
    attic: str | None = None
    fireplace: str | None = None
    garage_spaces: float | None = None
    parking: str | None = None
    pool: str | None = None
    patio_porch: str | None = None

    construction: str | None = None
    heating: str | None = None
    cooling: str | None = None
    sewer: str | None = None
    water: str | None = None
    utilities: str | None = None

    interior_features: str | None = None
    appliances: str | None = None
    flooring: str | None = None

    school_district: str | None = None
    tax_id: str | None = None
    taxes_annual: float | None = None
    tax_year: int | None = None

    # From the "Listing/Contract Info" continuation page.
    listing_contract_date: str | None = None
    on_market_date: str | None = None
    contract_date: str | None = None
    close_date: str | None = None
    close_price: float | None = None
    orig_list_price: float | None = None
    seller_concessions: float | None = None
    buyer_financing: str | None = None
    special_listing_conditions: str | None = None

    list_office: str | None = None
    list_agent: str | None = None
    public_remarks: str | None = None

    raw: dict[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v not in (None, "", {})}

    @property
    def address(self) -> str:
        parts = [self.street, self.city, f"{self.state} {self.postal_code}".strip()]
        return ", ".join(p for p in parts if p)

    @property
    def closed(self) -> bool:
        return (self.status or "").lower() == "sold"


# Labels whose values may run across several lines.
_BLOCK_LABELS = (
    "Interior:", "Appliances:", "Flooring:", "Parking:", "Construction:",
    "Utilities:", "Heating:", "Cooling:", "Sewer:", "Water:", "Basement:",
    "Attic:", "Fireplace:", "Pool:", "Patio/Porch Feat:", "Foundation:",
    "Elem Sch Dist:", "Tax ID#:", "Taxes Annual:", "List Office:", "List Agent:",
)


def parse(text: str, *, page: int | None = None) -> Listing | None:
    """Parse one MLS sheet.  Returns None if the text isn't a listing sheet."""
    doc = LabeledText.from_text(text)
    listing = Listing(source_page=page)

    header = next((ln for ln in doc.lines if ln), "")
    if m := _HEADER.match(header):
        listing.street = m.group("street").strip()
        listing.city = m.group("city").strip()
        state = m.group("state").strip()
        listing.state = STATE_CODES.get(state.lower(), state[:2].upper())
        listing.postal_code = m.group("zip")
        listing.county = m.group("county").strip()

    listing.mls_number = doc.find("MLS#")
    if not listing.mls_number:
        return None

    listing.status = doc.find("Status")
    listing.list_price = money(doc.find("List Price") or doc.find("Price"))
    listing.sale_price = money(doc.find("Sold Price"))
    if dom := doc.find("DOM/CDOM"):
        listing.days_on_market = integer(dom.split("/")[0])

    listing.property_subtype = doc.find("Sub Type")
    listing.architectural_style = doc.find("Architect. Style")
    listing.year_built = integer(doc.find("Yr Built"))
    listing.levels = doc.find("Levels in Unit/Home")
    listing.village = doc.find("Village")
    listing.township = doc.find("City/Township")

    if gla := doc.find("Taxable Living Area (GLA)"):
        listing.gla_reported = number(gla)
        # "3,400 Public Records" -> remember who said so.
        listing.gla_source = re.sub(r"^[\d,]+\s*", "", gla).strip() or None
    listing.building_area_total = number(doc.find("Building Area Total Sqft"))

    listing.bedrooms = integer(doc.find("Bedrooms"))
    if b := baths(doc.find("Baths")):
        listing.baths_full, listing.baths_half = b
    listing.rooms_total = integer(doc.find("Rooms Total"))

    listing.lot_acres = number(doc.find("Acre(s)"))
    listing.lot_sqft = number(doc.find("Lot Size SqFt"))
    listing.waterfront = doc.find("Waterfront")

    for attr, label in [
        ("basement", "Basement"), ("attic", "Attic"), ("fireplace", "Fireplace"),
        ("parking", "Parking"), ("pool", "Pool"), ("patio_porch", "Patio/Porch Feat"),
        ("construction", "Construction"), ("heating", "Heating"),
        ("cooling", "Cooling"), ("sewer", "Sewer"), ("water", "Water"),
        ("utilities", "Utilities"), ("interior_features", "Interior"),
        ("appliances", "Appliances"), ("flooring", "Flooring"),
        ("list_office", "List Office"), ("list_agent", "List Agent"),
    ]:
        setattr(listing, attr, doc.find(label, stop_labels=_BLOCK_LABELS))

    if garage := doc.find("Garage/Spaces"):
        listing.garage_spaces = number(garage.split("/")[-1])

    listing.school_district = doc.find("Elem Sch Dist")
    listing.tax_id = doc.find("Tax ID#")
    listing.taxes_annual = money(doc.find("Taxes Annual"))
    listing.tax_year = integer(doc.find("Tax Year"))

    listing.listing_contract_date = date(doc.find("Listing Contract Date"))
    listing.on_market_date = date(doc.find("On Market Date"))
    listing.contract_date = date(doc.find("Contract Date"))
    listing.close_date = date(doc.find("Close Date"))
    listing.close_price = money(doc.find("Close Price"))
    listing.orig_list_price = money(doc.find("Orig List Price"))
    listing.seller_concessions = money(doc.find("Seller Concessions"))
    listing.buyer_financing = doc.find("Buyer Financing")
    listing.special_listing_conditions = doc.find("Special Listing Conditions")

    # The header price and the contract block should agree; prefer the block.
    listing.sale_price = listing.close_price or listing.sale_price

    listing.public_remarks = _remarks(doc)
    return listing


def _remarks(doc: LabeledText) -> str | None:
    """Everything between the 'Public Remarks' heading and the next section."""
    try:
        start = doc.lines.index("Public Remarks") + 1
    except ValueError:
        return None
    out: list[str] = []
    for line in doc.lines[start:]:
        if line in ("Interior Features", "Exterior Features", "Systems & Utilities"):
            break
        if line:
            out.append(line)
    return " ".join(out) or None
