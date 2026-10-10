"""The footer's reference IDs (HF.005-HF.008), read and written where A-1 puts
them (T-919).

Every page's footer prints the Appraiser Reference ID, and -- when they apply
-- the Agency Case File ID, Client Reference ID and AMC Reference ID.  A-1
gives each a footer location, so the field index (built from the body's
Report Field IDs) has no binding for them and nothing in the editor could set
them.  Everything here is read from A-1's rows: the data point and its path,
the AdditionalValuationIdentifierType that tells the three shared ones apart
(2100.0004/0006/0008), and when each applies -- "IF GovernmentAgencyAppraisalType
= "FHA" OR "VA"", "IF PartyRoleType = "Client" AND Exists".
"""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

from lxml import etree

from . import bind, edit

SPEC = Path(__file__).resolve().parents[1] / "spec"
M = f"{{{bind.MISMO}}}"
TYPE = "AdditionalValuationIdentifierType"
_WANT = re.compile(r'AdditionalValuationIdentifierType\s*=\s*"(\w+)"')


@lru_cache(maxsize=1)
def specs() -> list[dict]:
    """HF.005-HF.008 in footer order: field, label, data point, type, rule."""
    rows = json.loads((SPEC / "delivery_spec.json").read_text(encoding="utf-8"))
    detail = next(k for k in rows[0] if k.startswith("Conditionality Details"))
    enum = next(k for k in rows[0] if k.startswith("Supported Data Point Enum"))
    when = {str(r.get(enum, "")).strip(): str(r.get(detail, "")).strip() for r in rows
            if r.get("MISMO Data Point Name") == TYPE}
    out = []
    for r in rows:
        loc = (r.get("Report Location") or "").strip()
        m = re.match(r"(HF\.00[5-8]):.*Footer - (.+)$", loc)
        if not m:
            continue
        cond = str(r.get(detail, "")).strip()
        kind = (_WANT.search(cond) or [None, ""])[1]
        out.append({"field": m.group(1), "label": m.group(2).strip(), "point": r["MISMO Data Point Name"],
                    "required": (r.get("Conditionality") or "").strip() == "R",
                    "type": kind, "applies_when": when.get(kind, "")})
    return sorted(out, key=lambda s: s["field"])


def by_field(field: str) -> dict:
    hit = next((s for s in specs() if s["field"] == field), None)
    if hit is None:
        raise KeyError(field)
    return hit


def _report(root) -> etree._Element | None:
    return root.find(f".//{M}VALUATION_REPORT")


def _identifier(root, kind: str) -> etree._Element | None:
    report = _report(root)
    for node in (report.iter(f"{M}ADDITIONAL_IDENTIFIER") if report is not None else []):
        if (node.findtext(f"{M}{TYPE}") or "").strip() == kind:
            return node
    return None


def read(root, field: str) -> str:
    s = by_field(field)
    if not s["type"]:
        node = root.find(f".//{M}{s['point']}")
        return (node.text or "").strip() if node is not None else ""
    node = _identifier(root, s["type"])
    return (node.findtext(f"{M}{s['point']}") or "").strip() if node is not None else ""


def applies(root, field: str) -> bool:
    """Does A-1 ask for it in this report?  Required always; otherwise when
    the condition on its type holds (the FHA / VA assignment, the client or
    AMC party), or when it already holds a value."""
    s = by_field(field)
    if s["required"] or read(root, field):
        return True
    m = re.match(r"IF\s+(\w+)\s*=\s*(.+?)(?:\s+AND\s+Exists)?\s*$", s["applies_when"])
    if not m:
        return False
    wanted = set(re.findall(r'"([^"]+)"', m.group(2)))
    have = {(e.text or "").strip() for e in root.iter(f"{M}{m.group(1)}")}
    return bool(wanted & have)


def write(root, field: str, value: str) -> str:
    """Set it (an empty value removes it).  Returns what is stored."""
    s = by_field(field)
    value = value.strip()
    report = _report(root)
    if report is None:
        raise ValueError("The document has no VALUATION_REPORT to hold the reference.")
    if not s["type"]:
        detail, _ = edit.ensure_path(report, ["VALUATION_REPORT_DETAIL"])
        node = detail.find(f"{M}{s['point']}")
        if not value:
            if node is not None:
                detail.remove(node)
            return ""
        if node is None:
            node = edit.insert_ordered(detail, s["point"])
        node.text = value
        return value
    node = _identifier(root, s["type"])
    if not value:
        if node is not None:
            holder = node.getparent()
            holder.remove(node)
            if not len(holder):
                holder.getparent().remove(holder)
        return ""
    if node is None:
        holder = report.find(f"{M}ADDITIONAL_IDENTIFIERS")
        if holder is None:
            holder = edit.insert_ordered(report, "ADDITIONAL_IDENTIFIERS")
        # the XSD makes the container require one, which creating it may
        # have left empty: fill that rather than add a second
        node = next((x for x in holder.findall(f"{M}ADDITIONAL_IDENTIFIER") if not len(x)), None)
        if node is None:
            node = edit.insert_ordered(holder, "ADDITIONAL_IDENTIFIER")
        edit.insert_ordered(node, TYPE).text = s["type"]
    point = node.find(f"{M}{s['point']}")
    if point is None:
        point = edit.insert_ordered(node, s["point"])
    point.text = value
    return value


def editable(root) -> list[dict]:
    """What the editor's footer offers: each reference that applies."""
    return [{"field": s["field"], "label": s["label"], "value": read(root, s["field"])}
            for s in specs() if applies(root, s["field"])]
