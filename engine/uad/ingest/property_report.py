"""Parser for ATTOM/assessor property reports.

These supply the public-record facts the MLS does not: APN and legal
identifiers, zoning, flood zone and panel, census tract, site dimensions,
assessed value and the full transfer history — all of which UAD requires.
"""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from typing import Any

from .labeled_text import LabeledText, date, integer, money, number


@dataclass
class Transfer:
    """One row of the recorded sales history."""

    sale_date: str | None = None
    recording_date: str | None = None
    buyer: str | None = None
    seller: str | None = None
    price: float | None = None


@dataclass
class PropertyRecord:
    source_page: int | None = None
    address: str | None = None

    apn: str | None = None
    legal_section: str | None = None
    legal_block: str | None = None
    legal_lot: str | None = None
    fips: str | None = None
    census_tract: str | None = None
    municipality: str | None = None
    township: str | None = None
    school_district: str | None = None

    flood_zone: str | None = None
    flood_panel: str | None = None
    flood_panel_date: str | None = None
    flood_description: str | None = None

    assessed_value: float | None = None
    assessor_market_value: float | None = None

    lot_acres: float | None = None
    lot_dimensions: str | None = None
    waterfront: str | None = None
    street_type: str | None = None
    traffic: str | None = None
    topography: str | None = None
    location_factor: str | None = None
    zoning_code: str | None = None
    zoning_description: str | None = None

    building_class: str | None = None
    style: str | None = None
    gla: float | None = None
    stories: float | None = None
    year_built: int | None = None
    rooms: int | None = None
    baths_full: int | None = None
    baths_half: int | None = None
    basement: str | None = None
    attic: str | None = None
    exterior_wall: str | None = None
    heating_type: str | None = None
    fuel_type: str | None = None
    garage_attached: int | None = None
    garage_detached: int | None = None
    condition: str | None = None

    transfers: list[Transfer] = field(default_factory=list)
    avm_value: float | None = None

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["transfers"] = [
            {k: v for k, v in t.items() if v is not None} for t in data["transfers"]
        ]
        return {k: v for k, v in data.items() if v not in (None, "", [], {})}


# Every caption these reports print, so a blank field returns None instead of
# swallowing the next caption as its value.
CAPTIONS = frozenset({
    "Legal ID", "Section", "Block", "Lot", "Lot Group", "Building/Unit", "APN",
    "FIPS", "ATTOM ID", "Municipality", "Township", "Energy Standard",
    "School District", "Census Number", "Census Tract", "Ownership", "Flood",
    "Zone", "Panel", "Panel Date", "Community", "FEMA Flood Map",
    "Assessed Value", "Assessor’s Value", "Assessor's Value", "Soundscore",
    "Pedestrian", "Vehicle", "Airports", "Overall Soundscore",
    "Land Information", "Acres", "Lot Dimensions", "Waterfront",
    "Location Information", "Street Type", "Traffic", "Topography",
    "Location Factor", "Fronting Factor", "Zoning",
    "Residential Building and Interior", "Building Class", "Style", "GLA",
    "Height (Stories)", "Year Built", "Rooms", "Full Baths", "Baths Half",
    "Rec Room Area", "Basement", "Fin Basement Area", "Attic", "Fireplaces",
    "Exterior Wall", "Heating Type", "Fuel Type", "Garages", "Attached",
    "Detached", "Condition", "Improvements", "Description", "Area", "Grade",
    "Sales History", "Sale Date", "Rec Date", "Buyer", "Seller", "Sale Price",
    "Liber", "Page", "Property Info", "Property Report", "Comparables",
})

_ZONING = re.compile(r"^\s*(?P<code>[A-Z0-9\-]{1,10})\s*$")
_TRANSFER = re.compile(
    r"(?P<sale>\d{2}/\d{2}/\d{4})\s*\n(?P<rec>\d{2}/\d{2}/\d{4})\s*\n"
    r"(?P<buyer>.+?)\s*\n(?P<seller>.+?)\s*\n\$(?P<price>[\d,]+)",
)


def parse(text: str, *, page: int | None = None, address: str | None = None) -> PropertyRecord:
    doc = LabeledText.from_text(text)
    rec = PropertyRecord(source_page=page, address=address)

    rec.legal_section = doc.find_bare(captions=CAPTIONS, label="Section")
    rec.legal_block = doc.find_bare(captions=CAPTIONS, label="Block")
    rec.legal_lot = doc.find_bare(captions=CAPTIONS, label="Lot")
    rec.apn = doc.find_bare(captions=CAPTIONS, label="APN")
    rec.fips = doc.find_bare(captions=CAPTIONS, label="FIPS")
    rec.census_tract = doc.find_bare(captions=CAPTIONS, label="Census Tract")
    rec.municipality = doc.find_bare(captions=CAPTIONS, label="Municipality")
    rec.township = doc.find_bare(captions=CAPTIONS, label="Township")
    rec.school_district = doc.find_bare(captions=CAPTIONS, label="School District")

    rec.flood_zone = doc.find_bare(captions=CAPTIONS, label="Zone")
    rec.flood_panel = doc.find_bare(captions=CAPTIONS, label="Panel")
    rec.flood_panel_date = doc.find_bare(captions=CAPTIONS, label="Panel Date")
    rec.flood_description = doc.find_bare(captions=CAPTIONS, label="Community")

    rec.assessed_value = number(doc.find_bare(captions=CAPTIONS, label="Assessed Value"))
    rec.assessor_market_value = money(doc.find_bare(captions=CAPTIONS, label="Assessor’s Value") or doc.find_bare(captions=CAPTIONS, label="Assessor's Value"))

    rec.lot_acres = number(doc.find_bare(captions=CAPTIONS, label="Acres"))
    rec.lot_dimensions = doc.find_bare(captions=CAPTIONS, label="Lot Dimensions")
    rec.waterfront = doc.find_bare(captions=CAPTIONS, label="Waterfront")
    rec.street_type = doc.find_bare(captions=CAPTIONS, label="Street Type")
    rec.traffic = doc.find_bare(captions=CAPTIONS, label="Traffic")
    rec.topography = doc.find_bare(captions=CAPTIONS, label="Topography")
    rec.location_factor = doc.find_bare(captions=CAPTIONS, label="Location Factor")

    if zoning := doc.find_bare(captions=CAPTIONS, label="Zoning"):
        rec.zoning_code = zoning if _ZONING.match(zoning) else None
        rec.zoning_description = doc.find_bare(captions=CAPTIONS, label="Zoning", skip=1)

    rec.building_class = doc.find_bare(captions=CAPTIONS, label="Building Class")
    rec.style = doc.find_bare(captions=CAPTIONS, label="Style")
    rec.gla = number(doc.find_bare(captions=CAPTIONS, label="GLA"))
    rec.stories = number(doc.find_bare(captions=CAPTIONS, label="Height (Stories)"))
    rec.year_built = integer(doc.find_bare(captions=CAPTIONS, label="Year Built"))
    rec.rooms = integer(doc.find_bare(captions=CAPTIONS, label="Rooms"))
    rec.baths_full = integer(doc.find_bare(captions=CAPTIONS, label="Full Baths"))
    rec.baths_half = integer(doc.find_bare(captions=CAPTIONS, label="Baths Half"))
    rec.basement = doc.find_bare(captions=CAPTIONS, label="Basement")
    rec.attic = doc.find_bare(captions=CAPTIONS, label="Attic")
    rec.exterior_wall = doc.find_bare(captions=CAPTIONS, label="Exterior Wall")
    rec.heating_type = doc.find_bare(captions=CAPTIONS, label="Heating Type")
    rec.fuel_type = doc.find_bare(captions=CAPTIONS, label="Fuel Type")
    rec.garage_attached = integer(doc.find_bare(captions=CAPTIONS, label="Attached"))
    rec.garage_detached = integer(doc.find_bare(captions=CAPTIONS, label="Detached"))
    rec.condition = doc.find_bare(captions=CAPTIONS, label="Condition")

    rec.avm_value = money(doc.find_bare(captions=CAPTIONS, label="Estimated Value From ATTOM AVM"))
    rec.transfers = _transfers(text)
    return rec


def _transfers(text: str) -> list[Transfer]:
    """Recorded transfers, most recent first."""
    out: list[Transfer] = []
    for m in _TRANSFER.finditer(text):
        out.append(
            Transfer(
                sale_date=date(m.group("sale")),
                recording_date=date(m.group("rec")),
                buyer=m.group("buyer").strip(),
                seller=m.group("seller").strip(),
                price=float(m.group("price").replace(",", "")),
            )
        )
    return out
