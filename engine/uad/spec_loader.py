"""Load the UAD 3.6 delivery spec, enumerations and compliance rules into
indexed, queryable form.  Everything downstream (the editable UI, the XML
generator and the validator) is driven from here rather than hand-coded.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import cached_property
from pathlib import Path

SPEC_DIR = Path(__file__).resolve().parent.parent / "spec"

ROLE_COLUMNS = {
    "subject": "Subject Property",
    "land_comp": "Land Comparable",
    "not_used": "Property Analyzed Not Used",
    "rental_comp": "Rental Comparable",
    "grm_comp": "Gross Rent Multiplier Comparable",
    "sales_comp": "Sales Comparable",
}

# "2.057: Assignment Information - Contact Information - Property Data Report - Reference ID"
_LOCATION_RE = re.compile(r"^\s*(?P<fid>[\d.]+)\s*:\s*(?P<rest>.+)$", re.S)


@dataclass(frozen=True)
class ReportLocation:
    """One place a data point surfaces on the printed report."""

    field_id: str
    section: str
    subsection: str
    label: str

    @property
    def sort_key(self) -> tuple:
        return tuple(int(p) if p.isdigit() else 0 for p in self.field_id.split("."))

    @classmethod
    def parse(cls, raw: str) -> "ReportLocation | None":
        m = _LOCATION_RE.match(raw.strip())
        if not m:
            return None
        parts = [p.strip() for p in m.group("rest").split(" - ")]
        if len(parts) < 2:
            return None
        section, subsection, *label_parts = parts
        if not label_parts:  # "Section - Label" form, no subsection given
            subsection, label_parts = "{No Subsection}", [subsection]
        if subsection == "{No Subsection}":
            subsection = ""
        return cls(m.group("fid"), section, subsection, " - ".join(label_parts))


@dataclass
class Field:
    """A single UAD data point or XML attribute."""

    unique_id: str
    sort_number: int
    xpath: str
    container: str
    data_point: str
    attribute: str
    definition: str
    format_type: str
    format_details: str
    conditionality: str
    conditionality_details: str
    cardinality: str
    notes: str
    locations: list[ReportLocation] = field(default_factory=list)
    roles: set[str] = field(default_factory=set)

    @property
    def name(self) -> str:
        """Element name, or attribute name without its leading '@'."""
        return self.data_point or self.attribute.lstrip("@")

    @property
    def is_attribute(self) -> bool:
        return bool(self.attribute) and not self.data_point

    @property
    def required(self) -> bool:
        return self.conditionality == "R"

    @property
    def displayed(self) -> bool:
        return bool(self.locations)


@dataclass
class Enumeration:
    data_point: str
    value: str
    display: str
    definition: str
    roles: set[str]


class Rule(dict):
    """A compliance rule row; dict-like for flexible access."""

    @property
    def id(self) -> str:
        return self["Message ID"]

    @property
    def fatal(self) -> bool:
        return self["Severity"] == "Fatal"


class UADSpec:
    def __init__(self, spec_dir: Path = SPEC_DIR):
        self.spec_dir = Path(spec_dir)
        self._raw_fields = self._load("delivery_spec.json")
        self._raw_enums = self._load("enumerations.json")
        self._raw_rules = self._load("compliance_rules.json")

    def _load(self, name: str) -> list[dict]:
        with open(self.spec_dir / name, encoding="utf-8") as fh:
            return json.load(fh)

    # ---------------------------------------------------------------- fields
    @cached_property
    def fields(self) -> list[Field]:
        out: list[Field] = []
        for row in self._raw_fields:
            if not (row.get("MISMO Data Point Name") or row.get("MISMO Attribute Name")):
                continue  # pure container row
            locs = [
                loc
                for line in row["Report Location"].splitlines()
                if (loc := ReportLocation.parse(line))
            ]
            roles = {
                key
                for key, col in ROLE_COLUMNS.items()
                if row.get(col, "").strip().lower() == "x"
            }
            out.append(
                Field(
                    unique_id=row.get("Unique ID", ""),
                    sort_number=int(row["XML Sort Number"] or 0),
                    xpath=row["MISMO xPath"],
                    container=row.get("MISMO Parent Container", ""),
                    data_point=row.get("MISMO Data Point Name", ""),
                    attribute=row.get("MISMO Attribute Name", ""),
                    definition=row.get("MISMO Data Point / Attribute Definition", ""),
                    format_type=row.get("UAD Data Point Format Type", ""),
                    format_details=row.get("UAD Data Point Format Details", ""),
                    conditionality=row.get("Conditionality", ""),
                    conditionality_details=row.get("Conditionality Details", ""),
                    cardinality=row.get("Cardinality", ""),
                    notes=row.get("Implementation Notes", ""),
                    locations=locs,
                    roles=roles,
                )
            )
        return out

    @cached_property
    def containers(self) -> list[dict]:
        return [
            r
            for r in self._raw_fields
            if not (r.get("MISMO Data Point Name") or r.get("MISMO Attribute Name"))
        ]

    @cached_property
    def sort_order(self) -> dict[str, int]:
        """xPath + name -> XML Sort Number, used to emit children in schema order."""
        order: dict[str, int] = {}
        for row in self._raw_fields:
            key = row["MISMO xPath"] + (
                row.get("MISMO Data Point Name") or row.get("MISMO Attribute Name") or ""
            )
            order.setdefault(key, int(row["XML Sort Number"] or 0))
        return order

    @cached_property
    def by_data_point(self) -> dict[str, list[Field]]:
        idx: dict[str, list[Field]] = {}
        for f in self.fields:
            idx.setdefault(f.name, []).append(f)
        return idx

    @cached_property
    def by_field_id(self) -> dict[str, tuple[Field, ReportLocation]]:
        """Report field ID (e.g. '22.01.18') -> the field that populates it."""
        idx: dict[str, tuple[Field, ReportLocation]] = {}
        for f in self.fields:
            for loc in f.locations:
                idx.setdefault(loc.field_id, (f, loc))
        return idx

    # ------------------------------------------------------------- structure
    @cached_property
    def sections(self) -> dict[str, dict[str, list[tuple[Field, ReportLocation]]]]:
        """section -> subsection -> [(field, location)], all in field-ID order."""
        tree: dict[str, dict[str, list]] = {}
        for f in self.fields:
            for loc in f.locations:
                tree.setdefault(loc.section, {}).setdefault(loc.subsection, []).append(
                    (f, loc)
                )
        for subs in tree.values():
            for items in subs.values():
                items.sort(key=lambda pair: pair[1].sort_key)
        return tree

    # ---------------------------------------------------------- enumerations
    @cached_property
    def enumerations(self) -> dict[str, list[Enumeration]]:
        idx: dict[str, list[Enumeration]] = {}
        for row in self._raw_enums:
            name = row["MISMO Data Point / Attribute Name"]
            display = next(
                (v for k, v in row.items() if k.startswith("Output Report Display Text")),
                "",
            )
            idx.setdefault(name, []).append(
                Enumeration(
                    data_point=name,
                    value=row["Supported Enumerations"],
                    display=display,
                    definition=row.get("Supported Enumerations Definitions", ""),
                    roles={
                        k
                        for k, c in ROLE_COLUMNS.items()
                        if row.get(c, "").strip().lower() == "x"
                    },
                )
            )
        return idx

    def allowed_values(self, data_point: str) -> list[str]:
        return [e.value for e in self.enumerations.get(data_point, [])]

    def display_text(self, data_point: str, value: str) -> str:
        for e in self.enumerations.get(data_point, []):
            if e.value == value:
                return e.display or e.value
        return value

    # ----------------------------------------------------------------- rules
    @cached_property
    def rules(self) -> list[Rule]:
        return [Rule(r) for r in self._raw_rules]

    @cached_property
    def rules_by_data_point(self) -> dict[str, list[Rule]]:
        idx: dict[str, list[Rule]] = {}
        for r in self.rules:
            idx.setdefault(r["Primary Data Element"], []).append(r)
        return idx


_spec: UADSpec | None = None


def load() -> UADSpec:
    """Process-wide singleton; the spec is read-only."""
    global _spec
    if _spec is None:
        _spec = UADSpec()
    return _spec
