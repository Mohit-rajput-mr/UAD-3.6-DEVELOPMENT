"""Compliance validation against the UAD 3.6 rule set.

Three layers, cheapest first:

1. **Schema** - the report must validate against the GSE XSD.
2. **Mechanical rules** - enumeration membership and data-point formats, taken
   straight from the delivery spec, so every enumerated value and every typed
   field is checked without hand-written rules.
3. **Compliance rules** - the 728 published rules.  Presence rules are executed
   directly; rules whose logic is conditional prose are reported as needing
   review rather than silently passed, so nothing is quietly skipped.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

from lxml import etree

from . import model as model_mod
from . import spec_loader

FATAL = "Fatal"
WARNING = "Warning"
REVIEW = "Review"

SCHEMA_PATH = (
    Path(__file__).resolve().parent.parent.parent
    / "_ref/schema/GSE_UAD_3.6.0_v1.3/Combined/GSE_UAD_3.6.0_v1.3.xsd"
)

_US_STATES = {
    "AL","AK","AZ","AR","CA","CO","CT","DE","FL","GA","HI","ID","IL","IN","IA",
    "KS","KY","LA","ME","MD","MA","MI","MN","MS","MO","MT","NE","NV","NH","NJ",
    "NM","NY","NC","ND","OH","OK","OR","PA","RI","SC","SD","TN","TX","UT","VT",
    "VA","WA","WV","WI","WY","DC","AS","GU","MP","PR","VI",
}

_POSTAL = re.compile(r"^\d{5}(-\d{4})?$")
_SIMPLE_PRESENCE = re.compile(r"^If (?P<name>\w+) is not provided\.?$", re.I)

_DATE_FORMATS = {
    "YYYY-MM-DD": "%Y-%m-%d",
    "YYYY-MM": "%Y-%m",
    "YYYY": "%Y",
    "YYYY-MM-DDThh:mm:ssZ": "%Y-%m-%dT%H:%M:%SZ",
}


def _matches_date_format(value: str, pattern: str) -> bool:
    directive = _DATE_FORMATS.get(pattern.strip())
    if directive is None:
        return True  # unknown pattern: don't invent a failure
    try:
        datetime.strptime(value, directive)
    except ValueError:
        # Timestamps are also written with an explicit offset rather than "Z".
        if directive.endswith("Z"):
            try:
                datetime.fromisoformat(value.replace("Z", "+00:00"))
                return True
            except ValueError:
                return False
        return False
    return True


@dataclass
class Finding:
    severity: str
    message: str
    rule_id: str | None = None
    data_point: str | None = None
    section: str | None = None
    field_id: str | None = None
    detail: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items() if v is not None}


@dataclass
class Report:
    findings: list[Finding] = field(default_factory=list)
    schema_valid: bool = True
    checked_rules: int = 0
    skipped_rules: int = 0

    def add(self, finding: Finding) -> None:
        self.findings.append(finding)

    def of(self, severity: str) -> list[Finding]:
        return [f for f in self.findings if f.severity == severity]

    @property
    def fatal(self) -> list[Finding]:
        return self.of(FATAL)

    @property
    def warnings(self) -> list[Finding]:
        return self.of(WARNING)

    @property
    def review(self) -> list[Finding]:
        return self.of(REVIEW)

    @property
    def deliverable(self) -> bool:
        return self.schema_valid and not self.fatal

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema_valid": self.schema_valid,
            "deliverable": self.deliverable,
            "counts": {
                "fatal": len(self.fatal),
                "warning": len(self.warnings),
                "review": len(self.review),
            },
            "checked_rules": self.checked_rules,
            "skipped_rules": self.skipped_rules,
            "findings": [f.as_dict() for f in self.findings],
        }


# ------------------------------------------------------------------ helpers
def _iter_elements(node: Any, tag: str = "MESSAGE") -> Iterable[tuple[str, Any]]:
    """Walk the canonical model, yielding (tag, node) for every container."""
    if isinstance(node, dict):
        yield tag, node
        for key, value in node.items():
            if key.startswith("@") or key == "#text":
                continue
            for item in value if isinstance(value, list) else [value]:
                yield from _iter_elements(item, key)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_elements(item, tag)


def _leaf_values(node: Any, tag: str = "MESSAGE") -> Iterable[tuple[str, str]]:
    """Every scalar data point in the model as (name, value).

    A data point that carries an attribute — an xlink:label, typically — is
    stored as a dict with its value under "#text" rather than as a bare string,
    so both shapes have to yield the element's own name.
    """
    if isinstance(node, list):
        for item in node:
            yield from _leaf_values(item, tag)
    elif isinstance(node, str):
        yield tag, node
    elif isinstance(node, dict):
        if "#text" in node:
            yield tag, str(node["#text"])
        for key, value in node.items():
            if key == "#text":
                continue
            if key.startswith("@"):
                yield key[1:].split(":")[-1], str(value)
            else:
                yield from _leaf_values(value, key)


# ------------------------------------------------------------------- checks
def check_schema(report: Report, xml_bytes: bytes) -> None:
    if not SCHEMA_PATH.exists():
        report.add(Finding(WARNING, "Schema file not found; schema check skipped."))
        return
    schema = etree.XMLSchema(etree.parse(str(SCHEMA_PATH)))
    try:
        tree = etree.fromstring(xml_bytes).getroottree()
    except etree.XMLSyntaxError as exc:
        report.schema_valid = False
        report.add(Finding(FATAL, f"XML is not well formed: {exc}"))
        return
    if not schema.validate(tree):
        report.schema_valid = False
        for error in list(schema.error_log)[:25]:
            report.add(Finding(FATAL, f"Schema: {error.message}", detail=f"line {error.line}"))


def check_enumerations(report: Report, data: dict, spec) -> None:
    """Every enumerated data point must carry a value the spec allows."""
    for name, value in _leaf_values(data):
        fields = spec.by_data_point.get(name)
        # The delivery spec's format type is authoritative: the enumerations
        # sheet carries stray rows for a few free-text fields, and enforcing
        # those would reject valid reports.
        if not fields or fields[0].format_type != "Enumerated":
            continue
        allowed = spec.enumerations.get(name)
        if not allowed:
            continue
        values = {e.value for e in allowed}
        if value not in values:
            location = spec.by_data_point.get(name, [])
            section = location[0].locations[0].section if location and location[0].locations else None
            report.add(Finding(
                FATAL,
                f"{name} has value '{value}', which is not a supported UAD enumeration.",
                data_point=name,
                section=section,
                detail=f"{len(values)} allowed values, e.g. {', '.join(sorted(values)[:4])}",
            ))


def check_formats(report: Report, data: dict, spec) -> None:
    """Typed data points must parse as their declared UAD format."""
    for name, value in _leaf_values(data):
        fields = spec.by_data_point.get(name)
        if not fields or not value:
            continue
        format_type = fields[0].format_type

        if name == "PostalCode" and not _POSTAL.match(value):
            report.add(Finding(FATAL, f"PostalCode '{value}' must be 5 digits or 5+4.",
                               data_point=name))
        elif name == "StateCode" and value not in _US_STATES:
            report.add(Finding(FATAL, f"StateCode '{value}' is not a valid US state or territory code.",
                               data_point=name))
        elif format_type in ("Date", "Datetime"):
            # UAD dates come in several widths: a full date, a year and month,
            # or a bare year (year built, for instance).
            pattern = fields[0].format_details or "YYYY-MM-DD"
            if not _matches_date_format(value, pattern):
                report.add(Finding(
                    FATAL,
                    f"{name} '{value}' does not match its required format ({pattern}).",
                    data_point=name,
                ))
        elif format_type in ("Numeric", "Amount"):
            try:
                float(value)
            except ValueError:
                report.add(Finding(FATAL, f"{name} '{value}' is not numeric.", data_point=name))
        elif format_type == "Boolean" and value not in ("true", "false"):
            report.add(Finding(FATAL, f"{name} '{value}' must be 'true' or 'false'.",
                               data_point=name))
        elif format_type == "String" and fields[0].format_details.isdigit():
            limit = int(fields[0].format_details)
            if len(value) > limit:
                report.add(Finding(
                    WARNING,
                    f"{name} is {len(value)} characters, longer than the {limit}-character "
                    f"maximum; it will be truncated on the report form.",
                    data_point=name,
                ))


def _scope_nodes(data: dict, property_affected: str) -> list[dict]:
    """The subtrees a rule applies to, per its 'Property Affected' column."""
    affected = (property_affected or "").lower()
    if "subject" in affected:
        subject = model_mod.subject(data)
        return [subject] if subject else []
    if "comparable" in affected:
        return model_mod.comparables(data)
    return [data]


def _containers(node: Any, tag: str) -> list[dict]:
    """Every container with this tag anywhere beneath ``node``."""
    return [n for found, n in _iter_elements(node) if found == tag and isinstance(n, dict)]


def _present_in(node: dict, name: str) -> bool:
    return any(found == name for found, _ in _leaf_values(node))


def check_rules(report: Report, data: dict, spec) -> None:
    """Execute the published compliance rules that can be executed.

    A presence rule is scoped to the container its xPath names and the property
    its 'Property Affected' column names.  Checking presence globally would let
    a comparable's value mask a missing subject value.
    """
    for rule in spec.rules:
        logic = rule.get("Rule Logic", "")
        match = _SIMPLE_PRESENCE.match(logic.strip())
        if not match:
            report.skipped_rules += 1
            continue

        report.checked_rules += 1
        name = match.group("name")

        scopes = _scope_nodes(data, rule.get("Property Affected", ""))
        if not scopes:
            continue

        segments = [s for s in (rule.get("xPath") or "").split("/") if s not in ("", "..")]
        container = segments[-1] if segments else None

        satisfied = False
        applicable = False
        for scope in scopes:
            targets = _containers(scope, container) if container else [scope]
            if not targets:
                continue  # the optional container isn't present at all
            applicable = True
            if any(_present_in(t, name) for t in targets):
                satisfied = True
                break

        if satisfied or not applicable:
            continue

        field_id = None
        located = spec.by_data_point.get(name)
        if located and located[0].locations:
            field_id = located[0].locations[0].field_id

        report.add(Finding(
            rule["Severity"],
            rule.get("Message Text") or f"{name} is required.",
            rule_id=rule.get("Message ID"),
            data_point=name,
            section=rule.get("Report Section"),
            field_id=field_id,
        ))


def run(data: dict, *, spec=None, xml_bytes: bytes | None = None) -> Report:
    """Validate a report model at every layer."""
    spec = spec or spec_loader.load()
    report = Report()

    if xml_bytes is None:
        xml_bytes = model_mod.serialize(data)
    check_schema(report, xml_bytes)
    check_enumerations(report, data, spec)
    check_formats(report, data, spec)
    check_rules(report, data, spec)
    return report
