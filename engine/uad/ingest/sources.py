"""Consolidate an appraisal packet into a single set of source facts.

Every property fact reaches us from more than one place — the MLS sheet, the
assessor record, and the appraiser's own inspection — and they disagree.  This
module resolves each field by a fixed precedence and records every disagreement
it resolved, so the appraiser reviews the conflicts rather than discovering
them after delivery.

Precedence, highest first:
    1. the appraiser's inspection and ANSI measurements
    2. the MLS listing
    3. the assessor / data-vendor record
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import mls, packet, property_report
from .labeled_text import LabeledText, integer, money, number

CONFIG_DIR = Path(__file__).resolve().parent.parent.parent / "config"

INSPECTION = "inspection"
MLS = "mls"
PUBLIC_RECORD = "public_record"
PRECEDENCE = (INSPECTION, MLS, PUBLIC_RECORD)


@dataclass
class Resolved:
    """One fact, the value chosen, and what every source claimed."""

    field: str
    value: Any
    source: str
    claims: dict[str, Any] = field(default_factory=dict)

    @property
    def conflicted(self) -> bool:
        distinct = {_comparable(v) for v in self.claims.values() if v is not None}
        return len(distinct) > 1


def _comparable(value: Any) -> Any:
    """Loose equality so 3112 and 3112.0 and ' 3112 ' don't read as conflicts."""
    if isinstance(value, (int, float)):
        return round(float(value), 2)
    if isinstance(value, str):
        return value.strip().lower()
    return value


def resolve(field_name: str, **claims: Any) -> Resolved:
    """Pick the highest-precedence non-null claim for one field."""
    for source in PRECEDENCE:
        value = claims.get(source)
        if value not in (None, ""):
            return Resolved(field_name, value, source, claims)
    return Resolved(field_name, None, "none", claims)


# ------------------------------------------------------------------- market
@dataclass
class MarketStudy:
    median_sale_price_total: float | None = None
    median_sale_price_current: float | None = None
    median_sale_price_prior_4_6: float | None = None
    median_sale_price_prior_7_12: float | None = None
    sales_current_3: int | None = None
    sales_prior_4_6: int | None = None
    sales_prior_7_12: int | None = None
    sales_total: int | None = None
    absorption_rate_total: float | None = None
    high_sale_price: float | None = None
    low_sale_price: float | None = None
    average_sale_price: float | None = None
    search_criteria: str | None = None
    date_range: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


def parse_market_study(text: str) -> MarketStudy:
    doc = LabeledText.from_text(text)
    study = MarketStudy()

    # The 1004MC grid prints four numbers per row: 7-12, 4-6, current, total.
    for i, line in enumerate(doc.lines):
        values = [v for v in doc.lines[i + 1 : i + 5] if v]
        if line.startswith("Total # of Comparable Sales") and "w/o" not in line:
            nums = [integer(v) for v in values[:4]]
            if len(nums) == 4:
                (study.sales_prior_7_12, study.sales_prior_4_6,
                 study.sales_current_3, study.sales_total) = nums
        elif line.startswith("Median Comparable Sale Price"):
            nums = [money(v) for v in values[:4]]
            if len(nums) == 4:
                (study.median_sale_price_prior_7_12, study.median_sale_price_prior_4_6,
                 study.median_sale_price_current, study.median_sale_price_total) = nums
        elif line.startswith("Absorption Rate"):
            nums = [number(v) for v in values[:4]]
            if len(nums) == 4:
                study.absorption_rate_total = nums[3]

    study.high_sale_price = money(doc.find_bare("High Sale Price"))
    study.low_sale_price = money(doc.find_bare("Low Sale Price"))
    study.average_sale_price = money(doc.find_bare("Average Sale Price"))
    study.search_criteria = doc.find_bare("Location")

    for line in doc.lines:
        if "sale date range of" in line:
            study.date_range = line.split("sale date range of")[-1].strip()
            break
    return study


# -------------------------------------------------------------------- order
def parse_order(text: str) -> dict[str, Any]:
    doc = LabeledText.from_text(text)
    keys = {
        "order_number": "Order Number",
        "property_address": "Property Address",
        "county": "Property County",
        "property_type": "Property Type",
        "client": "Client",
        "loan_type": "Loan Type",
        "loan_number": "Loan Number",
        "transaction_type": "Transaction Type",
        "product": "Product",
        "borrower_name": "Borrower Name",
        "due_date": "Order Due Date",
        "amc_registration": "AMC Reg. Number",
        "contact_name": "Name",
    }
    out = {name: doc.find(label) for name, label in keys.items()}
    out["appraiser_fee"] = money(doc.find("Total Vendor's Fee"))
    out["technology_fee"] = money(doc.find("Technology Fee"))
    out["net_fee"] = money(doc.find("Net Vendor's Fee"))
    out["client_address"] = doc.find(
        "Client Address", stop_labels=("Vendor:", "Order Priority:")
    )
    return {k: v for k, v in out.items() if v not in (None, "")}


# ------------------------------------------------------------------ bundle
@dataclass
class SourceFacts:
    order: dict[str, Any] = field(default_factory=dict)
    contract: dict[str, Any] = field(default_factory=dict)
    appraiser: dict[str, Any] = field(default_factory=dict)
    inspection: dict[str, Any] = field(default_factory=dict)
    subject: dict[str, Any] = field(default_factory=dict)
    comparables: list[dict[str, Any]] = field(default_factory=list)
    market: dict[str, Any] = field(default_factory=dict)
    conflicts: list[dict[str, Any]] = field(default_factory=list)
    documents: list[dict[str, Any]] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "order": self.order,
            "contract": self.contract,
            "appraiser": self.appraiser,
            "inspection": self.inspection,
            "subject": self.subject,
            "comparables": self.comparables,
            "market": self.market,
            "conflicts": self.conflicts,
            "gaps": self.gaps,
            "documents": self.documents,
        }


def _load_config(name: str) -> dict[str, Any]:
    path = CONFIG_DIR / name
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _match_record(
    listing: mls.Listing, records: list[property_report.PropertyRecord]
) -> property_report.PropertyRecord | None:
    """Pair an MLS sheet with its assessor record by street number and name."""
    if not listing.street:
        return None
    key = listing.street.lower().split()
    number_token = key[0] if key else ""
    name_token = key[1][:4].lower() if len(key) > 1 else ""
    for record in records:
        addr = (record.address or "").lower()
        if addr.startswith(number_token) and name_token and name_token in addr:
            return record
    return None


def _property_facts(
    listing: mls.Listing,
    record: property_report.PropertyRecord | None,
    inspection: dict[str, Any] | None,
) -> tuple[dict[str, Any], list[Resolved]]:
    """Merge the sources for one property and return facts plus resolutions."""
    rec = record or property_report.PropertyRecord()
    areas = (inspection or {}).get("areas", {})
    above = (inspection or {}).get("above_grade", {})

    resolutions = [
        resolve("gla_sqft", inspection=areas.get("gla_sqft"),
                mls=listing.gla_reported, public_record=rec.gla),
        resolve("year_built", mls=listing.year_built, public_record=rec.year_built),
        resolve("bedrooms", inspection=above.get("bedrooms"), mls=listing.bedrooms),
        resolve("baths_full", inspection=above.get("baths_full"),
                mls=listing.baths_full, public_record=rec.baths_full),
        resolve("baths_half", inspection=above.get("baths_half"),
                mls=listing.baths_half, public_record=rec.baths_half),
        resolve("rooms_total", inspection=above.get("rooms_total"),
                mls=listing.rooms_total, public_record=rec.rooms),
        resolve("lot_acres", mls=listing.lot_acres or None, public_record=rec.lot_acres),
        resolve("architectural_style", mls=listing.architectural_style,
                public_record=(rec.style or "").title() or None),
        resolve("basement_sqft", inspection=areas.get("basement_sqft")),
    ]

    facts = {
        "address": {
            "line": listing.street, "city": listing.city, "state": listing.state,
            "postal_code": listing.postal_code, "county": listing.county,
            "village": listing.village, "township": listing.township,
        },
        "mls": listing.as_dict(),
        "public_record": rec.as_dict(),
        "resolved": {r.field: {"value": r.value, "source": r.source} for r in resolutions},
    }
    return facts, resolutions


def build(pdf_path: str | Path, *, config_dir: Path = CONFIG_DIR) -> SourceFacts:
    """Read a packet and everything configured alongside it into source facts."""
    global CONFIG_DIR
    CONFIG_DIR = Path(config_dir)

    documents = packet.split(pdf_path)
    facts = SourceFacts()
    facts.documents = [
        {"type": d.doc_type.value, "pages": [d.first_page, d.last_page], "title": d.title}
        for d in documents
    ]

    facts.appraiser = _load_config("appraiser.json")
    facts.inspection = _load_config("inspection.json")
    facts.contract = _load_config("contract.json")

    listings = [
        (d, parsed)
        for d in documents
        if d.doc_type is packet.DocType.MLS_LISTING
        and (parsed := mls.parse(d.text, page=d.first_page))
    ]
    records = [
        property_report.parse(d.text, page=d.first_page, address=d.title)
        for d in documents
        if d.doc_type is packet.DocType.PROPERTY_REPORT
    ]

    for d in documents:
        if d.doc_type is packet.DocType.ORDER:
            facts.order.update(parse_order(d.text))
        elif d.doc_type is packet.DocType.MARKET_STUDY:
            facts.market = parse_market_study(d.text).as_dict()

    subject_street = (facts.order.get("property_address") or "").lower()
    all_resolutions: list[tuple[str, Resolved]] = []

    for index, (document, listing) in enumerate(listings):
        record = _match_record(listing, records)
        first_token = (listing.street or "").split()[0].lower() if listing.street else ""
        is_subject = bool(first_token) and first_token in subject_street and index == 0

        data, resolutions = _property_facts(
            listing, record, facts.inspection if is_subject else None
        )
        data["source_pages"] = [document.first_page, document.last_page]

        label = "subject" if is_subject else f"comparable_{len(facts.comparables) + 1}"
        all_resolutions += [(label, r) for r in resolutions]

        if is_subject:
            facts.subject = data
        else:
            facts.comparables.append(data)

    facts.conflicts = [
        {
            "property": label,
            "field": r.field,
            "chosen": r.value,
            "source": r.source,
            "claims": {k: v for k, v in r.claims.items() if v is not None},
        }
        for label, r in all_resolutions
        if r.conflicted
    ]
    facts.gaps = _find_gaps(facts)
    return facts


def _find_gaps(facts: SourceFacts) -> list[str]:
    """Facts UAD requires that the packet simply does not contain."""
    gaps: list[str] = []
    if (facts.order.get("transaction_type") or "").lower() == "purchase":
        if not facts.contract.get("purchase_price"):
            gaps.append(
                "Contract price for the subject purchase is missing; the contract of "
                "sale is a scanned image, so it must be transcribed into "
                "config/contract.json"
            )
        elif facts.contract.get("seller_concessions") is None:
            gaps.append(
                "Seller concessions are not stated in the contract of sale; confirm "
                "with the listing agent before completing the Sales Contract section"
            )
    if not facts.market:
        gaps.append("No 1004MC / market study found in the packet")
    for i, comp in enumerate(facts.comparables, 1):
        if not comp.get("mls", {}).get("close_date") and comp.get("mls", {}).get("status") != "Active":
            gaps.append(f"Comparable {i} has no close date")
    return gaps
