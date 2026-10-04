"""Learn what TOTAL demands beyond UAD from what it actually flagged -- and test it.

TOTAL's 759 validators name the fields they guard but not the conditions under
which they apply, so "every comparable needs X" cannot be read off the form
model without false alarms.  This learns the rules from measured runs instead:
for every field-validation finding of a round trip (tools/roundtrip.py output),
the field is traced to the data points it holds (TOTAL's own tables), and a
rule "a <role> carries one of <data points>" is formed.  Each rule is then
**tested on every property of every sample**: predicted = the package lacks all
of those data points on that property; flagged = TOTAL raised the finding there.

  reliable     predicted exactly where TOTAL flagged (no false alarm, >= 2 hits):
               preflight enforces it (P12)
  conditional  TOTAL applies a condition the rule does not model: listed, with
               the false alarms, not enforced

Adjustment rows ("an adjustment entry is required when subject and comparable
data differ", E-031) are learned the same way through TOTAL's own
type <-> row map (builds/<build>/adjustment_map.json): predicted = the
comparable's row data differs from the subject's and the package carries no
amount of that ComparableAdjustmentType (P13).

    python tools/learn_requirements.py --run ../knowledge/total/e2e/0.0.1.3848/total [--run ...]

Writes knowledge/total/builds/<build>/requirements.json and prints the table.
"""
from __future__ import annotations

import argparse
import json
import re
from collections import Counter, defaultdict
from pathlib import Path

from lxml import etree

HERE = Path(__file__).resolve().parent
KNOW = HERE.parents[1] / "knowledge" / "total" / "builds"
GRID = {"GC": "SalesComparable", "RP": "RentalComparable", "RC": "RentalComparable",
        "GR": "GrossRentMultiplierComparable"}
ADJ_MESSAGE = re.compile(r"adjustment (entry )?is required", re.I)


def _local(tag) -> str:
    return etree.QName(tag).localname if isinstance(tag, str) else ""


def _street(prop) -> str:
    return re.sub(r"\s+", " ", (prop.findtext("{*}ADDRESS/{*}AddressLineText") or "").strip().upper())


def load(xml: Path) -> dict:
    """{'report': {dp: [values]}, (role, street|ordinal): {dp: [values]}, 'order': {(role, n): street},
    'adjusted': {(role, street): {ComparableAdjustmentType with an amount}}}"""
    root = etree.parse(str(xml), etree.XMLParser(huge_tree=True, recover=True)).getroot()
    out = {"report": defaultdict(list), "order": {}, "adjusted": defaultdict(set)}
    props = set()
    counters = Counter()
    for prop in root.iter("{*}PROPERTY"):
        role = prop.get("ValuationUseType") or ""
        counters[role] += 1
        n = 0 if role == "SubjectProperty" else counters[role]
        street = _street(prop)
        key = (role, street if n and street else n)
        out["order"][(role, n)] = key
        vals = out.setdefault(key, defaultdict(list))
        for e in prop.iter():
            if isinstance(e.tag, str) and len(e) == 0 and (e.text or "").strip():
                vals[_local(e.tag)].append(e.text.strip())
        for adj in prop.iter("{*}COMPARABLE_ADJUSTMENT"):
            t, a = adj.findtext("{*}ComparableAdjustmentType"), adj.findtext("{*}ComparableAdjustmentAmount")
            if t and a and a.strip():
                out["adjusted"][key].add(t.strip())
        props.add(prop)
    for e in root.iter():
        if isinstance(e.tag, str) and len(e) == 0 and (e.text or "").strip():
            if not any(_local(a.tag) == "PROPERTY" for a in e.iterancestors()):
                out["report"][_local(e.tag)].append(e.text.strip())
    return out


def base_of(field: str):
    m = re.match(r"^(GC|GR|RP|RC)(\d+)(?:\.(\d+))?_(.+)$", field or "")
    if m:
        return m.group(4), GRID[m.group(1)], int(m.group(3) or m.group(2))
    return field or "", "SubjectProperty", 0


def data_points(build: str) -> dict:
    dps = defaultdict(set)
    for rule in json.loads((KNOW / build / "validation_profile.json").read_text(encoding="utf-8")):
        for d in rule["data_points"]:
            dps[rule["field"]].add(d["data_point"])
    for dp, placements in json.loads((KNOW / build / "uid_map.json").read_text(encoding="utf-8")).items():
        for x in placements:
            name = x["BaseDataFieldName"]
            dps[name].add(dp)
            if name.startswith("PU_"):
                dps[name[3:]].add(dp)
    for name in list(dps):
        dps[name] -= {"ComparableAdjustmentAmount"}
    return dps


def samples(runs: list[Path]):
    for run in runs:
        for d in sorted(p for p in run.iterdir() if (p / "eando.json").exists() and (p / "state.json").exists()):
            pkg = Path(json.loads((d / "state.json").read_text(encoding="utf-8"))["file"])
            tot = d / "total.xml"
            if pkg.exists() and tot.exists():
                yield d.name, pkg, tot, json.loads((d / "eando.json").read_text(encoding="utf-8"))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--run", action="append", required=True, help="a round-trip output folder (repeatable)")
    ap.add_argument("--build", default="0.0.1.3848")
    a = ap.parse_args(argv)
    dps_of = data_points(a.build)
    type_of = {v["field"]: k for m in json.loads((KNOW / a.build / "adjustment_map.json").read_text(encoding="utf-8")).values()
               for k, v in m.items()}

    flagged = defaultdict(set)          # (role, base) -> {(sample, key)}
    messages = defaultdict(Counter)
    loaded = {}
    for name, pkg, tot, eo in samples([Path(r) for r in a.run]):
        p, t = load(pkg), load(tot)
        loaded[name] = p
        for f in eo.get("field_validation", []):
            base, role, n = base_of(f.get("field"))
            tkey = t["order"].get((role, n))
            if tkey is None:
                continue
            street = tkey[1] if isinstance(tkey[1], str) else None
            key = (role, street) if street else p["order"].get((role, n), (role, n))
            flagged[(role, base)].add((name, key))
            messages[(role, base)][(f.get("message") or "")[:120]] += 1

    rules = []
    for (role, base), hits in sorted(flagged.items()):
        is_adj = base.endswith("_ADJ") and any(ADJ_MESSAGE.search(m) for m in messages[(role, base)])
        row = base[:-4] if base.endswith("_ADJ") else base
        dps = sorted(dps_of.get(row, set()))
        if not dps:
            continue
        adj_type = type_of.get(base)
        core = [d for d in dps if not d.endswith("OtherDescription")] or dps

        def predict(mode):
            predicted = set()
            for name, p in loaded.items():
                subject = p.get(("SubjectProperty", 0), {})
                for key, vals in p.items():
                    if not isinstance(key, tuple) or key[0] != role:
                        continue
                    have = set(vals) | (set(p["report"]) if role == "SubjectProperty" else set())
                    if not is_adj:
                        # "any": TOTAL wants one of the row's data points;
                        # "all": every core one ("complete all required ... fields")
                        missing = not (set(dps) & have) if mode == "any" else not set(core) <= have
                        if missing:
                            predicted.add((name, key))
                    elif adj_type:
                        # TOTAL counts a comparable with no value against a
                        # subject with one as "differs"
                        s = [sorted(subject.get(d, [])) for d in core]
                        c = [sorted(vals.get(d, [])) for d in core]
                        if (any(s) or any(c)) and s != c and adj_type not in p["adjusted"].get(key, set()):
                            predicted.add((name, key))
            return predicted

        tried = [(m, predict(m)) for m in (("any", "all") if not is_adj else ("differs",))]
        # the mode with no false alarm and most hits; else the fewest false alarms
        mode, predicted = min(tried, key=lambda mp: (len(mp[1] - hits) > 0, -len(hits & mp[1]), len(mp[1] - hits)))
        tp, fp, fn = hits & predicted, predicted - hits, hits - predicted
        rules.append({"kind": "adjustment" if is_adj else "data", "role": role, "field": base, "mode": mode,
                      "adjustment_type": adj_type if is_adj else None, "data_points": dps, "core": core,
                      "messages": [m for m, _ in messages[(role, base)].most_common(3)],
                      "flagged": len(hits), "predicted": len(predicted), "tp": len(tp), "fp": len(fp), "fn": len(fn),
                      "samples": sorted({s for s, _ in hits}),
                      "reliable": not fp and len(tp) >= 2,
                      "false_alarms": sorted(f"{s}:{k[1]}" for s, k in fp)[:6],
                      "missed": sorted(f"{s}:{k[1]}" for s, k in fn)[:6]})
    out = KNOW / a.build / "requirements.json"
    out.write_text(json.dumps({"build": a.build, "runs": a.run, "rules": rules}, indent=1), encoding="utf-8")
    rel = [r for r in rules if r["reliable"]]
    print(f"{len(rules)} rules learned from {len(loaded)} samples; {len(rel)} reliable -> {out}")
    print(f"{'kind':<10} {'role':<16} {'field':<34} {'tp':>3} {'fp':>3} {'fn':>3}  reliable  message")
    for r in sorted(rules, key=lambda r: (not r["reliable"], r["kind"], r["role"], r["field"])):
        print(f"{r['kind']:<10} {r['role'][:16]:<16} {r['field'][:34]:<34} {r['tp']:>3} {r['fp']:>3} {r['fn']:>3}  "
              f"{'yes' if r['reliable'] else 'no':<8}  {r['messages'][0][:60]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
