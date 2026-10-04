"""TOTAL's own error check (E&O), read back as a list you can act on.

The product calls this E&O -- the panel an appraiser clears before delivering.
The engine will run it and hand over every finding, but only when
``enableCefRemoteDebugging`` is set; the hooks were written for a test harness
and answer ``-1`` otherwise.  Setting it is what makes the checker readable.

Each finding names the control, the section and the rule in the product's own
words.  That is more useful than a count: it says what a file is missing, so
the file can be fixed rather than the form patched by hand.

The counts the engine exposes are unreliable when the panel has not been
opened, so the number reported here is counted from the findings themselves.
"""
from __future__ import annotations

import json
import time
from collections import Counter
from dataclasses import dataclass


@dataclass
class Finding:
    key: str
    field: str
    instance: int
    section: str
    section_name: str
    description: str
    rule: str = ""          # a UAD rule's id (UAD-1091 ...); empty for field validation
    severity: str = ""      # a UAD rule's severity (Fatal / Warning)

    @property
    def is_error(self) -> bool:
        # The engine keys a finding by the panel it belongs to; anything not
        # explicitly a warning is treated as an error, which is the safe way
        # round for something that gates delivery.
        if self.severity:
            return self.severity.lower() != "warning"
        return "warn" not in self.key.lower()


def run(report, *, settle: float = 4.0) -> list[Finding]:
    """Run E&O and return every finding."""
    page = report.page
    # The hooks are gated; without this they answer -1 and an empty map.
    page.evaluate("window.engine.enableCefRemoteDebugging = true")
    # Conditionality decides which fields are required at all, so it has to
    # have run before the check means anything.
    try:
        page.evaluate("window.engine.ExecuteAllFormConditionality()")
    except Exception:
        pass
    page.evaluate("window.engine.RunEandOForTesting()", await_promise=True)
    time.sleep(settle)

    raw = page.evaluate("window.engine.GetEandOItemMapForTesting()",
                        await_promise=True) or ""
    if not raw:
        return []
    try:
        items = json.loads(raw)
    except json.JSONDecodeError:
        return []

    found = []
    for key, value in items.items():
        if not isinstance(value, dict):
            continue
        if "RuleId" in value:
            # once field validation is clean the map holds TOTAL's UAD rule
            # results instead, in another shape (CATALOG E-027)
            found.append(Finding(
                key=key, field=value.get("DataPointName", "") or "", instance=0,
                section="uad-rules", section_name="UAD rules",
                description=value.get("MessageText", "") or "",
                rule=str(value.get("RuleId", "") or ""), severity=str(value.get("Severity", "") or "")))
            continue
        found.append(Finding(
            key=key,
            field=value.get("fieldName", ""),
            instance=int(value.get("instance", 0) or 0),
            section=value.get("sectionKey", ""),
            section_name=value.get("sectionFriendlyName", ""),
            description=value.get("description", "")))
    return found


#: TOTAL skips a re-run of its rules started within 15 s of the last one
_RERUN_GUARD = 16


def eando(report, *, neutral: str = "assignment") -> dict:
    """TOTAL's own E&O, read the way that can be trusted: which gate stopped
    it, and every item.

    Run from a neutral section: with Sales Comparison open, TOTAL's field
    validation does not report the comparable-grid findings at all (CATALOG
    E-035) -- the same report reads 0 there and 48 anywhere else.  The gates
    run in order (field validation, schema, UAD rules) and a later gate is not
    run while an earlier one fails, so "stage" says which list this is.
    """
    report.goto(neutral, settle=2.0)
    time.sleep(_RERUN_GUARD)
    found = run(report)
    field = [{"field": f.field, "instance": f.instance, "section": f.section, "message": f.description}
             for f in found if not f.rule]
    rules = [{"rule": f.rule, "severity": f.severity, "data_point": f.field, "message": f.description[:240]}
             for f in found if f.rule]
    stage = "field-validation" if field else ("uad-rules" if rules else "clean-or-not-run")
    panel = report.page.evaluate(r"""(() => { const t = document.body.innerText; const m = t.match(/UAD Errors:\s*(-?\d+)/);
                                             return m ? m[1] : null; })()""")
    return {"stage": stage, "field_validation": field, "uad_rules": rules, "panel_uad_errors": panel}


def by_section(found: list[Finding]) -> dict[str, list[Finding]]:
    out: dict[str, list[Finding]] = {}
    for finding in found:
        out.setdefault(finding.section_name or finding.section, []).append(finding)
    return out


def field_ids(report, found: list[Finding]) -> dict[str, str]:
    """The Report Field ID behind each control a finding names.

    A finding says ``SIT_UTLIMP_WTR_IMP``; what a file has to carry is the
    field id.  The form stamps that on the control, so the sections holding
    the faulted controls are visited and the ids read off.
    """
    wanted = {f.field for f in found if f.field}
    sections = {f.section for f in found if f.section}
    ids: dict[str, str] = {}
    for key in sections:
        try:
            report.goto(key, 1.2)
        except Exception:
            continue
        for control in report.controls():
            fn = control.get("fn", "")
            if fn in wanted and control.get("fmid"):
                ids.setdefault(fn, control["fmid"])
    return ids


def summarise(found: list[Finding]) -> str:
    if not found:
        return "E&O is clear: no findings."
    if all(f.rule for f in found):
        errors = sum(f.is_error for f in found)
        return (f"field validation clear; TOTAL's UAD rules: {errors} error(s), "
                f"{len(found) - errors} warning(s)")
    counts = Counter(f.section_name or f.section for f in found)
    lines = [f"{len(found)} finding(s) across {len(counts)} section(s)"]
    for section, n in counts.most_common():
        lines.append(f"    {section:<40} {n}")
    return "\n".join(lines)
