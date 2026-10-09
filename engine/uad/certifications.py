"""Additional certifications: the appraiser's (29.053) and the supervisor's (29.062).

A-1 keeps every additional certification in one list,
``VALUATION_REPORT/SCOPE_OF_WORK/VALUATION_REPORT_ADDITIONAL_CERTIFICATIONS``,
each one saying whose it is (``ValuationAdditionalCertificationIncludedByType``:
Appraiser or AppraiserSupervisor) beside its text.  Two indicators on
``VALUATION_REPORT_DETAIL`` say whether each party added any; A-1 makes the text
required when the indicator is true (29.053 / 29.062 "CR").  Neither the type
nor the indicators print, so the form cannot ask for them: they follow the
list here, on every change.

C-1 lays the first certification out as "1." under the italic rule; B-1 prints
each further one numbered after it.  WinTOTAL adds and removes them (Alt+A /
Alt+R); here the next number is always open to type into, and x removes one.

The general field writer could not save these at all (both fields share one
path and their type is not on the form; E-159).
"""
from __future__ import annotations

from lxml import etree

from . import bind, edit

M = f"{{{bind.MISMO}}}"
INDICATOR = {"Appraiser": "AppraiserAdditionalCertificationIndicator",
             "AppraiserSupervisor": "AppraiserSupervisorAdditionalCertificationIndicator"}
FIELDS = {"29.053": "Appraiser", "29.062": "AppraiserSupervisor"}


def max_length() -> int:
    """ValuationAdditionalCertificationText's A-1 String length (360)."""
    d = next(d for d in edit.field("29.053").binding.data_points
             if d.get("mismo") == "ValuationAdditionalCertificationText")
    return int(d.get("format_details") or 0) or 360


def _report(root: etree._Element) -> etree._Element | None:
    return next(root.iter(f"{M}VALUATION_REPORT"), None)


def listed(root: etree._Element, by: str) -> list[etree._Element]:
    """This party's certifications, in document order."""
    return [c for c in root.iter(f"{M}VALUATION_REPORT_ADDITIONAL_CERTIFICATION")
            if (c.findtext(f"{M}ValuationAdditionalCertificationIncludedByType") or "").strip() == by]


def texts(root: etree._Element, by: str) -> list[str]:
    return [(c.findtext(f"{M}ValuationAdditionalCertificationText") or "").strip()
            for c in listed(root, by)]


def set_text(root: etree._Element, by: str, ordinal: int, text: str) -> int:
    """Write certification #ordinal of this party (one past the last adds one;
    empty text removes it) and bring its indicator into line.  Returns how
    many this party now has."""
    if by not in INDICATOR:
        raise ValueError(f"no such party: {by}")
    report = _report(root)
    if report is None:
        raise ValueError("this document has no VALUATION_REPORT")
    items = listed(root, by)
    if not 1 <= ordinal <= len(items) + 1:
        raise ValueError(f"there is no certification #{ordinal} to write")
    text = (text or "").strip()
    if len(text) > max_length():
        raise ValueError(f"A certification can be at most {max_length():,} characters (A-1).")
    if not text:
        if ordinal <= len(items):
            node = items[ordinal - 1]
            holder = node.getparent()
            holder.remove(node)
            if not len(holder):
                holder.getparent().remove(holder)
    elif ordinal <= len(items):
        node = items[ordinal - 1]
        leaf = node.find(f"{M}ValuationAdditionalCertificationText")
        if leaf is None:
            leaf = edit.insert_ordered(node, "ValuationAdditionalCertificationText")
        leaf.text = text
    else:
        holder, _ = edit.ensure_path(report, ["SCOPE_OF_WORK", "VALUATION_REPORT_ADDITIONAL_CERTIFICATIONS"])
        node = edit.insert_ordered(holder, "VALUATION_REPORT_ADDITIONAL_CERTIFICATION")
        # after this party's last, so the numbering is the document's order
        if items and items[-1].getparent() is holder:
            items[-1].addnext(node)
        edit.insert_ordered(node, "ValuationAdditionalCertificationIncludedByType").text = by
        edit.insert_ordered(node, "ValuationAdditionalCertificationText").text = text
    count = len(listed(root, by))
    detail, _ = edit.ensure_path(report, ["VALUATION_REPORT_DETAIL"])
    flag = detail.find(f"{M}{INDICATOR[by]}")
    if flag is None:
        flag = edit.insert_ordered(detail, INDICATOR[by])
    flag.text = "true" if count else "false"
    return count
