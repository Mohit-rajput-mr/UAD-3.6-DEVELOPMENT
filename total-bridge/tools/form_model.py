"""Extract TOTAL's UAD 3.6 form model -- everything the form knows, not what it shows.

A read-only build-time tool.  It writes nothing into TOTAL.  Point it at an open
report (a blank one is best: nothing in it hides anything) and it records, as
data, what the rest of this project needs to know about the form:

live, from the running form
  fields.json        every control in every section, popup and template (the
                     hidden, repeatable structure included): field name, UAD
                     field ID (fmid), control class, section, required flag,
                     display rules, trigger, visibility
  datafields.json    per field name: pick-list items, shared list, default,
                     format, "other" companion field, mutual exclusions
  popups.json        each popup, the field that opens it and the fields in it
  templates.json     the repeatable sections/rows (dwelling, unit, outbuilding,
                     manufactured home, liens, grids) and their fields
  repeatables.json   min/max for every repeatable group
  visibility.json    the visibility rule keys and their instances
  shared_items.json  the shared pick lists
  grids.json         comparable grid managers (sales, rental, GRM)
  section_tree.json  the Report Setup structure (buildings -> units)
  datamodel.json     the data layer's group hierarchy (what a report stores)

static, from the served bundle (same build)
  uid_map.json       MISMO data point -> every TOTAL field that holds it, keyed
                     by the spec's own UID and report field ID
  validators.json    every field-validation registration: field, trigger
                     (LeaveField / SelectClosed / HidePopup / ValueChanged),
                     dependants, rule names, owning validator class
  rtv_messages.json  the messages those rules show
  connector.json     the actions WinTOTAL can ask of the form, and the events
                     the form sends back

    python tools/form_model.py --report "sample blank" --out ../knowledge/total/builds

The bundle is cached under tools/.cache (not committed: it is a la mode's code).
Only the extracted tables are kept.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import subprocess
import sys
import tempfile
from collections import Counter
from datetime import date
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from bridge import sections                 # noqa: E402
from bridge.total import Report             # noqa: E402

BS = chr(92)

# ---------------------------------------------------------------- live model
_LIVE = r"""(() => {
 const e = window.engine, f = e.currentForm, d = e.dataLayer.DataSets.get(f.formName);
 const cls = o => (o && o.constructor && o.constructor.name) || '';
 const short = v => { try { const s = JSON.stringify(v); return s && s.length > 400 ? s.slice(0, 400) + '...' : s; } catch (x) { return String(v); } };
 const rows = [], seen = new Set(), df = {};
 const record = (c, ctx) => {
   const k = [c.fieldName, c.instance, ctx.section || '', ctx.template || '', ctx.popup || ''].join('|');
   if (seen.has(k)) return; seen.add(k);
   const dfield = d.GetDataField(c.fieldName, c.instance || 0) || d.GetDataField(c.fieldName, 0);
   rows.push({field: c.fieldName, instance: c.instance || 0, control: cls(c),
     fmid: c._fmid || (dfield && dfield.fmid) || '', section: ctx.section || '', template: ctx.template || '',
     popup: ctx.popup || '', required: !!c.requiredfield, default_visible: c.defaultVisible !== false,
     visible: !!c._visible, read_only: !!c._readOnly, trigger: !!c.triggerField,
     display_rules: (c.displayRules || []).map(short), string_format: c.stringFormat || '',
     max_chars: c._maxChars || 0, in_data_layer: !!dfield});
   if (dfield && !df[c.fieldName]) df[c.fieldName] = {fmid: dfield.fmid || '', name: dfield.friendlyName || '',
     items: dfield._items || [], shared: dfield.sharedItemsCollectionKey || '', default: String(dfield.defaultValue ?? ''),
     format: dfield.format || '', max_select: dfield.maxSelect ?? null, other_field: dfield.otherInputFn || '',
     mutex: dfield.mutexc || '', excluded: dfield.excludedTerms || '', force_single: dfield.forceSingle || '',
     group: (dfield.parentGroup && dfield.parentGroup.key) || ''};
 };
 const walk = (o, ctx, depth) => {
   if (!o || depth > 60) return;
   for (const c of (o.htmlChildren || [])) {
     if (!c) continue;
     let n = ctx;
     if (cls(c) === 'Section') n = Object.assign({}, ctx, {section: c.key});
     if (c.fieldName) record(c, n);
     walk(c, n, depth + 1);
   }
 };
 walk(f, {}, 0);
 const templates = [];
 for (const [key, t] of f.templates.entries()) {
   const before = rows.length;
   walk(t, {template: key, section: t.key || key}, 0);
   templates.push({key, control: cls(t), fields: rows.slice(before).map(r => r.field)});
 }
 const fieldByGuid = new Map();
 for (const [g, x] of f.fields.entries()) fieldByGuid.set(g, x);
 const popups = [];
 for (const [key, p] of f.popups.entries()) {
   const before = rows.length;
   walk(p, {popup: key}, 0);
   const trig = [...f.triggerFieldMap.entries()].filter(([, pk]) => pk === key)
     .map(([g]) => { const x = fieldByGuid.get(g); return x ? x.fieldName + '#' + (x.instance || 0) : g; });
   popups.push({key, triggers: trig, fields: [...new Set(rows.slice(before).map(r => r.field))]});
 }
 const m = window.__uadSectionManager;
 const tree = (m && m.GetSectionTree ? m.GetSectionTree() : []).map(s => ({key: s.SectionKey,
   instance: s.SectionInstance, identifier: s.SectionIdentifier, caption: s.SectionCaption,
   children: (s.Children || []).map(c => ({key: c.SectionKey, instance: c.SectionInstance}))}));
 const grids = [...d.compManagers.entries()].map(([k, c]) => ({key: k, min: c.MinComps, max: c.MaxComps,
   comps: c.comps, subject_prefix: c.SubjectPrefix, comp_prefix: c.CompPrefix,
   fields: (c.fields || []).length, adjustment_fields: (c.adjFields || []).length,
   row_templates: [...((c.rowTemplates && c.rowTemplates.keys && c.rowTemplates.keys()) || [])],
   section_templates: [...((c.sectionTemplates && c.sectionTemplates.keys && c.sectionTemplates.keys()) || [])]}));
 const model = [];
 const grp = (o, depth, path) => {
   for (const x of (o.dataObjects || [])) {
     if ((x.dataObjects || []).length) {
       model.push({group: x.key, instance: x.instance ?? 0, depth, path,
         fields: x.dataObjects.filter(y => !(y.dataObjects || []).length).map(y => y.key),
         groups: [...new Set(x.dataObjects.filter(y => (y.dataObjects || []).length).map(y => y.key))]});
       if (depth < 12) grp(x, depth + 1, path + '/' + x.key);
     }
   }
 };
 grp(d, 0, '');
 return JSON.stringify({
   form: f.formName, title: f.title, version: f.version, build: f.buildNumber,
   fields: rows, datafields: df, templates, popups,
   repeatables: [...d.repeatableMin.keys()].map(k => ({key: k, min: d.repeatableMin.get(k), max: d.repeatableMax.get(k)})),
   visibility: {master_keys: Object.fromEntries(d.visibilityRules.masterKeys),
                rules: Object.fromEntries(d.visibilityRules.rules)},
   shared_items: Object.fromEntries(d.sharedItemsCollections),
   grids, section_tree: tree, datamodel: model,
   defaults: d.fieldsWithDefaultValues.map(x => ({field: x.key, instance: x.instance, default: String(x.defaultValue ?? '')}))
 });
})()"""


# -------------------------------------------------------------- static tables
def _enclosing(txt: str, pos: int) -> int:
    depth, i = 0, pos
    while i > 0:
        c = txt[i]
        if c == '}':
            depth += 1
        elif c == '{':
            if depth == 0:
                return i
            depth -= 1
        i -= 1
    return -1


def _match(txt: str, start: int) -> int:
    depth, i, q = 0, start, None
    while i < len(txt):
        c = txt[i]
        if q:
            if c == BS:
                i += 2
                continue
            if c == q:
                q = None
        elif c in '"\'`':
            q = c
        elif c == '{':
            depth += 1
        elif c == '}':
            depth -= 1
            if depth == 0:
                return i
        i += 1
    return -1


def _assigned_object(txt: str, anchor: str) -> str:
    """The whole object literal assigned to a name, found from a key inside it."""
    pos = txt.find(anchor)
    if pos < 0:
        raise LookupError(anchor)
    s = _enclosing(txt, pos)
    while s > 0 and txt[s - 1] != '=':
        s = _enclosing(txt, s - 1)
    return txt[s:_match(txt, s) + 1]


def _js_to_json(literal: str) -> object:
    """Evaluate a pure-data object literal with Node (no page, no network)."""
    with tempfile.NamedTemporaryFile("w", suffix=".js", delete=False, encoding="utf-8") as fh:
        fh.write(literal)
        path = fh.name
    script = ("const fs=require('fs');process.stdout.write(JSON.stringify("
              "(0,eval)('('+fs.readFileSync(process.argv[1],'utf8')+')')))")
    out = subprocess.run(["node", "-e", script, path], capture_output=True, text=True,
                         encoding="utf-8", check=True)
    Path(path).unlink(missing_ok=True)
    return json.loads(out.stdout)


_VALIDATOR = re.compile(
    r'this\.addValidator\("([A-Za-z0-9_\-.]+)",dataChangedEventHandler\.\$H\.([A-Za-z]+)'
    r'(?:,\[([^\]]*)\])?\)((?:\.addRule\((?:[^()]|\((?:[^()]|\([^()]*\))*\))*\))+)')


def static_tables(txt: str) -> dict:
    classes = [(m.start(), m.group(1)) for m in re.finditer(r'class ([A-Za-z0-9_$]+)(?: extends [A-Za-z0-9_$.]+)?\{', txt)]

    def owner(pos):
        best = ""
        for s, n in classes:
            if s > pos:
                break
            best = n
        return best

    validators = []
    for m in _VALIDATOR.finditer(txt):
        field, trigger, deps, rules = m.groups()
        validators.append({
            "field": field, "trigger": trigger,
            "dependants": re.findall(r'name:"([^"]+)"', deps or ""),
            "rule_names": re.findall(r',"([A-Za-z][A-Za-z0-9]*)"\)(?=\.addRule|$)', rules),
            "rules": rules.count(".addRule("),
            "not_empty": "commonValidationRules.z2" in rules,
            "validator_class": owner(m.start())})
    uid_map = _js_to_json(_assigned_object(txt, "MeasurementStandardPublisherType:[{BaseDataFieldName"))
    # the validation messages are a module export: {_default:{_default:{...}}, amenities:{...}, ...}
    start = txt.find("{_default:{_default:{")
    if start < 0 or txt.find('unitssfglarequiredcondition:"', start) < 0:
        raise LookupError("validation message table not found -- the bundle changed shape")
    messages = _js_to_json(txt[start:_match(txt, start) + 1])
    i = txt.find("async ExecuteReportAction(")
    j = txt.find("OnSmartAdjustEvent", i) if i >= 0 else -1
    actions = sorted(set(re.findall(r'case"([a-z0-9]+)"', txt[i:i + 40000]))) if i >= 0 else []
    events = Counter(re.findall(r'FireEvent\("([A-Za-z_]+)"', txt))
    return {"validators": validators, "uid_map": uid_map, "rtv_messages": messages,
            "connector": {"report_actions_from_wintotal": actions, "events_to_wintotal": dict(events)}}


# ------------------------------------------------------------ derived profile
def validation_profile(folder: Path) -> list[dict]:
    """Every TOTAL validation rule joined to the MISMO data points it guards.

    validators.json names a base field (``DP_FINTYP1``); uid_map.json lists each
    data point's placements by the same base name (with ``GSU_``/``GC1_`` grid
    prefixes); rtv_messages.json holds the text per section, field and rule.
    The join says, for example, that TOTAL requires a financing type on every
    sales comparable (CATALOG E-030) -- read from TOTAL's own tables.
    """
    validators = json.loads((folder / "validators.json").read_text(encoding="utf-8"))
    uid_map = json.loads((folder / "uid_map.json").read_text(encoding="utf-8"))
    messages = json.loads((folder / "rtv_messages.json").read_text(encoding="utf-8"))
    by_base: dict = {}
    for dp, rows in uid_map.items():
        for x in rows:
            by_base.setdefault(x["BaseDataFieldName"], []).append(
                {"data_point": dp, "uid": x.get("UID"), "fmid": x.get("FMID"),
                 "grid": x.get("GridManagerKey", ""), "prefix": x.get("FieldPrefix", ""),
                 "context": x.get("AdditionalContext", "")})
    out = []
    for v in validators:
        field = v["field"]
        sect = next((s for s, fields in messages.items() if isinstance(fields, dict) and field in fields), "")
        texts = messages.get(sect, {}).get(field, {}) if sect else {}
        dps = by_base.get(field, [])
        out.append({
            "field": field, "section": sect, "validator_class": v["validator_class"], "trigger": v["trigger"],
            "rules": v["rule_names"] or (["notempty"] if v["not_empty"] else []),
            "messages": texts, "dependants": v["dependants"],
            "grid": sorted({d["grid"] for d in dps if d["grid"]}),
            "data_points": sorted({(d["data_point"], d["uid"], d["fmid"]) for d in dps}),
        })
    for row in out:
        row["data_points"] = [{"data_point": a, "uid": b, "fmid": c} for a, b, c in row["data_points"]]
    return out


# ---------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", help="name of an open TOTAL report (read only)")
    ap.add_argument("--out", required=True, help="builds folder; a subfolder per TOTAL build is written")
    ap.add_argument("--derive", metavar="BUILD",
                    help="only recompute derived files for an already extracted build (no TOTAL needed)")
    a = ap.parse_args(argv)
    if a.derive:
        folder = Path(a.out) / a.derive
        prof = validation_profile(folder)
        (folder / "validation_profile.json").write_text(json.dumps(prof, indent=1, ensure_ascii=False),
                                                        encoding="utf-8")
        print(f"validation_profile.json: {len(prof)} rules, "
              f"{sum(1 for p in prof if p['data_points'])} joined to data points, "
              f"{sum(1 for p in prof if p['grid'])} on grids")
        return 0
    if not a.report:
        ap.error("--report is required unless --derive is given")

    with Report.attach(a.report, allow_signed=True) as r:
        sections.manager(r)
        src = r.page.evaluate("[...document.scripts].map(s=>s.src).find(s=>/index\\.js$/.test(s))")
        build = re.search(r"/(\d+\.\d+\.\d+\.\d+)/", src).group(1)
        bundle = r.page.evaluate(f"fetch({json.dumps(src)}).then(x=>x.text())", await_promise=True)
        live = json.loads(r.page.evaluate(_LIVE))

    cache = HERE / ".cache"
    cache.mkdir(exist_ok=True)
    (cache / f"index.{build}.js").write_text(bundle, encoding="utf-8")
    out = Path(a.out) / build
    out.mkdir(parents=True, exist_ok=True)

    tables = static_tables(bundle)
    files = {
        "fields.json": live["fields"], "datafields.json": live["datafields"],
        "templates.json": live["templates"], "popups.json": live["popups"],
        "repeatables.json": live["repeatables"], "visibility.json": live["visibility"],
        "shared_items.json": live["shared_items"], "grids.json": live["grids"],
        "section_tree.json": live["section_tree"], "datamodel.json": live["datamodel"],
        "defaults.json": live["defaults"],
        "uid_map.json": tables["uid_map"], "validators.json": tables["validators"],
        "rtv_messages.json": tables["rtv_messages"], "connector.json": tables["connector"],
    }
    for name, data in files.items():
        (out / name).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    (out / "validation_profile.json").write_text(
        json.dumps(validation_profile(out), indent=1, ensure_ascii=False), encoding="utf-8")

    fields = live["fields"]
    index = {
        "form": live["form"], "title": live["title"], "form_version": live["version"],
        "form_build": live["build"], "web_engine_build": build,
        "bundle_sha256": hashlib.sha256(bundle.encode("utf-8")).hexdigest(),
        "extracted": date.today().isoformat(), "from_report": a.report,
        "counts": {
            "controls": len(fields),
            "distinct_field_names": len({x["field"] for x in fields}),
            "controls_with_fmid": sum(1 for x in fields if x["fmid"]),
            "distinct_fmids": len({x["fmid"] for x in fields if x["fmid"]}),
            "controls_in_templates": sum(1 for x in fields if x["template"]),
            "controls_in_popups": sum(1 for x in fields if x["popup"]),
            "controls_hidden_by_default": sum(1 for x in fields if not x["default_visible"]),
            "controls_with_display_rules": sum(1 for x in fields if x["display_rules"]),
            "templates": len(live["templates"]), "popups": len(live["popups"]),
            "repeatable_groups": len(live["repeatables"]), "shared_lists": len(live["shared_items"]),
            "validators": len(tables["validators"]),
            "validators_by_trigger": dict(Counter(v["trigger"] for v in tables["validators"])),
            "mismo_data_points": len(tables["uid_map"]),
            "mismo_field_placements": sum(len(v) for v in tables["uid_map"].values()),
            "wintotal_actions": len(tables["connector"]["report_actions_from_wintotal"]),
        },
        "files": sorted(files),
    }
    (out / "index.json").write_text(json.dumps(index, indent=1), encoding="utf-8")
    print(json.dumps(index, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
