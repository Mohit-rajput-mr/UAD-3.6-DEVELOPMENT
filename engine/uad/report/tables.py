"""Populate the URAR's in-section tables.

Appendix E Part 2 defines 41 tables beyond the sales comparison grid — parcels,
site influences, utilities, level and room detail, amenities, transfer history,
approaches to value and the rest.  Their column heads come from
``engine/spec/tables.json``; the binding from column head to MISMO data point
is derived from the delivery specification, which already records the xPath of
every labelled field.

A table draws one row per instance of the repeating container its columns share,
so a property with three parcels prints three rows without anything being
written per table.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any

from .. import model as model_mod
from .. import spec_loader
from .sections import _scalar, _walk, format_value

SPEC_FILE = Path(__file__).resolve().parent.parent.parent / "spec" / "tables.json"


@dataclass
class Table:
    name: str
    section: str
    columns: list[str]
    rows: list[list[str]] = field(default_factory=list)
    width_picas: int = 45

    @property
    def populated(self) -> bool:
        return any(any(cell for cell in row) for row in self.rows)


@lru_cache(maxsize=1)
def definitions() -> list[dict]:
    if not SPEC_FILE.exists():
        return []
    with open(SPEC_FILE, encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def _labelled() -> dict[tuple[str, str], list]:
    """(section, label) -> the spec fields that print under it."""
    index: dict[tuple[str, str], list] = {}
    for entry in spec_loader.load().fields:
        for location in entry.locations:
            index.setdefault((location.section, location.label), []).append(entry)
    return index


def _container(xpath: str) -> list[str]:
    """The path segments below PROPERTY for a field's own container."""
    parts = [p for p in xpath.split("/") if p]
    if "PROPERTY" not in parts:
        return []
    return parts[parts.index("PROPERTY") + 1 :]


def _shared_container(paths: list[list[str]]) -> list[str]:
    """The deepest path prefix every column shares — the repeating row."""
    if not paths:
        return []
    shortest = min(paths, key=len)
    shared: list[str] = []
    for depth, segment in enumerate(shortest):
        if all(path[depth] == segment for path in paths):
            shared.append(segment)
        else:
            break
    return shared


def build(data: dict, section: str) -> list[Table]:
    """Every table this section prints, populated from the report."""
    spec = spec_loader.load()
    subject = model_mod.subject(data)
    if subject is None:
        return []

    index = _labelled()
    out: list[Table] = []

    for definition in definitions():
        if not definition["section"] or not section.startswith(definition["section"][:18]):
            continue

        # Find the data point behind each column head.
        bindings: list[tuple[str, Any]] = []
        for column in definition["columns"]:
            candidates = index.get((definition["section"], column)) or []
            candidates = [c for c in candidates if _container(c.xpath)]
            bindings.append((column, candidates[0] if candidates else None))

        bound = [(c, f) for c, f in bindings if f is not None]
        if len(bound) < 2:
            continue  # nothing to draw this table from

        row_path = _shared_container([_container(f.xpath) for _, f in bound])
        if not row_path:
            continue

        table = Table(
            name=definition["name"],
            section=section,
            columns=definition["columns"],
            width_picas=definition.get("width_picas", 45),
        )

        for instance in _walk(subject, row_path):
            if not isinstance(instance, dict):
                continue
            row: list[str] = []
            for column, spec_field in bindings:
                if spec_field is None:
                    row.append("")
                    continue
                tail = _container(spec_field.xpath)[len(row_path):]
                found = [
                    _scalar(node.get(spec_field.name))
                    for node in _walk(instance, tail)
                    if isinstance(node, dict) and spec_field.name in node
                ]
                found = [f for f in found if f not in (None, "")]
                value = format_value(
                    spec, spec_field.name,
                    " | ".join(dict.fromkeys(str(f) for f in found)) if found else None,
                    spec_field.format_type,
                )
                row.append("" if value is None else str(value))
            if any(row):
                table.rows.append(row)

        if table.populated:
            out.append(table)
    return out
