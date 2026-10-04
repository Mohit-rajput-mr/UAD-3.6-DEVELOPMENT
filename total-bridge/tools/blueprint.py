"""How TOTAL's UAD 3.6 form works inside, extracted from its own code (offline).

Reads the form-engine snapshot `tools/dump_bundle.py` keeps outside the
repository and writes, into knowledge/total/builds/<build>/, facts *about* that
code -- never the code:

  blueprint.json   per module: the classes it defines and their methods; the
                   importer's parsers/importers, the XML writer's Create* steps,
                   the calculation classes and the field keys that trigger them
  transfers.json   TOTAL's field transfers: fields kept equal to each other
                   (a value written into one is copied over the others), grouped
                   by master key; plus copies done in code (photo fields)

    python tools/blueprint.py [--build 0.0.1.3848]

Everything here is regex over minified code: good for finding your way and for
lists a generator must respect, never proof on its own.  A behaviour is
confirmed by experiment (knowledge/errors/CATALOG.md) before a rule rests on it.
"""
from __future__ import annotations

import argparse
import json
import os
import re
from collections import defaultdict
from pathlib import Path

HERE = Path(__file__).resolve().parent
KNOW = HERE.parents[1] / "knowledge" / "total" / "builds"
SNAP = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "uad36-bridge" / "bundle"

CLASS = re.compile(r"\bclass ([A-Za-z_$][\w$]*)(?: extends ([\w$.]+))?\{")
METHOD = re.compile(r"(?:^|[;}{,])\s*(?:static\s+|async\s+|get\s+|set\s+)*([A-Za-z_$][\w$]*)\(([^()]{0,160})\)\{")
KEYWORDS = {"if", "for", "while", "switch", "catch", "function", "return", "with", "constructor"}
CASE = re.compile(r'case"([A-Z][A-Z0-9_\-]{2,})"')


def classes(src: str) -> list[dict]:
    starts = [(m.start(), m.group(1), m.group(2) or "") for m in CLASS.finditer(src)]
    out = []
    for i, (pos, name, base) in enumerate(starts):
        end = starts[i + 1][0] if i + 1 < len(starts) else len(src)
        body = src[pos:end]
        methods = []
        for m in METHOD.finditer(body):
            if m.group(1) not in KEYWORDS and m.group(1) not in methods:
                methods.append(m.group(1))
        out.append({"class": name, "extends": base.split(".")[-1], "chars": len(body),
                    "methods": methods[:150], "case_keys": sorted(set(CASE.findall(body)))[:400]})
    return out


def transfers(src: str) -> dict:
    enum = dict(re.findall(r"StandardTransferMasterKeys\.(\w+)=\"([^\"]+)\"", src))
    groups = defaultdict(list)
    for m in re.finditer(r"new TransferDataItem\(StandardTransferMasterKeys\.(\w+),([^)]*)\)", src):
        args = [a.strip() for a in m.group(2).split(",")]
        strip = lambda a: a.strip('"') if a.startswith('"') else a
        section = strip(args[0]) if args else ""
        field = strip(args[1]) if len(args) > 1 else ""
        base = strip(args[2]) if len(args) > 2 and args[2].startswith('"') else ""
        groups[enum.get(m.group(1), m.group(1))].append(
            {"section": section, "field": field, "base": base or field,
             "use_source_instance": "!1" not in args[3:4], "all_destination_instances": "!0" in args[4:5]})
    return {k: v for k, v in sorted(groups.items())}


def code_photo_copies(src: str) -> list[dict]:
    out = []
    for m in re.finditer(r'sourceField:"(\w+)"', src):
        window = src[max(0, m.start() - 900):m.start() + 200]
        targets = re.findall(r'destinationField:"(\w+)"', window)
        fn = re.findall(r"(\w+)\(\)\{setTimeout", window)
        if targets:
            out.append({"source": m.group(1), "targets": sorted(set(targets)), "in": fn[-1] if fn else ""})
    return out


def adjustment_maps(src: str) -> dict:
    """The writer's own maps: MISMO ComparableAdjustmentType -> grid field
    (`salesComparableAdjustmentMap = {HazardZone: {DsField: "SITE_HAZARD_ZONE_ADJ",
    FmId: "22.03.27"}, ...}`) -- the join between a package's adjustment rows
    and TOTAL's grid rows."""
    out = {}
    for m in re.finditer(r"this\.(\w+Map)=\{", src):
        body, depth, i = [], 0, m.end() - 1
        for j in range(i, min(len(src), i + 40000)):
            depth += {"{": 1, "}": -1}.get(src[j], 0)
            if depth == 0:
                body = src[i:j + 1]
                break
        pairs = re.findall(r'(\w+):\{DsField:"(\w+)",FmId:"([\d.]+)"\}', body)
        if pairs:
            out[m.group(1)] = {k: {"field": f, "fmid": fm} for k, f, fm in pairs}
    return out


#: How the writer's report-level switches read the form -- one pattern per
#: kind of read.  Minified module aliases differ per build, so they are "[\w$.]+".
_SWITCH = [
    ("checkbox", re.compile(r'this\.(\w+)=[\w$.]+\.GetCheckBoxStateBoolean\(this\.dataSet,"(\w+)","(\w+)","([^"]*)",(\d+)\)')),
    ("checkbox-text", re.compile(r'this\.(\w+)=([^,]*?\?)?[\w$.]+\.GetCheckBoxState\(this\.dataSet,"(\w+)","(\w+)","([^"]*)",(\d+)\)')),
    ("selector", re.compile(r'this\.(\w+)=[\w$.]+\.GetSelectorStateBoolean\(this\.dataSet,"(\w+)",(\d+)\)')),
    ("integer", re.compile(r'this\.(\w+)=Number\.parseInt\(this\.dataSet\.GetData(?:Field|Value)\("(\w+)",(\d+)\)')),
    ("value", re.compile(r'this\.(\w+)=this\.dataSet\.GetDataValue\("(\w+)",(\d+)\)(?=[,}])')),
    ("nonempty", re.compile(r'this\.(\w+)=this\.dataSet\.GetDataValue\("(\w+)",(\d+)\)\.length>0(?:&&this\.(\w+)\.length>0)?')),
    ("multiselect", re.compile(r'this\.(\w+)=[\w$.]+\.GetCheckedValues\("(\w+)",(\d+),this\.dataSet\)')),
    ("enumeration", re.compile(r'this\.(\w+)=[\w$.]+\.DisplayValueToMISMOEnum\(this\.dataSet\.GetDataField\("(\w+)"\)')),
    ("sections", re.compile(r'this\.(\w+)=[\w$.]+\.(IncludeInRentChecked)\(\)')),
    ("constant", re.compile(r'this\.(\w+)=(!0|!1|"[^"]*")(?=[,}])')),
]


def common_info(src: str) -> dict:
    """The report-level switches TOTAL's MISMO writer reads before writing
    anything (which approaches were developed, whether there is a sales
    contract, units, ADUs, agency, ...): the class whose constructor sets
    ``LivingUnitExcludingADUCount`` from the form.  These decide which parts of
    the MISMO document TOTAL writes -- the report's configuration as TOTAL
    itself sees it."""
    starts = list(CLASS.finditer(src))
    for i, m in enumerate(starts):
        body = src[m.end():starts[i + 1].start() if i + 1 < len(starts) else len(src)]
        end = body.find("}get ")
        ctor = body[:end] if end > 0 else body
        if "LivingUnitExcludingADUCount=Number.parseInt" not in ctor:
            continue
        switches = []
        for kind, rx in _SWITCH:
            for s in rx.finditer(ctor):
                g = s.groups()
                row = {"name": g[0], "kind": kind}
                if kind == "checkbox":
                    row.update(yes=g[1], no=g[2], mark=g[3], instance=int(g[4]))
                elif kind == "checkbox-text":
                    row.update(only_if=(g[1] or "").rstrip("?"), yes=g[2], no=g[3], mark=g[4], instance=int(g[5]))
                elif kind in ("selector", "integer", "value", "multiselect"):
                    row.update(field=g[1], instance=int(g[2]))
                elif kind == "nonempty":
                    row.update(field=g[1], instance=int(g[2]), and_nonempty=g[3])
                elif kind == "enumeration":
                    row.update(field=g[1])
                elif kind == "sections":
                    row.update(call=g[1])
                elif kind == "constant":
                    row.update(value={"!0": True, "!1": False}.get(g[1], g[1].strip('"')))
                switches.append(row)
        # a later assignment wins, as in the constructor ("SalesComparisonApproachIndicator=!0")
        last = {}
        for row in switches:
            last[row["name"]] = row
        return {"class": m.group(1), "switches": sorted(last.values(), key=lambda r: r["name"])}
    return {}


def form_codes(src: str) -> dict:
    """TOTAL's UAD 3.6 form codes (`Literals.FORM_URAR_1_000 = "UAD-3.6-AR-1.000"`, ...)."""
    return dict(re.findall(r'\.(FORM_\w+)="(UAD-[^"]+)"', src))


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--build", default="0.0.1.3848")
    ap.add_argument("--snapshot", default=str(SNAP))
    a = ap.parse_args(argv)
    mods = Path(a.snapshot) / a.build / "modules"
    if not mods.exists():
        raise SystemExit(f"no snapshot at {mods}: run tools/dump_bundle.py --report <scratch report> first")
    blueprint = {"build": a.build, "modules": []}
    all_transfers, copies, adj_maps, config, codes = {}, [], {}, {}, {}
    for f in sorted(mods.glob("*.js"), key=lambda p: int(p.stem) if p.stem.isdigit() else 0):
        src = f.read_text(encoding="utf-8")
        if not config and "LivingUnitExcludingADUCount=Number.parseInt" in src:
            config = dict(common_info(src), module=f.stem)
        codes.update(form_codes(src))
        cls = classes(src)
        if cls:
            blueprint["modules"].append({"id": f.stem, "chars": len(src), "classes": cls})
        if "new TransferDataItem(" in src:
            all_transfers.update(transfers(src))
        if 'sourceField:"' in src:
            copies += [dict(c, module=f.stem) for c in code_photo_copies(src)]
        if "DsField:" in src:
            adj_maps.update(adjustment_maps(src))
    names = [c["class"] for m in blueprint["modules"] for c in m["classes"]]
    blueprint["pipeline"] = {
        "importer": sorted(n for n in names if n.startswith(("MISMODeserializer", "MismoDeserializer"))),
        "writer": sorted(n for n in names if "Serializer" in n and not n.startswith("MISMODeserializer")),
        "calcs": sorted(n for n in names if n.endswith("Calcs")),
        "validators": sorted(n for n in names if n.endswith(("Validators", "Validation"))),
    }
    out = KNOW / a.build
    out.mkdir(parents=True, exist_ok=True)
    (out / "blueprint.json").write_text(json.dumps(blueprint, indent=1), encoding="utf-8")
    (out / "transfers.json").write_text(json.dumps({"groups": all_transfers, "code_copies": copies}, indent=1),
                                        encoding="utf-8")
    (out / "adjustment_map.json").write_text(json.dumps(adj_maps, indent=1), encoding="utf-8")
    (out / "configuration.json").write_text(json.dumps({"form_codes": codes, "common_info": config}, indent=1),
                                            encoding="utf-8")
    print(f"form codes {codes}; configuration switches {len(config.get('switches', []))} "
          f"(class {config.get('class')}) -> {out / 'configuration.json'}")
    print(f"adjustment maps: {', '.join(f'{k} ({len(v)})' for k, v in adj_maps.items())} -> "
          f"{out / 'adjustment_map.json'}")
    p = blueprint["pipeline"]
    print(f"{len(blueprint['modules'])} modules with classes, {len(names)} classes -> {out / 'blueprint.json'}")
    print(f"importer classes {len(p['importer'])}, writer {len(p['writer'])}, calcs {len(p['calcs'])}, "
          f"validators {len(p['validators'])}")
    print(f"transfer groups {len(all_transfers)} ({sum(len(v) for v in all_transfers.values())} fields), "
          f"code copies {len(copies)} -> {out / 'transfers.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
