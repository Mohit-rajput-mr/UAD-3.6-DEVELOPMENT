"""Writing the A-1 data points that never appear on the report.

Most of what a UAD 3.6 file carries is printed somewhere, so the editor can
reach it by the field the report prints.  About 180 points are different:
A-1 marks them "Does Not Display", yet requires them all the same, and H-1
faults a file that leaves them out.  The switches that say which approaches to
value were developed are the clearest example -- ``IncomeApproachIndicator``
is required, decides whether a rent schedule and a gross rent multiplier are
demanded at all, and has no label anywhere on the form.

They are written here the same way every other value is written: A-1's own
xPath for the container, A-1's own data point name for the leaf, and the
editor's ordered insert, so the document stays in the schema's order and the
Store's guard still refuses anything that would break it.  Nothing is
hand-placed and nothing is special-cased; the delivery specification is the
only source.

    points.write(tree, "1000.0030", "false")                # the subject
    points.write(tree, "1800.0363", "1", scope=comparable)  # a comparable
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from lxml import etree

from . import bind, edit

SPEC = Path(__file__).resolve().parents[1] / "spec" / "delivery_spec.json"

ENUMS = "Supported Data Point Enumerations\n\n(Reference the MISMO Data Point Name column)"


@lru_cache(maxsize=1)
def index() -> dict[str, dict]:
    """Every A-1 data point by its Unique ID, in the shape a write takes."""
    raw = json.loads(SPEC.read_text(encoding="utf-8"))
    rows = raw if isinstance(raw, list) else raw.get("rows", raw.get("data_points", []))
    out: dict[str, dict] = {}
    for row in rows:
        uid = (row.get("Unique ID") or "").strip()
        name = (row.get("MISMO Data Point Name") or "").strip()
        xpath = (row.get("MISMO xPath") or "").strip()
        if not uid or not name or not xpath:
            continue
        out.setdefault(uid, {
            "unique_id": uid,
            "mismo": name,
            "xpath": xpath.rstrip("/"),
            "container": (row.get("MISMO Parent Container") or "").strip(),
            "format_type": (row.get("UAD Data Point Format Type") or "").strip(),
            "format_details": (row.get("UAD Data Point Format Details") or "").strip(),
            "context": (row.get("Additional Context") or "").strip(),
            "enumerations": [{"value": v} for v in (row.get(ENUMS) or "").split("|") if v],
            "conditionality": (row.get("Conditionality") or "").strip(),
            "conditionality_details": (row.get("Conditionality Details") or "").strip(),
            "report_location": (row.get("Report Location") or "").strip(),
        })
    return out


def point(unique_id: str) -> dict:
    dp = index().get(unique_id)
    if dp is None:
        raise KeyError(f"{unique_id} is not a data point in A-1")
    return dp


def permitted(unique_id: str) -> list[str]:
    return [e["value"] for e in point(unique_id)["enumerations"]]


def write(tree, unique_id: str, value: str,
          scope: etree._Element | None = None, ordinal: int = 1) -> edit.Written:
    """Set one A-1 data point by its Unique ID.

    ``scope`` is the element the value belongs inside -- a comparable's
    PROPERTY.  Without one a point under a PROPERTY is the subject's, which is
    the same rule the rest of the editor follows.
    """
    dp = point(unique_id)
    allowed = permitted(unique_id)
    if allowed and value not in allowed:
        raise ValueError(f"{unique_id} ({dp['mismo']}) takes one of "
                         f"{'|'.join(allowed)}, not {value!r}")
    binding = bind.Binding(field_id=unique_id, section="", subsection="",
                           label=dp["mismo"], data_points=[dp])
    return edit.write(tree, unique_id, value, data_point=dp["mismo"],
                      binding=binding, scope=scope, ordinal=ordinal)


def read(root: etree._Element, unique_id: str,
         scope: etree._Element | None = None) -> str:
    dp = point(unique_id)
    # Without a scope the point is the subject's -- and many of these sit
    # beside the property rather than inside it (the approach indicators are
    # on the analysis), so the whole document is the place to look.
    where = scope if scope is not None else root
    node = next((n for n in where.iter(f"{{{bind.MISMO}}}{dp['mismo']}")), None)
    return (node.text or "").strip() if node is not None else ""
