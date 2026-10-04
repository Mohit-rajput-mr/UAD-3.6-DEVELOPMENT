"""One list of what is wrong, before and after import -- each item pointing at its field.

knowledge/ARCHITECTURE.md §6.  Every layer's findings in one shape, so the
appraiser (and the next agent) reads one list, and every item that has a field
can be navigated to inside TOTAL from the bridge's panel.

Before import -- a package, no TOTAL needed:

  profile          tools/preflight.py: the TOTAL import profile (P1-P24)
  configuration    what the package is (bridge/detect.py: legacy form or
                   atypical), and every switch TOTAL's writer reads that the
                   package leaves unstated -- TOTAL then keeps its own default

After import -- a live report (reads, runs TOTAL's own validation, navigates
to a neutral section for E&O; writes no value):

  configuration    what the report is; a mirror field (Summary, grid subject
                   column) disagreeing with its source; a Yes/No pair with both
                   boxes marked, anywhere in the report (TOTAL then writes no
                   value, silently)
  total-field-validation   TOTAL's own field validation (its E&O first gate)
  total-uad        TOTAL's UAD rules -- they run only when field validation is
                   clear (P21), so while it is not, this layer says "not run"
  roundtrip        with a package: TOTAL's serialization against it; a
                   difference in a value-affecting data point is severe

Blocking: whether an item stops signing or the ZIP is **not yet known** (the
owner's sign/ZIP test, FINDINGS U4 / T-979): E&O items say "e&o" (they hold up
TOTAL's check the appraiser clears before delivering), round-trip value
differences "value", the rest "unknown" until measured.

    python -m bridge.cli diagnose --xml PACKAGE.xml                 (before)
    python -m bridge.cli diagnose --report "SAMPLE BLANK" [--xml PACKAGE.xml] [--no-uad] [--hud]
"""
from __future__ import annotations

import json
import re
import sys
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from lxml import etree

from . import detect

HERE = Path(__file__).resolve().parents[1]


@dataclass
class Diagnostic:
    layer: str
    severity: str                     # fatal | severe | warning | info
    message: str
    blocking: str = "unknown"         # e&o | value | none | unknown
    section: str = ""                 # TOTAL section key (navigation)
    field: str = ""                   # TOTAL field (navigation)
    instance: int = 0
    data_point: str = ""              # MISMO name
    uid: str = ""
    fid: str = ""
    where: str = ""                   # package path, when there is no field
    cause: str = ""                   # CATALOG / profile id
    fix: str = ""
    rule: str = ""                    # TOTAL / H-1 rule id

    def line(self) -> str:
        at = f"{self.section}/{self.field}#{self.instance}" if self.field else (self.where or self.section)
        tag = f"[{self.severity}/{self.layer}]"
        return f"{tag:<34} {at[:48]:<48} {self.message[:110]}"


# ------------------------------------------------------------ joins
@lru_cache(maxsize=4)
def _placements(build_dir: str) -> dict[str, list[dict]]:
    """TOTAL base field name -> its MISMO placements (uid_map)."""
    uid_map = json.loads((Path(build_dir) / "uid_map.json").read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = {}
    for dp, rows in uid_map.items():
        for x in rows:
            out.setdefault(x["BaseDataFieldName"], []).append(dict(x, data_point=dp))
            if x.get("FieldPrefix"):
                out.setdefault(x["FieldPrefix"] + x["BaseDataFieldName"], []).append(dict(x, data_point=dp))
    return out


def _data_point(field_name: str, build_dir: Path) -> dict:
    """A TOTAL field -> its data point, UID and FID, when the MISMO table has it.
    Section and column copies carry a prefix (DE1_, UI2_, GC3_): try the name,
    then without the prefix."""
    table = _placements(str(build_dir))
    for name in (field_name, re.sub(r"^[A-Z]{1,4}\d*_", "", field_name, count=1)):
        rows = table.get(name)
        if rows:
            return {"data_point": rows[0]["data_point"], "uid": rows[0].get("UID", ""),
                    "fid": rows[0].get("FMID", "")}
    return {}


def _mismo_names() -> dict[str, list[dict]]:
    rows = json.loads((detect.SPEC / "delivery_spec.json").read_text(encoding="utf-8"))
    out: dict[str, list[dict]] = {}
    for r in rows:
        name = r.get("MISMO Data Point Name")
        if name:
            out.setdefault(name, []).append(r)
    return out


# ------------------------------------------------------------ before import
def before(xml_path, build: str = "") -> list[Diagnostic]:
    """A package, checked before it goes near TOTAL."""
    sys.path.insert(0, str(HERE / "tools"))
    import preflight                                 # tools/preflight.py
    xml_path = Path(xml_path)
    out: list[Diagnostic] = []
    for f in preflight.run(xml_path):
        sev = {"error": "severe", "warning": "warning"}.get(f["severity"], "info")
        out.append(Diagnostic("profile", sev, f["message"], where=f["where"], cause=f"{f['rule']} {f['catalog']}".strip(),
                              fix=f["fix"], rule=f["rule"]))

    out += engine_gates(xml_path, build)

    found = detect.drivers_from_xml(xml_path)
    lg = detect.legacy(found)
    what = ", ".join(lg["forms"]) or (f"atypical ({lg['atypical']})" if lg["atypical"] else "no legacy form")
    out.append(Diagnostic("configuration", "info", f"package is {what}: {found.as_text()}",
                          blocking="none", cause=lg["source"]))

    # switches TOTAL's writer reads that the package leaves unstated
    bdir = detect._build_dir(build)
    config = detect._json(bdir, "configuration.json") or {}
    defaults = {d["field"]: d["default"] for d in (detect._json(bdir, "defaults.json") or [])}
    names = _mismo_names()
    root = etree.parse(str(xml_path), etree.XMLParser(huge_tree=True)).getroot()
    present = {etree.QName(e).localname for e in root.iter() if isinstance(e.tag, str)}
    for s in (config.get("common_info") or {}).get("switches", []):
        rows = names.get(s["name"])
        if not rows or s["name"] in present or s["kind"] == "constant":
            continue
        subject_rows = [r for r in rows if r.get("Subject Property") == "x"] or rows
        fields = [s.get(k) for k in ("yes", "no", "field") if s.get(k)]
        held = {f: defaults[f] for f in fields if f in defaults}
        # required: its absence is an error TOTAL papers over with a default;
        # conditionally required: absent is right when A-1's condition is not met
        required = (subject_rows[0].get("Conditionality") or "").strip() == "R"
        cond = (subject_rows[0].get("Conditionality Details") or "").strip()
        out.append(Diagnostic(
            "configuration", "warning" if required else "info",
            f"the package does not state {s['name']}; TOTAL keeps its own value"
            + (f" ({', '.join(f'{k}={v}' for k, v in held.items())})" if held else "")
            + ("" if required else f" -- conditional in A-1: {cond[:140]}"),
            data_point=s["name"], uid=subject_rows[0]["Unique ID"],
            fid=(subject_rows[0].get("Report Location") or "").split(":")[0],
            field=fields[0] if fields else "", cause="P5 E-029 (inferred)",
            fix=f"state {s['name']} explicitly in the package"))
    return out


def _field_of_fid(fid: str, build_dir: Path) -> tuple[str, str]:
    """A Report Field ID -> TOTAL's field and section for it (uid_map), so an
    item found in the package can be navigated to once it is imported."""
    for rows in (detect._json(build_dir, "uid_map.json") or {}).values():
        for x in rows:
            if x.get("FMID") == fid:
                name = x.get("FieldPrefix", "") + x["BaseDataFieldName"]
                return name, _section_of(name, build_dir)
    return "", ""


def engine_gates(xml_path, build: str = "") -> list[Diagnostic]:
    """The engine's own gates on the package (engine/uad/review.py): the GSE
    subschema and the executed H-1 rules.  Rules the engine cannot execute are
    carried as info, never counted as passed."""
    sys.path.insert(0, str(detect.REPO / "engine"))
    from uad import review as engine_review          # noqa: E402
    tree = etree.parse(str(xml_path), etree.XMLParser(huge_tree=True))
    bdir = detect._build_dir(build)
    out: list[Diagnostic] = []
    for it in engine_review.build(tree).items:
        layer = "generator-schema" if it.source == "schema" else "generator-h1"
        sev = {"Fatal": "fatal", "Warning": "warning"}.get(it.severity, "info")
        field_name, section = _field_of_fid(it.field_id, bdir) if it.field_id else ("", "")
        out.append(Diagnostic(layer, sev, it.message, blocking="e&o" if sev == "fatal" else "unknown",
                              section=section, field=field_name, fid=it.field_id, rule=it.code,
                              where=it.path or it.detail, fix=it.detail if sev != "info" else ""))
    return out


# ------------------------------------------------------------ after import
_PAIRS =r"""(() => {
  const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
  const v = {};
  const walk = o => { for (const x of (o.dataObjects || [])) {
      if ((x.dataObjects || []).length) { walk(x); continue; }
      const k = x.key || '';
      if (/_(YES|NO|ENABLE|DISABLE|DISABLED)$/.test(k)) v[k + '#' + (x.instance ?? 0)] = String(x.value ?? '').trim();
  } };
  walk(d);
  const out = [];
  for (const [key, yes] of Object.entries(v)) {
    const m = key.match(/^(.*)_(YES|ENABLE)#(\d+)$/);
    if (!m || !yes) continue;
    for (const neg of ['_NO', '_DISABLE', '_DISABLED']) {
      const no = v[m[1] + neg + '#' + m[3]];
      if (no) out.push({yes: m[1] + '_' + m[2], no: m[1] + neg, instance: +m[3], yes_value: yes, no_value: no});
    }
  }
  return out;
})()"""


def after(report, *, package: bytes | None = None, uad: bool = True, progress=print) -> list[Diagnostic]:
    """A live report, after import (or at any time)."""
    from . import compare as cmp
    from . import review, rtv
    out: list[Diagnostic] = []
    state = detect.describe(report)
    bdir = detect.BUILDS / state["knowledge_build"]
    lg = state["legacy"]
    what = ", ".join(lg["forms"]) or (f"atypical ({lg['atypical']})" if lg["atypical"] else "no legacy form yet")
    out.append(Diagnostic("configuration", "info",
                          f"{state['family']} {state['form']} -- {what}; "
                          f"{state['structure']['buildings']} building(s), {state['structure']['units']} unit(s)",
                          blocking="none"))
    if state["build"] != state["knowledge_build"]:
        out.append(Diagnostic("configuration", "severe",
                              f"TOTAL's web engine is {state['build']} but the knowledge is for "
                              f"{state['knowledge_build']}: extract it and diff before trusting the Import Module",
                              fix="python tools/form_model.py --report <scratch>; python tools/diff_builds.py"))
    for d in state["driver_disagreements"]:
        out.append(Diagnostic("configuration", "severe",
                              f"{d['driver']}: {d['field']} shows {d['shows']} but its source holds "
                              f"{d['source_holds'] or 'nothing'}", field=d["field"],
                              section=_section_of(d["field"], bdir, state["sections"]), **_data_point(d["field"], bdir)))

    progress("  Yes/No pairs ...")
    for p in report.page.evaluate(_PAIRS) or []:
        out.append(Diagnostic("configuration", "severe",
                              f"both {p['yes']} and {p['no']} are marked: TOTAL writes no value for it",
                              field=p["yes"], instance=p["instance"], section=_section_of(p["yes"], bdir, state["sections"]),
                              cause="FINDINGS §9 (Indicator helper)", fix="clear the box that is not true",
                              **_data_point(p["yes"], bdir)))

    progress("  TOTAL field validation ...")
    problems = rtv.problems(report)
    for p in problems:
        out.append(Diagnostic("total-field-validation", "severe", p.message, blocking="e&o",
                              section=p.section, field=p.field, instance=p.instance,
                              fix=("options: " + ", ".join(p.options[:8])) if p.options else "",
                              **_data_point(p.field, bdir)))

    if uad and not problems:
        progress("  TOTAL UAD rules (from a neutral section) ...")
        eo = review.eando(report)
        for r in eo["uad_rules"]:
            out.append(Diagnostic("total-uad", "fatal" if (r["severity"] or "").lower() == "fatal" else "warning",
                                  r["message"], blocking="e&o", rule=r["rule"], data_point=r["data_point"]))
    elif uad:
        out.append(Diagnostic("total-uad", "info", "TOTAL's UAD rules did not run: field validation is not clear "
                              "(P21) -- clear it and diagnose again", blocking="e&o", cause="P21 E-012"))

    if package:
        progress("  round trip: TOTAL's XML against the package ...")
        tot = report.page.evaluate("window.engine.CreateAndReturnMismoXML()", await_promise=True) or ""
        diff = cmp.compare(package, tot.encode("utf-8"))
        value = {id(r) for r in cmp.value_diffs(diff)}
        for r in diff["rows"]:
            owned = expected(r)
            sev = "severe" if id(r) in value else ("info" if owned else "warning")
            out.append(Diagnostic("roundtrip", sev,
                                  f"{r['kind']}: package {r['file'][:3]} -> TOTAL {r['total'][:3]}"
                                  + (f" -- expected: {owned['why']}" if owned and sev == "info" else ""),
                                  blocking="value" if id(r) in value else ("none" if owned else "unknown"),
                                  where=f"{r['scope']}: {r['path']}", data_point=r["data_point"],
                                  cause=owned["evidence"] if owned else ""))
    return out


@lru_cache(maxsize=1)
def _expected_table() -> list[dict]:
    p = detect.REPO / "knowledge" / "total" / "expected_differences.json"
    return json.loads(p.read_text(encoding="utf-8"))["entries"] if p.exists() else []


def expected(row: dict) -> dict | None:
    """The knowledge entry saying a round-trip row is TOTAL's own value, if one does."""
    for e in _expected_table():
        if e["data_point"] == row["data_point"] and e.get("path", "") in row["path"] \
                and row["kind"] in e.get("kinds", [row["kind"]]):
            return e
    return None


def _section_of(field_name: str, build_dir: Path, sections: list[dict] | None = None) -> str:
    """The section key a field is shown in, for navigation: a section copy's
    own key (DE1_ -> dwelling-exterior-1, from the section manager), else the
    field's group in TOTAL's form definition."""
    for s in sections or []:
        if s.get("prefix") and field_name.startswith(s["prefix"]):
            return f"{s['key']}-{s['instance']}"
    df = detect._json(build_dir, "datafields.json") or {}
    for name in (field_name, re.sub(r"^[A-Z]{1,4}\d*_", "", field_name, count=1)):
        if name in df and df[name].get("group"):
            return df[name]["group"]
    return ""


# ------------------------------------------------------------ output
ORDER = {"fatal": 0, "severe": 1, "warning": 2, "info": 3}


def ranked(found: list[Diagnostic]) -> list[Diagnostic]:
    return sorted(found, key=lambda d: (ORDER.get(d.severity, 9), d.layer, d.section, d.field))


def report_text(found: list[Diagnostic]) -> str:
    from collections import Counter
    counts = Counter((d.layer, d.severity) for d in found)
    head = ", ".join(f"{layer} {sev} {n}" for (layer, sev), n in sorted(counts.items()))
    return "\n".join([head, ""] + [d.line() for d in ranked(found)])


def as_json(found: list[Diagnostic]) -> list[dict]:
    return [asdict(d) for d in ranked(found)]
