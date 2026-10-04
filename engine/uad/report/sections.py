"""Build the whole report from the delivery specification.

Appendix A-1 already defines every field the URAR can print: its Report Field
ID, the section and subsection it belongs to, its label, its order, its MISMO
xPath and its data point.  That registry — not hand-written section code — is
the authority for what the report contains.

Each field is resolved by walking the report model at the field's own xPath, so
a section prints exactly the fields the spec places in it, in Field ID order,
and only those for which the report actually has data.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from .. import model as model_mod
from .. import spec_loader

# The report's own section order, as published (B-1 p29-31).
SECTION_ORDER = [
    "Summary",
    "Assignment Information",
    "Subject Property",
    "Site",
    "Disaster Mitigation",
    "Energy Efficient and Green Features",
    "Sketch",
    "Dwelling Exterior",
    "Manufactured Home",
    "Unit Interior",
    "Functional Obsolescence",
    "Outbuilding",
    "Vehicle Storage",
    "Subject Property Amenities",
    "Overall Quality and Condition",
    "Highest and Best Use",
    "Market",
    "Project Information",
    "Subject Listing Information",
    "Sales Contract",
    "Prior Sale and Transfer History",
    "Sales Comparison Approach",
    "Rental Information",
    "Income Approach",
    "Cost Approach",
    "Reconciliation",
    "Revision History",
    "Supplemental Information",
    "Certifications",
]

# Sections that always print, whether or not the packet supplies data (B-1 p29-31).
ALWAYS_PRESENT = {
    "Summary", "Assignment Information", "Subject Property", "Site", "Sketch",
    "Dwelling Exterior", "Functional Obsolescence", "Vehicle Storage",
    "Subject Property Amenities", "Overall Quality and Condition",
    "Highest and Best Use", "Market", "Subject Listing Information",
    "Prior Sale and Transfer History", "Reconciliation", "Certifications",
}

# Sections handled by purpose-built renderers rather than the field registry.
SPECIAL = {"Sales Comparison Approach"}

# Sections the guide starts on a fresh page.
NEW_PAGE = {"Assignment Information", "Sales Comparison Approach",
            "Supplemental Information", "Certifications"}


@dataclass
class Field:
    """One labelled value, located by its Report Field ID."""

    field_id: str
    label: str
    value: Any
    data_point: str
    required: bool = False
    format_type: str = ""
    column: str = "left"          # which page column Appendix E places it in

    @property
    def sort_key(self) -> tuple:
        return tuple(int(p) if p.isdigit() else 0 for p in self.field_id.split("."))


@dataclass
class Subsection:
    title: str
    fields: list[Field] = field(default_factory=list)


@dataclass
class ReportSection:
    title: str
    subsections: list[Subsection] = field(default_factory=list)
    new_page: bool = False
    tables: list[Any] = field(default_factory=list)   # tables.Table

    @property
    def field_count(self) -> int:
        return sum(len(s.fields) for s in self.subsections)


# ------------------------------------------------------------------ resolving
_MESSAGE_PREFIX = "MESSAGE/"


def _walk(node: Any, parts: list[str]) -> Iterable[Any]:
    """Every value reachable by this path, following repeated containers."""
    if not parts:
        yield node
        return
    head, rest = parts[0], parts[1:]
    for item in node if isinstance(node, list) else [node]:
        if isinstance(item, dict) and head in item:
            yield from _walk(item[head], rest)


def _scalar(value: Any) -> Any:
    """Unwrap a data point that carries attributes alongside its text."""
    if isinstance(value, dict):
        return value.get("#text")
    return value


@lru_cache(maxsize=1)
def _layout() -> dict:
    """Column assignments and subsection names, from Appendix E Part 2."""
    path = Path(__file__).resolve().parent.parent.parent / "spec" / "layout.json"
    if not path.exists():
        return {}
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


def _column_for(section: str, label: str) -> str:
    """Which page column a label sets in, per Appendix E Part 2."""
    columns = (_layout().get(section) or {}).get("columns", {})
    if label in columns:
        return columns[label]
    # Sub-labels inherit from the label they qualify, e.g. "Appraiser - Name".
    for known, side in columns.items():
        if label.endswith(known) or known in label:
            return side
    return "left"


@lru_cache(maxsize=1)
def _registry() -> dict[str, list]:
    """Report Field ID -> (spec field, location), grouped by section."""
    spec = spec_loader.load()
    by_section: dict[str, list] = {}
    for entry in spec.fields:
        for location in entry.locations:
            by_section.setdefault(location.section, []).append((entry, location))
    for items in by_section.values():
        items.sort(key=lambda pair: pair[1].sort_key)
    return by_section


# A party-scoped label names the role it belongs to; without that scoping a
# field would collect every party's value at once.
ROLE_BY_LABEL_PREFIX = [
    ("Supervisory Appraiser", "AppraiserSupervisor"),
    ("Significant Real Property Appraisal Assistance",
     "SignificantRealPropertyAppraisalAssistance"),
    ("Property Data Report", "PropertyDataCollector"),
    ("Appraiser", "Appraiser"),
    ("Client", "Client"),
    ("Borrower", "Borrower"),
    ("Seller", "PropertySeller"),
    ("Current Owner of Public Record", "PropertyOwner"),
]


def _role_for(label: str) -> str | None:
    for prefix, role in ROLE_BY_LABEL_PREFIX:
        if label.startswith(prefix):
            return role
    return None


def _party_with_role(data: dict, role: str) -> dict | None:
    """The PARTY carrying this role, if the report has one."""
    parties = model_mod.get(
        data, f"{model_mod.DEAL_PATH}/SERVICES/SERVICE/PARTIES/PARTY", []
    )
    for party in parties if isinstance(parties, list) else [parties]:
        if not isinstance(party, dict):
            continue
        roles = party.get("ROLES", {}).get("ROLE", [])
        for entry in roles if isinstance(roles, list) else [roles]:
            if not isinstance(entry, dict):
                continue
            detail = entry.get("ROLE_DETAIL", {})
            detail = detail[0] if isinstance(detail, list) else detail
            if _scalar(detail.get("PartyRoleType")) == role:
                return party
    return None


def resolve(data: dict, spec_field, label: str = "", *, subject_only: bool = True) -> Any:
    """The value of a spec field within the report model.

    Scoping matters more than the path: a field under PROPERTY belongs to the
    subject, and a field under PARTY belongs to the party whose role the label
    names.  Without that, one label would show every property's or every
    party's value joined together.
    """
    path = spec_field.xpath
    if not path.startswith(_MESSAGE_PREFIX):
        return None
    parts = [p for p in path[len(_MESSAGE_PREFIX):].split("/") if p]
    root = data.get("MESSAGE", data)

    if "PARTY" in parts:
        role = _role_for(label)
        scope = _party_with_role(data, role) if role else None
        if scope is None:
            return None
        tail = parts[parts.index("PARTY") + 1:]
    elif subject_only and "PROPERTY" in parts:
        scope = model_mod.subject(data)
        if scope is None:
            return None
        tail = parts[parts.index("PROPERTY") + 1:]
    else:
        scope, tail = root, parts

    found = [
        _scalar(v.get(spec_field.name))
        for v in _walk(scope, tail)
        if isinstance(v, dict) and spec_field.name in v
    ]
    found = [str(f) for f in found if f not in (None, "")]
    if not found:
        return None
    # A repeating data point displays its values separated by " | " (B-1).
    return " | ".join(dict.fromkeys(found))


# Appendix E sets checkboxes in Wingdings2, so the spec's display text carries
# the glyph characters for checked and unchecked boxes.  They are presentation,
# not content, and are stripped before the value is shown.
_CHECKBOX_GLYPHS = str.maketrans("", "", "R☐☑☒")


def _strip_glyphs(text: str) -> str:
    cleaned = text.translate(_CHECKBOX_GLYPHS) if text.endswith(("R", "")) else text
    return cleaned.strip()


def format_value(spec, data_point: str, value: Any, format_type: str) -> Any:
    """Render a value the way the printed form shows it.

    B-1 p32-33 governs: dates print as mm/dd/yyyy whatever the XML carries,
    amounts print with separators and without trailing zero cents, and
    enumerations print their display text rather than their code.
    """
    if value in (None, ""):
        return None
    text = str(value)

    if data_point in spec.enumerations:
        parts = [
            _strip_glyphs(spec.display_text(data_point, v.strip()) or v.strip())
            for v in text.split("|")
        ]
        return " | ".join(p for p in parts if p)

    if format_type == "Boolean":
        return {"true": "Yes", "false": "No"}.get(text.lower(), text)

    if format_type in ("Date", "Datetime"):
        return _format_date(text)

    if format_type == "Amount":
        try:
            amount = float(text)
        except ValueError:
            return text
        # Whole dollars print without cents; cents are kept when present.
        return f"${amount:,.0f}" if amount == int(amount) else f"${amount:,.2f}"

    if format_type == "Numeric":
        try:
            number = float(text)
        except ValueError:
            return text
        return f"{number:,.0f}" if number == int(number) else f"{number:,}"

    return text


def _format_date(text: str) -> str:
    """ISO dates print as mm/dd/yyyy on the report (B-1 p32)."""
    from datetime import datetime

    for pattern, out in (("%Y-%m-%d", "%m/%d/%Y"), ("%Y-%m", "%m/%Y"), ("%Y", "%Y")):
        try:
            return datetime.strptime(text, pattern).strftime(out)
        except ValueError:
            continue
    return text


def display(spec, data_point: str, value: Any) -> Any:
    """Backwards-compatible entry point for enumeration display text."""
    return format_value(spec, data_point, value, "")


# ------------------------------------------------------------------ building
def build(data: dict, *, include_empty: bool = False) -> list[ReportSection]:
    """Every section the report should print, populated from the model."""
    spec = spec_loader.load()
    registry = _registry()
    out: list[ReportSection] = []

    for name in SECTION_ORDER:
        if name in SPECIAL:
            continue
        entries = registry.get(name) or registry.get(_alias(name, registry))
        if not entries:
            continue

        section = ReportSection(name, new_page=name in NEW_PAGE)
        buckets: dict[str, Subsection] = {}

        for spec_field, location in entries:
            if spec_field.format_type == "" and not spec_field.data_point:
                continue
            if location.label.startswith("["):
                continue  # a placeholder for a repeating role block
            value = format_value(
                spec, spec_field.name,
                resolve(data, spec_field, location.label),
                spec_field.format_type,
            )
            if value is None and not include_empty:
                continue

            bucket = buckets.get(location.subsection)
            if bucket is None:
                bucket = Subsection(location.subsection)
                buckets[location.subsection] = bucket
                section.subsections.append(bucket)

            bucket.fields.append(
                Field(
                    field_id=location.field_id,
                    label="" if location.label == "{No Label}" else location.label,
                    value=value,
                    data_point=spec_field.name,
                    required=spec_field.required,
                    format_type=spec_field.format_type,
                    column=_column_for(name, location.label),
                )
            )

        for bucket in section.subsections:
            bucket.fields = _merge_components(bucket.fields)

        from .tables import build as build_tables
        section.tables = build_tables(data, name)

        if should_display(name, data, section.field_count + len(section.tables)):
            out.append(section)
    return out


# Data points the spec splits across several Field IDs but the form prints as
# one line: a person's name, and a postal address.
NAME_PARTS = ["FirstName", "MiddleName", "LastName", "SuffixName"]
ADDRESS_PARTS = ["AddressLineText", "CityName", "StateCode", "PostalCode"]


def _merge_components(fields: list[Field]) -> list[Field]:
    """Fold fields that share a label into the single line the form prints.

    The specification gives FirstName and LastName their own Field IDs, but the
    report shows one "Borrower Name"; the same is true of the four parts of an
    address.  Merging keeps one row per label without losing any component.
    """
    grouped: dict[str, list[Field]] = {}
    order: list[str] = []
    for f in fields:
        if f.label not in grouped:
            grouped[f.label] = []
            order.append(f.label)
        grouped[f.label].append(f)

    merged: list[Field] = []
    for label in order:
        group = grouped[label]
        if len(group) == 1:
            merged.append(group[0])
            continue

        points = {f.data_point for f in group}
        if points <= set(NAME_PARTS):
            value = _join_by(group, NAME_PARTS, " ")
        elif points <= set(ADDRESS_PARTS):
            value = _format_address(group)
        else:
            value = " | ".join(
                dict.fromkeys(str(f.value) for f in group if f.value not in (None, ""))
            )

        first = group[0]
        merged.append(
            Field(first.field_id, label, value, first.data_point,
                  first.required, first.format_type)
        )
    return merged


def _join_by(group: list[Field], order: list[str], sep: str) -> str:
    by_point = {f.data_point: str(f.value) for f in group if f.value not in (None, "")}
    return sep.join(by_point[p] for p in order if p in by_point)


def _format_address(group: list[Field]) -> str:
    """'213-37 39th Ave #213, Bayside, NY 11361'"""
    by_point = {f.data_point: str(f.value) for f in group if f.value not in (None, "")}
    line = by_point.get("AddressLineText", "")
    city = by_point.get("CityName", "")
    state = by_point.get("StateCode", "")
    postal = by_point.get("PostalCode", "")
    tail = " ".join(x for x in (state, postal) if x)
    return ", ".join(x for x in (line, city, tail) if x)


def should_display(name: str, data: dict, field_count: int) -> bool:
    """Whether a section prints, per the conditions in B-1 p29-31.

    Several data points are shared across sections — a data source appears in
    Site, Sales Comparison, Rental, Income and Cost — so field count alone
    would print approach sections that were never developed.  The scope of
    work states which approaches the appraiser actually used, and that governs.
    """
    # The kind of property decides the template: a co-operative report carries
    # sections a single-family one never does, and the reverse.  The profiles
    # are learned from Appendix D-1's worked scenarios.
    from .profiles import sections_for

    expected = sections_for(data)
    if expected and name not in expected:
        return False

    if name in ALWAYS_PRESENT:
        return True

    scope = model_mod.get(
        data, f"{model_mod.VALUATION_PATH}/VALUATION_ANALYSES/VALUATION_ANALYSIS/"
              f"VALUATION_REPORT/SCOPE_OF_WORK/SCOPE_OF_WORK_DETAIL", {}
    ) or {}

    def flag(name: str) -> bool:
        return str(_scalar(scope.get(name, "false"))).lower() == "true"

    subject = model_mod.subject(data) or {}
    detail = subject.get("PROPERTY_DETAIL", {})
    detail = detail[0] if isinstance(detail, list) else detail

    def indicator(name: str) -> bool:
        return str(_scalar(detail.get(name, "false"))).lower() == "true"

    conditions = {
        # Approach sections display only when that approach was developed.
        "Cost Approach": lambda: flag("CostApproachIndicator"),
        "Income Approach": lambda: flag("IncomeApproachIndicator"),
        "Rental Information": lambda: flag("RentScheduleIndicator"),
        # A project section needs the property to be in a project or PUD.
        "Project Information": lambda: indicator("PUDIndicator")
                                       or indicator("PropertyInProjectIndicator"),
        # These display when the underlying feature exists at all.
        "Disaster Mitigation": lambda: field_count > 0,
        "Energy Efficient and Green Features": lambda: field_count > 0,
        "Manufactured Home": lambda: field_count > 0,
        "Outbuilding": lambda: field_count > 0,
        "Unit Interior": lambda: field_count > 0,
        "Sales Contract": lambda: bool(subject.get("SALES_CONTRACTS")),
        "Revision History": lambda: field_count > 0,
        "Supplemental Information": lambda: field_count > 0,
    }
    check = conditions.get(name)
    return check() if check else field_count > 0


def _alias(name: str, registry: dict) -> str:
    """The spec labels a couple of sections slightly differently."""
    aliases = {
        "Certifications": "Certifications",
        "Energy Efficient and Green Features": "Energy Efficient and Green Features",
    }
    candidate = aliases.get(name, name)
    if candidate in registry:
        return candidate
    for key in registry:
        if key.startswith(name):
            return key
    return name


def coverage(data: dict) -> dict[str, int]:
    """How many fields each section populated, for reporting."""
    return {s.title: s.field_count for s in build(data)}
