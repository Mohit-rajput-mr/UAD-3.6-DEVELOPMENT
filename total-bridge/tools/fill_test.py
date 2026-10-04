"""Build a TEST package: a D-1 sample given what TOTAL's field validation asked for.

The question it answers (TASKS T-995): when a package *does* carry the
comparable facts TOTAL validates beyond UAD (IMPORT_PROFILE P12) and states an
adjustment wherever subject and comparable differ (P13), does TOTAL's importer
put them where its validators look -- does field validation reach zero, and do
TOTAL's UAD rules then run?  The official samples never carry those facts, so
this was never observed.

**The output is not a report.**  Its values are stand-ins chosen mechanically:
the subject's own value for the same grid row when the sample has one, else
"None" when A-1 offers it, else A-1's first enumeration; a count copies the
subject's; an adjustment is $0.  The file is named ``*_TEST_NOT_A_REPORT.xml``
and must never be delivered.

    python tools/fill_test.py --run ../knowledge/total/e2e/0.0.1.3855/total/SF1_Appraisal \
        --package ../knowledge/total/e2e/0.0.1.3848/SF1_Appraisal/portable.xml --build 0.0.1.3855
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent
REPO = HERE.parents[1]
sys.path.insert(0, str(REPO / "engine"))
sys.path.insert(0, str(HERE))

from uad import bind, edit                      # noqa: E402
from uad.report import comparables              # noqa: E402
import classify_findings as cf                  # noqa: E402

M = "{%s}" % bind.MISMO


def _enums() -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for r in json.loads((REPO / "engine" / "spec" / "enumerations.json").read_text(encoding="utf-8")):
        if r.get("Unique ID") and r.get("Supported Enumerations"):
            out.setdefault(r["Unique ID"], []).append(r["Supported Enumerations"])
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", required=True, help="one sample's roundtrip output folder (eando.json, total.xml)")
    ap.add_argument("--package", required=True)
    ap.add_argument("--build", required=True)
    ap.add_argument("--out")
    a = ap.parse_args(argv)
    run, pkg = Path(a.run), Path(a.package)
    builds = REPO / "knowledge" / "total" / "builds" / a.build
    uid_map = json.loads((builds / "uid_map.json").read_text(encoding="utf-8"))
    adj_map = json.loads((builds / "adjustment_map.json").read_text(encoding="utf-8"))["salesComparableAdjustmentMap"]
    adj_type = {v["field"]: k for k, v in adj_map.items()}
    enums = _enums()

    # grid field (base name) -> (comparable FID, subject FID) from TOTAL's own table
    # every comparable grid (sales GC, GRM GR, rental property RP, rental unit
    # RC) and its subject column (GSU, GRU, RSU, RSX), from TOTAL's own prefixes
    COMP = {"GC": "GC", "GR": "GR", "RP": "RP", "RCX": "RC"}
    SUBJ = {"GSU": "GC", "GRU": "GR", "RSU": "RP", "RSX": "RC"}
    comp_fid, subj_fid = {}, {}
    for rows in uid_map.values():
        for x in rows:
            head = re.sub(r"\d*_$", "", x.get("FieldPrefix", ""))
            if head in COMP:
                comp_fid[(COMP[head], x["BaseDataFieldName"])] = x["FMID"]
            elif head in SUBJ:
                subj_fid[(SUBJ[head], x["BaseDataFieldName"])] = x["FMID"]

    tree = etree.parse(str(pkg), etree.XMLParser(huge_tree=True))
    root = tree.getroot()
    subject = bind.subject(root)
    street = lambda p: re.sub(r"\s+", " ", (p.findtext(f"{M}ADDRESS/{M}AddressLineText") or "").strip().upper())
    by_street = {(p.get("ValuationUseType"), street(p)): p for p in root.iter(f"{M}PROPERTY")
                 if p.get("ValuationUseType") != "SubjectProperty"}
    # TOTAL numbers its columns itself: column n -> street, from TOTAL's XML
    tot = cf.properties(run / "total.xml")["addresses"]

    # P27 (E-044): a defect picture's caption, from its own defect record
    captions = []
    for defect in root.iter(f"{M}DEFECT"):
        det = defect.find(f"{M}DEFECT_DETAIL")
        what = ""
        if det is not None:
            comp = det.findtext(f"{M}DefectComponentLabelTypeOtherDescription") or det.findtext(f"{M}DefectComponentLabelType") or ""
            seen = (det.findtext(f"{M}DefectItemDescription") or "").split(".")[0]
            what = " - ".join(x for x in (comp, seen) if x)[:120]
        for image in defect.iter(f"{M}IMAGE"):
            if what and not (image.findtext(f"{M}ImageCaptionCommentDescription") or "").strip():
                edit.insert_ordered(image, "ImageCaptionCommentDescription").text = what
                captions.append((image.findtext(f"{M}ImageFileLocationIdentifier") or "")[-40:])

    findings = json.loads((run / "eando.json").read_text(encoding="utf-8"))["field_validation"]
    # a row TOTAL flags once per unit instance is a per-unit row
    per_unit_rows: dict[str, int] = {}
    for f in findings:
        per_unit_rows[f["field"]] = per_unit_rows.get(f["field"], 0) + 1

    def unit_ids(prop) -> list[str]:
        return [u.findtext(f"{M}PROPERTY_UNIT_DETAIL/{M}UnitIdentifier") or u.findtext(f".//{M}UnitIdentifier") or ""
                for u in prop.iter(f"{M}PROPERTY_UNIT")]

    def write_unit_adjustment(prop, kind: str, amount: str, ident: str) -> bool:
        """A $0 adjustment of this type (for this unit, when per unit) unless
        the comparable already states one."""
        for node in prop.iter(f"{M}COMPARABLE_ADJUSTMENT"):
            if (node.findtext(f"{M}ComparableAdjustmentType") or "") == kind and \
                    (node.findtext(f"{M}UnitIdentifier") or "") == ident:
                return False
        if not ident:
            comparables.write_adjustment(prop, kind, amount)
            return True
        comparable, _ = edit.ensure_path(prop, ["COMPARABLE"])
        holder, _ = edit.ensure_path(comparable, ["COMPARABLE_ADJUSTMENTS"])
        node = edit.insert_ordered(holder, "COMPARABLE_ADJUSTMENT")
        edit.insert_ordered(node, "ComparableAdjustmentAmount").text = amount
        edit.insert_ordered(node, "ComparableAdjustmentType").text = kind
        edit.insert_ordered(node, "UnitIdentifier").text = ident
        return True

    def held(scope, dp: dict, unit: int | None) -> list[str]:
        """The data point's values strictly inside this property (and inside
        its unit-th PROPERTY_UNIT for a per-unit row), by A-1's own path --
        never another property's."""
        xpath = dp.get("xpath") or ""
        if "PROPERTIES/PROPERTY/" not in xpath:
            return []
        nodes = [scope]
        for step in [s for s in xpath.split("PROPERTIES/PROPERTY/", 1)[1].split("/") if s]:
            nodes = [c for n in nodes for c in n.findall(M + step)]
            if step == "PROPERTY_UNIT" and unit:
                nodes = nodes[unit - 1:unit]
        return [(c.text or "").strip() for n in nodes for c in n.findall(M + dp["mismo"]) if (c.text or "").strip()]

    log, skipped = [], []
    for f in findings:
        base, role, ordinal = cf.base_of(f["field"])
        grid = re.match(r"^(GC|GR|RP|RC)", f["field"] or "")
        if role == "SubjectProperty" or not grid:
            skipped.append((f["field"], "not a comparable grid row"))
            continue
        grid = grid.group(1)
        # the unit a row is about: RC<unit>.<comp>_, or the instance of a
        # per-unit sales row (GC1_LEVELS #2 = unit 3)
        m = re.match(r"^RC(\d+)\.\d+_", f["field"])
        unit = int(m.group(1)) if m else int(f.get("instance") or 0) + 1
        prop = by_street.get((role, tot.get((role, ordinal), "")))
        if prop is None:
            skipped.append((f["field"], "comparable not matched by address"))
            continue
        per_unit = per_unit_rows.get(f["field"], 0) > 1 or grid == "RC"
        if base.endswith("_ADJ"):
            kind = adj_type.get(base)
            if not kind:
                skipped.append((f["field"], "no adjustment type in TOTAL's map"))
                continue
            ident = unit_ids(prop)[unit - 1] if per_unit and len(unit_ids(prop)) >= unit else ""
            if write_unit_adjustment(prop, kind, "0", ident):
                log.append((f["field"], f"{kind} = 0" + (f" ({ident})" if ident else "")))
            continue
        fid = comp_fid.get((grid, base))
        if not fid:
            skipped.append((f["field"], "no comparable field ID"))
            continue
        binding = bind.binding_for(fid)
        wrote = False
        for dp in binding.data_points:
            name, uid = dp.get("mismo"), dp.get("unique_id")
            if not name or name.endswith("OtherDescription") or dp.get("attribute"):
                continue
            if held(prop, dp, unit if per_unit else None):
                continue                                  # the comparable already says it
            value = ""
            sfid = subj_fid.get((grid, base))
            if sfid:
                sb = bind.binding_for(sfid)
                same = [d for d in sb.data_points if d.get("mismo") == name] if sb else []
                if same:
                    got = held(subject, same[0], unit if per_unit else None) or held(subject, same[0], None)
                    value = got[0] if got else ""
            if not value:
                options = [e for e in enums.get(uid, []) if e != "Other"]
                value = "None" if "None" in options else (options[0] if options else "")
            if not value and name.endswith(("Count", "Measure")):
                value = "0"
            if not value and name.endswith("Indicator"):
                value = "false"
            if not value:
                continue
            edit.write(tree, fid, value, data_point=name, scope=prop, ordinal=unit if per_unit else 1)
            log.append((f["field"], f"{name} = {value}" + (f" (unit {unit})" if per_unit else "")))
            wrote = True
        if not wrote:
            skipped.append((f["field"], "nothing written (already present or no stand-in)"))

    out = Path(a.out) if a.out else pkg.with_name(pkg.stem + "_TEST_NOT_A_REPORT.xml")
    tree.write(str(out), encoding="utf-8", xml_declaration=True)
    print(f"{len(log)} stand-in value(s) written, {len(captions)} defect caption(s), {len(skipped)} finding(s) skipped -> {out}")
    for field, what in log:
        print(f"  + {field:<40} {what}")
    for field, why in skipped:
        print(f"  - {field:<40} {why}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
