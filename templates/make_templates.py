"""Generate the per-configuration fill sheets in templates/ — never typed by hand.

One sheet per official D-1 sample: each sample is Fannie Mae / Freddie Mac's own
complete worked example of one configuration (single family, condominium,
cooperative, 2-4 unit, manufactured home; inspection types; project, ADU and
outbuilding variants).  For every value the example carries, the sheet records:

  where        property role (subject / sales / rental / GRM / not-used) and the
               element path from the property (or report) down
  spec         data point, UID(s), report field ID(s) and label(s), format,
               allowed values                         <- engine/spec/uad_map.json
  rules        the H-1 rules on that data point: id, severity, logic
                                                      <- engine/spec/compliance_rules.json
  TOTAL        the WinTOTAL field(s) holding it       <- knowledge/total/builds/<build>/uid_map.json
  import       kept / changed / dropped / not measured by TOTAL's import
                                                      <- knowledge/total/roundtrip/<build>/d1/<sample>/diff.json

Reads data files only (no code from engine/ or total-bridge/), so it runs
anywhere:

    python templates/make_templates.py [--build 0.0.1.3848]

What it is not (yet): the conditional requirements that apply to a
configuration but happen to be absent from its example.  Those come from
evaluating H-1's rule logic per configuration (TASKS: phase 2).
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from lxml import etree

REPO = Path(__file__).resolve().parents[1]
SPEC = REPO / "engine" / "spec"
KNOW = REPO / "knowledge" / "total"
OUT = REPO / "templates"

SKIP_TAGS = {"EXTENSION", "EmbeddedContentXML", "EmbeddedFile"}
SKIP_ATTR = re.compile(r"(^\{http://www\.w3\.org/1999/xlink\}|^xmlns|SensitiveIndicator$|schemaLocation$)")
ROLE_PREFIX = {"SubjectProperty": {"", "GSU_", "RSU_", "RSX_", "GRU_"},
               "SalesComparable": {"GC"}, "RentalComparable": {"RP", "RC"},
               "GrossRentMultiplierComparable": {"GR"}}


def specs_root() -> Path:
    import os
    env = os.environ.get("UAD36_SPECS")
    if env:
        return Path(env)
    here = REPO / "specs" / "official"
    return here if here.exists() else Path(r"C:\3.6 uad zips\_UNZIPPED_ALL")


def _local(tag) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


def _role(prop) -> str:
    role = prop.get("ValuationUseType") or ""
    if not role:
        for e in prop.iter():
            if _local(e.tag) == "ValuationUseType" and (e.text or "").strip():
                return e.text.strip()
    return role or "Property"


def values(root) -> dict:
    """(role, path) -> Counter of example values."""
    out: dict = defaultdict(Counter)

    def walk(node, role, path):
        name = _local(node.tag)
        if not name or name in SKIP_TAGS:
            return
        if name == "PROPERTY":
            role, path = _role(node), ()
        here = path + (name,)
        for k, v in node.attrib.items():
            if not SKIP_ATTR.search(k) and v.strip():
                out[(role, "/".join(here) + "@" + _local(k))][v.strip()] += 1
        kids = [c for c in node if isinstance(c.tag, str)]
        if not kids:
            if (node.text or "").strip():
                out[(role, "/".join(here))][node.text.strip()] += 1
            return
        for c in kids:
            walk(c, role, here)

    walk(root, "report", ())
    return out


def configuration(root) -> dict:
    """What kind of assignment the example is, read from its own values."""
    def first(name):
        for e in root.iter():
            if _local(e.tag) == name and (e.text or "").strip():
                return e.text.strip()
        return ""

    subject = next((p for p in root.iter() if _local(p.tag) == "PROPERTY" and _role(p) == "SubjectProperty"), None)
    units = adus = structures = 0
    if subject is not None:
        for u in subject.iter():
            if _local(u.tag) == "PROPERTY_UNIT":
                adu = any(_local(e.tag) == "AccessoryDwellingUnitIndicator" and (e.text or "") == "true"
                          for e in u.iter())
                adus += adu
                units += not adu
            if _local(u.tag) == "STRUCTURE":
                structures += 1
    roles = Counter(_role(p) for p in root.iter() if _local(p.tag) == "PROPERTY")
    return {
        "exterior_inspection": first("PropertyExteriorInspectionMethodType") or first("InspectionExteriorMethodType"),
        "interior_inspection": first("PropertyInteriorInspectionMethodType") or first("InspectionInteriorMethodType"),
        "attachment": first("AttachmentType"),
        "project_legal_structure": first("ProjectLegalStructureType"),
        "pud": first("PUDIndicator"),
        "construction_method": first("ConstructionMethodType"),
        "structure_design": first("StructuralDesignType") or first("StructureDesignType"),
        "units_excluding_adu": units, "adus": adus, "structures": structures,
        "comparables": {k: v for k, v in roles.items() if k != "SubjectProperty"},
        "assignment": first("ValuationAssignmentType"),
    }


def total_fields(uid_map: dict, dp: str, role: str) -> list[str]:
    want = ROLE_PREFIX.get(role)
    rows = []
    for x in uid_map.get(dp, []):
        prefix = x.get("FieldPrefix", "")
        if want is not None and role != "report":
            if role == "SubjectProperty" and prefix not in want:
                continue
            if role != "SubjectProperty" and not any(prefix.startswith(p) for p in want):
                continue
        rows.append(f"{prefix}{x['BaseDataFieldName']} ({x.get('Section', '')}, {x.get('FMID', '')})")
    return sorted(set(rows))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", default="0.0.1.3848", help="WinTOTAL web-engine build to annotate with")
    a = ap.parse_args(argv)

    spec = json.loads((SPEC / "uad_map.json").read_text(encoding="utf-8"))["data_points"]
    rules = json.loads((SPEC / "compliance_rules.json").read_text(encoding="utf-8"))
    by_dp = defaultdict(list)
    for r in rules:
        by_dp[r.get("Primary Data Element", "")].append(
            {"id": r.get("Message ID"), "severity": r.get("Severity"), "uid": r.get("Unique ID"),
             "logic": r.get("Rule Logic"), "section": r.get("Report Section")})
    uid_path = KNOW / "builds" / a.build / "uid_map.json"
    uid_map = json.loads(uid_path.read_text(encoding="utf-8")) if uid_path.exists() else {}
    rt_root = KNOW / "roundtrip" / a.build / "d1"
    prof_path = KNOW / "builds" / a.build / "validation_profile.json"
    profile = json.loads(prof_path.read_text(encoding="utf-8")) if prof_path.exists() else []
    grid_role = {"Sales": "SalesComparable", "Rental": "RentalComparable", "RentalProp": "RentalComparable",
                 "GrossRent": "GrossRentMultiplierComparable", "GRM": "GrossRentMultiplierComparable"}
    validates = defaultdict(list)          # (role, data point) -> TOTAL rules
    for rule in profile:
        text = "; ".join(rule["messages"].values()) or ", ".join(rule["rules"])
        roles = {grid_role.get(g, g) for g in rule["grid"]} or {"SubjectProperty"}
        if rule["grid"]:
            roles.add("SubjectProperty")   # grid rows have a subject column too
        for d in rule["data_points"]:
            for role in roles:
                validates[(role, d["data_point"])].append(
                    {"total_field": rule["field"], "trigger": rule["trigger"], "rule": text[:200]})

    index = []
    for xml in sorted(specs_root().glob("Appendix D-1 */*.xml")):
        name = xml.stem
        root = etree.parse(str(xml), etree.XMLParser(huge_tree=True)).getroot()
        vals = values(root)
        diff_file = rt_root / name / "diff.json"
        status = {}
        if diff_file.exists():
            for row in json.loads(diff_file.read_text(encoding="utf-8"))["rows"]:
                role = re.sub(r"[@#].*", "", row["scope"])
                status.setdefault((role, row["path"]), row["kind"])
        rows = []
        for (role, path), ctr in sorted(vals.items()):
            leaf = path.split("/")[-1]
            dp = leaf.split("@")[0] if "@" not in leaf else leaf.split("@")[1]
            s = spec.get(dp, {})
            rows.append({
                "role": role, "path": path, "data_point": dp,
                "example": sorted(ctr)[:3],
                "field_ids": [loc.split(":")[0] for loc in s.get("locations", [])][:8],
                "labels": [loc.split(":", 1)[1].strip() for loc in s.get("locations", [])][:4],
                "format": s.get("format_type", ""), "allowed": s.get("values", [])[:40],
                "rules": by_dp.get(dp, [])[:12],
                "total_fields": total_fields(uid_map, dp, role),
                "total_validates": validates.get((role, dp), [])[:6],
                "total_import": ("kept" if diff_file.exists() and (role, path) not in status
                                 else status.get((role, path), "not measured")),
            })
        conf = configuration(root)
        present = {(r["role"], r["data_point"]) for r in rows}
        roles_here = {r["role"] for r in rows}
        beyond = sorted({(role, dp) for (role, dp) in validates
                         if role in roles_here and (role, dp) not in present})
        sheet_beyond = [{"role": role, "data_point": dp, "total_validates": validates[(role, dp)][:4]}
                        for role, dp in beyond]
        eo_file = rt_root / name / "eando.json"
        flagged = []
        if eo_file.exists():
            eo = json.loads(eo_file.read_text(encoding="utf-8"))
            seen = set()
            for f in eo.get("field_validation", []):
                base = re.sub(r"^(GC|GR|RP|RC|DE|UI|OB|MH|SSDE|SSOB)\d+(\.\d+)?_", lambda m: m.group(1) + "#_", f.get("field") or "")
                key = (f.get("section"), base, f.get("message"))
                if key not in seen:
                    seen.add(key)
                    flagged.append({"section": key[0], "field": key[1], "message": key[2]})
        sheet = {"generated_by": "templates/make_templates.py", "example": str(xml.relative_to(specs_root())),
                 "total_build": a.build, "configuration": conf,
                 "counts": {"values": len(rows),
                            "with_total_field": sum(1 for r in rows if r["total_fields"]),
                            "import": dict(Counter(r["total_import"] for r in rows)),
                            "total_validates_beyond_example": len(sheet_beyond),
                            "total_flagged_on_example": len(flagged)},
                 "data_points": rows,
                 # TOTAL validates these for a role present in this configuration, but the official
                 # example does not carry them: fill them (they may be conditional) -- CATALOG E-030
                 "total_validates_beyond_example": sheet_beyond,
                 # MEASURED: what TOTAL's field validation flagged after importing this very example into
                 # a fresh blank report (knowledge/total/roundtrip/<build>/d1/<example>/eando.json)
                 "total_flagged_on_example": flagged}
        (OUT / f"{name}.json").write_text(json.dumps(sheet, indent=1, ensure_ascii=False), encoding="utf-8")
        index.append((name, conf, sheet["counts"]))
        print(f"{name:<42} {len(rows):>5} values  import {sheet['counts']['import']}")

    lines = ["# Fill sheets (generated — do not edit)", "",
             "Regenerate: `python templates/make_templates.py`. See `README.md`.", "",
             "| Sheet | Inspection ext/int | Attachment | Project | Units / ADUs / structures | Comparables | Values | TOTAL import |",
             "|---|---|---|---|---|---|---|---|"]
    for name, c, n in index:
        lines.append(f"| [{name}]({name}.json) | {c['exterior_inspection']} / {c['interior_inspection']} | "
                     f"{c['attachment']} | {c['project_legal_structure'] or ('PUD' if c['pud'] == 'true' else '')} | "
                     f"{c['units_excluding_adu']} / {c['adus']} / {c['structures']} | "
                     f"{', '.join(f'{k} {v}' for k, v in c['comparables'].items())} | {n['values']} | "
                     f"{', '.join(f'{k} {v}' for k, v in n['import'].items())} |")
    (OUT / "INDEX.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
