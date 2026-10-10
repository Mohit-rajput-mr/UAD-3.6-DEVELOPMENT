"""Which report is open, and what kind of report it is.

UAD 3.6 has no form numbers -- "the data that describes the subject property
drives the appraisal report, not a form type/number" (UAD FAQ 9).  So "is this
a 1025?" is answered from three authorities, each read rather than typed:

1. **TOTAL's form** -- which UAD 3.6 form the page carries: URAR, Completion
   Report, Restricted Appraisal Update, or a mobile variant.  TOTAL's own form
   codes, extracted from its code (``builds/<build>/configuration.json``).
2. **TOTAL's configuration** -- the report-level switches TOTAL's MISMO writer
   reads before it writes anything (approaches developed, sales contract, units,
   ADUs, agency, revision history ...; same file), its section list (buildings,
   unit interiors, ADUs, outbuildings, manufactured homes) and its comparable
   grids.  This is the report as TOTAL itself will deliver it.
3. **The GSE property type** -- the six data points *Functioning without Form
   Numbers* (Fannie Mae / Freddie Mac, v1.1) names, and the legacy form(s) their
   values correspond to, or "atypical" (``engine/spec/legacy_forms.json``).

Everything works on a **live report** (read from TOTAL's data layer; nothing is
written) and on a **MISMO file** (the portable package before import, or TOTAL's
own XML after), so a package and the report it became can be compared.

    python -m bridge.cli detect                 # every open report
    python -m bridge.cli detect --xml case.xml  # a package

How the GSE table is read -- one row of it does not read literally.  For 1004C
and 1025 its *Project Legal Structure* cell says "Condominium or Cooperative",
although both families plainly include properties in no project (its own 1004C
description starts "Manufactured Home, including: In a PUD"; a 2-4 unit
building is usually in none).  So matching runs twice: first literally, then,
only if nothing matched, with every "A or B" cell also admitting the data
point's absence.  The result says which reading matched.  Checked on the twelve
D-1 samples (tests/test_detect.py).
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from lxml import etree

REPO = Path(__file__).resolve().parents[2]
SPEC = REPO / "engine" / "spec"
BUILDS = REPO / "knowledge" / "total" / "builds"
MISMO = "http://www.mismo.org/residential/2009/schemas"
M = "{%s}" % MISMO


# ------------------------------------------------------------ spec tables
def _norm(text) -> str:
    return re.sub(r"[^a-z0-9]", "", str(text).lower())


@lru_cache(maxsize=1)
def legacy_table() -> dict:
    return json.loads((SPEC / "legacy_forms.json").read_text(encoding="utf-8"))


@lru_cache(maxsize=1)
def _enumerations() -> tuple[dict, dict]:
    """A-1's enumerations: UID -> {normalised display text or enumeration:
    enumeration}, and (UID, FID) -> the enumerations shown at that FID (a
    checkbox such as "Condominium" at 3.011 stands for one enumeration)."""
    by_uid: dict[str, dict[str, str]] = {}
    by_fid: dict[tuple[str, str], set[str]] = {}
    for row in json.loads((SPEC / "enumerations.json").read_text(encoding="utf-8")):
        uid, enum = row.get("Unique ID"), row.get("Supported Enumerations")
        if not uid or not enum:
            continue
        table = by_uid.setdefault(uid, {})
        table[_norm(enum)] = enum
        disp = next((v for k, v in row.items() if k.startswith("Output Report Display Text")), "") or ""
        first = disp.split("\n")[0].strip()
        if first and not first.startswith("<<") and _norm(first) not in ("yes", "no"):
            table.setdefault(_norm(first), enum)
        for loc in (row.get("Report Location") or "").splitlines():
            m = re.match(r"\s*([\d.]+):", loc)
            if m:
                by_fid.setdefault((uid, m.group(1)), set()).add(enum)
    return by_uid, by_fid


def to_enumeration(uid: str, raw: str) -> str:
    """A value as the form shows it -> A-1's enumeration (unchanged when it is
    not one of the data point's enumerations: a count, a date, a boolean)."""
    if is_indicator(uid):                              # A-1 displays true / false as Yes / No
        return {"yes": "true", "no": "false"}.get(_norm(raw), raw)
    return _enumerations()[0].get(uid, {}).get(_norm(raw), raw)


def is_indicator(uid: str) -> bool:
    """A true/false data point (A-1 lists exactly those two, or none)."""
    table = _enumerations()[0].get(uid)
    return table is None or set(table.values()) == {"true", "false"}


@lru_cache(maxsize=1)
def _xpaths() -> dict[str, str]:
    """UID -> A-1's xPath for its data point."""
    out: dict[str, str] = {}
    for row in json.loads((SPEC / "delivery_spec.json").read_text(encoding="utf-8")):
        uid, name = row.get("Unique ID"), row.get("MISMO Data Point Name")
        if uid and name and uid not in out:
            out[uid] = row["MISMO xPath"].rstrip("/") + "/" + name
    return out


def drivers() -> list[dict]:
    """The six property-type data points: label, UID, FIDs, word -> enumeration."""
    return legacy_table()["drivers"]


def targets() -> list[tuple[str, str]]:
    """(name, UID) of everything detection reads: the six drivers, then the data
    points their notes depend on (Construction Method "does not apply" to a
    high-, mid- or low-rise, which StructuralDesignType says)."""
    out = [(d["label"], d["uid"]) for d in drivers()]
    for d in drivers():
        x = d.get("not_applicable_when")
        if x and (x["data_point"], x["uid"]) not in out:
            out.append((x["data_point"], x["uid"]))
    return out


# ------------------------------------------------------------ the six values
@dataclass
class Drivers:
    """The six data points' values, as MISMO enumerations / "true" / counts.

    ``values[label]`` is a list: a report with several buildings can carry
    several construction methods.  ``sources`` says where each value was read
    (field or xPath) -- the thing a diagnostic points at."""
    values: dict[str, list[str]] = field(default_factory=dict)
    sources: dict[str, list[dict]] = field(default_factory=dict)
    disagreements: list[dict] = field(default_factory=list)

    def as_text(self) -> str:
        return "; ".join(f"{k}: {'/'.join(v) if v else '-'}" for k, v in self.values.items())

    @property
    def six(self) -> dict[str, list[str]]:
        labels = {d["label"] for d in drivers()}
        return {k: v for k, v in self.values.items() if k in labels}


def drivers_from_xml(source) -> Drivers:
    """The six values from a MISMO document (path, bytes or text), read at A-1's
    xPaths below the subject PROPERTY."""
    if isinstance(source, (str, Path)) and Path(str(source)).exists():
        root = etree.parse(str(source)).getroot()
    else:
        data = source.encode("utf-8") if isinstance(source, str) else source
        root = etree.fromstring(data)
    subject = [p for p in root.iter(M + "PROPERTY") if p.get("ValuationUseType") == "SubjectProperty"]
    out = Drivers()
    for label, uid in targets():
        path = _xpaths().get(uid, "")
        if "/PROPERTIES/PROPERTY/" in path:
            nodes, steps = subject, path.split("/PROPERTIES/PROPERTY/", 1)[1].split("/")
        else:
            nodes, steps = [root], path.split("/")[1:]
        for step in steps:
            nodes = [c for n in nodes for c in n.findall(M + step)]
        vals: list[str] = []
        for n in nodes:
            t = to_enumeration(uid, (n.text or "").strip())
            if t and t not in vals:
                vals.append(t)
        out.values[label] = vals
        out.sources[label] = [{"xpath": path, "values": vals}]
    return out


# ------------------------------------------------------------ legacy forms
def _allowed(label: str, words: list[str]) -> set[str]:
    table = next(d for d in drivers() if d["label"] == label)["enumerations"]
    return {table.get(w) or w for w in words}


def _check(label: str, cell: dict, found: "Drivers", relaxed: bool) -> str:
    """'' when the value satisfies the cell, else why not."""
    if not cell["cell"]:
        return ""                                   # the document leaves it open
    have = found.values.get(label, [])
    allowed = _allowed(label, cell["values"])
    if not allowed:                                  # a dash: must be absent
        return "" if not have else f"is {'/'.join(have)}; the form has none"
    if not have:
        x = next(d for d in drivers() if d["label"] == label).get("not_applicable_when")
        rise = set(found.values.get(x["data_point"], [])) & set(x["values"]) if x else set()
        if rise:
            # "does not apply" to this structure: the value is unknown, which
            # satisfies the general cell (every ordinary method) but not a form
            # defined by one particular method -- a high-rise unit is not
            # thereby a manufactured home
            widest = max(len(_allowed(label, f["drivers"][label]["values"])) for f in legacy_table()["forms"])
            if len(allowed) == widest:
                return ""
            return f"not applicable to a {'/'.join(sorted(rise))} structure; the form has {cell['cell']}"
        if relaxed and " or " in cell["cell"]:
            return ""
        return f"missing; the form has {cell['cell']}"
    extra = [v for v in have if v not in allowed]
    return f"is {'/'.join(extra)}; the form has {cell['cell']}" if extra else ""


def legacy(found: Drivers) -> dict:
    """The legacy form(s) these values correspond to, per the GSE mapping."""
    table = legacy_table()
    result = {"forms": [], "reading": None, "atypical": None, "nearest": [],
              "source": f"{table['source']['file']} (v{table['source']['version']}, {table['source']['date']})"}
    for relaxed in (False, True):
        scored = []
        for form in table["forms"]:
            why = {label: _check(label, cell, found, relaxed)
                   for label, cell in form["drivers"].items()}
            misses = {k: v for k, v in why.items() if v}
            scored.append((len(misses), form, misses))
        hits = [f for n, f, _ in scored if n == 0]
        if hits:
            result["forms"] = [f"{f['fannie_mae']} ({f['freddie_mac']})" if f["freddie_mac"] != "-"
                               else f["fannie_mae"] for f in hits]
            result["family"] = sorted({f["family"] for f in hits})
            result["reading"] = "relaxed" if relaxed else "literal"
            break
        if relaxed:
            scored.sort(key=lambda t: t[0])
            result["nearest"] = [{"form": f["fannie_mae"], "differs": m} for _, f, m in scored[:2]]
    for ex in table["atypical"]["examples"]:
        if all(not _check(label, cell, found, False)
               for label, cell in ex["drivers"].items()):
            result["atypical"] = ex["name"]
            break
    if not result["forms"] and not result["atypical"]:
        result["atypical_kinds"] = table["atypical"]["listed"]
    return result


# ------------------------------------------------------------ TOTAL, live
def _build_of(page) -> str:
    src = page.evaluate("(document.querySelector('script[src*=\"index.js\"]')||{}).src || location.href") or ""
    m = re.search(r"/(\d+\.\d+\.\d+\.\d+)/", src)
    return m.group(1) if m else ""


def _build_dir(build: str) -> Path:
    if build and (BUILDS / build).exists():
        return BUILDS / build
    known = sorted((p for p in BUILDS.iterdir() if p.is_dir() and re.match(r"\d+\.\d+\.\d+\.\d+$", p.name)),
                   key=lambda p: [int(x) for x in p.name.split(".")])
    return known[-1]


def _version(p: Path) -> list[int]:
    return [int(x) for x in p.name.split(".")]


def _json(build_dir: Path, name: str):
    """A table extracted from one WinTOTAL build.  Not every capture recorded
    every table (3886 and 3894 have no configuration.json, defaults.json or
    uid_map.json; their DIFF_FROM_ notes show the controls, validators and
    MISMO placements unchanged), so a table a capture lacks is read from the
    newest earlier capture that has it -- not silently taken as empty, which
    left every unstated switch unreported (T-1017)."""
    p = build_dir / name
    if not p.exists() and re.match(r"\d+\.\d+\.\d+\.\d+$", build_dir.name):
        earlier = sorted((b for b in build_dir.parent.iterdir()
                          if b.is_dir() and re.match(r"\d+\.\d+\.\d+\.\d+$", b.name)
                          and _version(b) < _version(build_dir) and (b / name).exists()),
                         key=_version)
        if earlier:
            p = earlier[-1] / name
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None


_STATE = r"""((args) => {
  const e = window.engine, f = e.currentForm, ri = e.ReportInfo || {};
  const d = e.dataLayer.DataSets.get(f.formName);
  const sm = window.__uadSectionManager;
  if (!window.__uadIndicator && window.__uadReq) {
    const req = window.__uadReq;
    for (const id of Object.keys(req.m || {})) {
      let m; try { m = req(id); } catch (x) { continue; }
      if (!m) continue;
      for (const k of Object.keys(m)) {
        const v = m[k];
        if (typeof v === 'function' && typeof v.GetCheckBoxStateBoolean === 'function'
            && typeof v.GetSelectorStateBoolean === 'function') { window.__uadIndicator = v; break; }
      }
      if (window.__uadIndicator) break;
    }
  }
  const I = window.__uadIndicator;
  const obj = (k, i) => { try { return d.GetDataObject(k, i || 0); } catch (x) { return undefined; } };
  const raw = (k, i) => { const o = obj(k, i); return o === undefined ? null : String(o.value ?? ''); };
  const ask = fn => { try { const v = fn(); return v === undefined ? null : v; } catch (x) { return null; } };

  // the writer's switches, each evaluated the way TOTAL evaluates it
  const sw = {};
  for (const s of args.switches) {
    const r = {kind: s.kind};
    if (s.kind === 'checkbox' || s.kind === 'checkbox-text') {
      r.yes = raw(s.yes, s.instance); r.no = raw(s.no, s.instance);
      r.fields = [s.yes, s.no];
      r.value = I ? ask(() => I.GetCheckBoxStateBoolean(d, s.yes, s.no, s.mark, s.instance)) : null;
      if ((r.yes || '').trim() && (r.no || '').trim()) r.conflict = true;
      if (s.only_if) r.only_if = s.only_if;
    } else if (s.kind === 'selector') {
      r.raw = raw(s.field, s.instance); r.fields = [s.field];
      r.value = I ? ask(() => I.GetSelectorStateBoolean(d, s.field, s.instance)) : null;
    } else if (s.kind === 'integer') {
      r.raw = raw(s.field, s.instance); r.fields = [s.field];
      const n = parseInt(r.raw); r.value = isNaN(n) ? null : n;
    } else if (s.kind === 'value' || s.kind === 'enumeration' || s.kind === 'nonempty') {
      r.raw = raw(s.field, s.instance || 0); r.fields = [s.field]; r.value = r.raw;
    } else if (s.kind === 'multiselect') {
      const o = obj(s.field, s.instance); r.fields = [s.field];
      const delim = o && o.delimiter ? (o.delimiter === 'br' ? '<br>' : o.delimiter) : '<br>';
      r.value = o ? String(o.value ?? '').split(delim).filter(Boolean) : [];
    } else if (s.kind === 'sections') {
      r.value = sm && typeof sm[s.call] === 'function' ? ask(() => sm[s.call]()) : null;
    } else if (s.kind === 'constant') {
      r.value = s.value;
    }
    sw[s.name] = r;
  }
  for (const s of args.switches)                      // "X.length>0 && Y.length>0"
    if (s.kind === 'nonempty') {
      const other = s.and_nonempty ? sw[s.and_nonempty] : null;
      sw[s.name].value = !!(sw[s.name].raw || '').length &&
                         (!other || !!(other.value || []).length);
    }

  // the values behind the six property-type data points, every placement
  const vals = {};
  const want = new Set(args.fields);
  const walk = o => { for (const x of (o.dataObjects || [])) {
      if ((x.dataObjects || []).length) { walk(x); continue; }
      if (want.has(x.key)) (vals[x.key] = vals[x.key] || []).push([x.instance ?? 0, String(x.value ?? '').trim()]);
  } };
  walk(d);

  const plain = o => { const r = {}; for (const k of Object.keys(o || {})) { const v = o[k];
      if (v === null || ['string', 'number', 'boolean'].includes(typeof v)) r[k] = v; } return r; };
  const grids = {};
  for (const [k, g] of d.compManagers || [])
    grids[k] = {columns: g.comps, min: g.MinComps, max: g.MaxComps,
                subject: g.SubjectPrefix, comparable: g.CompPrefix};
  return {
    name: ri.Description || '', report_id: ri.Proj2000ID || '', major_form: ri.MajorFormKey || '',
    order_form: ri.OrderFormKey || '', counts: {comps: ri.Comps, rentals: ri.Rentals, listings: ri.Listings},
    form: f.formName, title: f.title, version: f.version,
    signed: e.IsSigned ? ask(() => e.IsSigned()) : null,
    section_on_screen: e.currentActiveSectionKey || '',
    section_keys: ask(() => e.GetAllSectionKeys()) || [],
    visible: document.visibilityState, focused: document.hasFocus(),
    multi_family: sm ? ask(() => sm.IsMultiFamilyReport()) : null,
    sections: sm ? sm.GetSections().map(s => { const p = plain(s);
        return {key: p.sectionKey, instance: p.sectionInstance, prefix: p.keyPrefix,
                identifier: p.SectionIdentifier, description: p.Description, choice: p.DropDownValue,
                adu: !!(p.InteriorIsADU || p.OutbuildingIsADU), adu_manufactured: !!p.AduIsManufacturedHome,
                in_rent_schedule: !!p.IncludedInRentSchedule, parent: p.ParentGuid, guid: p.sectionGuid}; }) : [],
    grids, switches: sw, values: vals,
    indicator_helper: !!I
  };
})"""


def _placements(uid_map: dict) -> dict[str, list[dict]]:
    """UID -> TOTAL's fields for it (from the build's MISMO<->field table)."""
    out: dict[str, list[dict]] = {}
    for rows in uid_map.values():
        for x in rows:
            out.setdefault(x.get("UID"), []).append(x)
    return out


def _live_drivers(state: dict, uid_map: dict) -> Drivers:
    """The six values from the data layer.  A field of the section it belongs
    to is the source; Summary fields and the grid's subject column mirror it --
    when a mirror holds something else, TOTAL shows one answer and may deliver
    another, which is worth a finding of its own."""
    by_uid = _placements(uid_map)
    by_fid = _enumerations()[1]
    prefixes = {s["prefix"] for s in state["sections"] if s.get("prefix")}
    vals = state["values"]
    out = Drivers()
    for label, uid in targets():
        boolean = is_indicator(uid)
        primary, mirrors = [], []
        for p in by_uid.get(uid, []):
            base, pre = p["BaseDataFieldName"], p.get("FieldPrefix", "")
            keys = [pre + base] if pre else [base] + [x + base for x in prefixes]
            for key in keys:
                for inst, whole in vals.get(key, []):
                    # a multi-select holds its choices joined by TOTAL's "<br>"
                    for raw in [x.strip() for x in whole.split("<br>") if x.strip()] or [whole]:
                        value = _read_value(uid, p, key, inst, raw, vals, by_fid, boolean)
                        if value is None:
                            continue
                        row = {"field": key, "instance": inst, "raw": raw, "value": value,
                               "fmid": p.get("FMID"), "section": p.get("Section")}
                        (mirrors if pre or p.get("Section") == "Summary" else primary).append(row)
        chosen = primary or mirrors
        values: list[str] = []
        for r in chosen:
            if r["value"] and r["value"] not in values:
                values.append(r["value"])
        out.values[label] = values
        out.sources[label] = primary + mirrors
        for r in mirrors:
            if primary and r["value"] and r["value"] not in values:
                out.disagreements.append({"driver": label, "field": r["field"], "shows": r["value"],
                                          "source_holds": values})
        sources = [p for p in by_uid.get(uid, []) if not p.get("FieldPrefix") and p.get("Section") != "Summary"]
        if not primary and mirrors and sources:
            out.disagreements.append({"driver": label, "field": mirrors[0]["field"], "shows": mirrors[0]["value"],
                                      "source_holds": [], "source_fields": [p["BaseDataFieldName"] for p in sources]})
    return out


def _read_value(uid, placement, key, inst, raw, vals, by_fid, boolean):
    """One field's value as an enumeration / "true" / "false" / count, or None."""
    base = placement["BaseDataFieldName"]
    if base.endswith("_YES"):                          # a checkbox standing for a value
        no = [v for i, v in vals.get(key[:-4] + "_NO", []) if i == inst]
        if raw:
            one = by_fid.get((uid, placement.get("FMID") or ""), set())
            return next(iter(one)) if len(one) == 1 and not boolean else "true"
        if boolean and no and no[0]:
            return "false"
        return None
    return to_enumeration(uid, raw) if raw else None


def form_family(form_code: str, codes: dict) -> str:
    """TOTAL's form code -> its name for it (FORM_URAR_1_000 -> "URAR")."""
    for name, code in (codes or {}).items():
        if code == form_code:
            return re.sub(r"^FORM_|_\d+_\d+$", "", name)
    return ""


def fields_to_read(uid_map: dict) -> list[str]:
    names = set()
    for _label, uid in targets():
        for p in _placements(uid_map).get(uid, []):
            base, pre = p["BaseDataFieldName"], p.get("FieldPrefix", "")
            names.add(pre + base)
            if base.endswith("_YES"):
                names.add(pre + base[:-4] + "_NO")
    return sorted(names)


def describe(report) -> dict:
    """Everything detection knows about one open report (reads only)."""
    from . import sections
    try:
        sections.manager(report)
    except RuntimeError:
        pass
    build = _build_of(report.page)
    bdir = _build_dir(build)
    config = _json(bdir, "configuration.json") or {}
    uid_map = _json(bdir, "uid_map.json") or {}
    # section-prefixed copies of section fields (DE1_CONST_METHOD ...) are
    # added once the section list is known; read them all in one pass
    base_fields = fields_to_read(uid_map)
    switches = (config.get("common_info") or {}).get("switches", [])
    first = report.page.evaluate(f"({_STATE})({json.dumps({'switches': switches, 'fields': base_fields})})")
    prefixes = sorted({s["prefix"] for s in first["sections"] if s.get("prefix")})
    extra = [p + f for p in prefixes for f in base_fields]
    state = report.page.evaluate(f"({_STATE})({json.dumps({'switches': switches, 'fields': base_fields + extra})})")
    found = _live_drivers(state, uid_map)
    state.update(build=build, knowledge_build=bdir.name,
                 family=form_family(state["form"], config.get("form_codes")),
                 drivers=found.six, context=found.values, driver_sources=found.sources,
                 driver_disagreements=found.disagreements, legacy=legacy(found),
                 structure=structure(state["sections"]))
    return state


def structure(secs: list[dict]) -> dict:
    """Buildings, unit interiors, ADUs, outbuildings, manufactured homes."""
    count = lambda key, **kw: sum(1 for s in secs if s["key"] == key
                                  and all(s.get(k) == v for k, v in kw.items()))
    return {"buildings": count("dwelling-exterior"),
            "units": count("interior", adu=False),
            "adu_interiors": count("interior", adu=True),
            "outbuildings": count("outbuilding"),
            "adu_outbuildings": count("outbuilding", adu=True),
            "manufactured_homes": count("manufactured"),
            "units_in_rent_schedule": sum(1 for s in secs if s["key"] == "interior" and s["in_rent_schedule"])}


def open_reports(host=None, port=None) -> list[dict]:
    """Every UAD 3.6 report TOTAL has loaded, described, with the active one
    marked: the page TOTAL shows (visible) and, among several, the focused one."""
    from . import cdp
    from .total import Report
    host, port = host or cdp.DEFAULT_HOST, port or cdp.DEFAULT_PORT
    out = []
    for r in Report.open_reports(host, port):
        rep = Report(cdp.Page(r["ws"]), r["name"], bool(r["signed"]))
        try:
            out.append(dict(describe(rep), ws=r["ws"]))
        finally:
            rep.page.close()
    shown = [r for r in out if r["visible"] == "visible"]
    focused = [r for r in shown if r["focused"]]
    active = focused[0] if len(focused) == 1 else shown[0] if len(shown) == 1 else \
        out[0] if len(out) == 1 else None
    for r in out:
        r["active"] = r is active
    return out


# ------------------------------------------------------------ printing
def summary(state: dict) -> list[str]:
    lg, st, sw = state["legacy"], state["structure"], state["switches"]
    on = lambda k: (sw.get(k) or {}).get("value")
    forms = ", ".join(lg["forms"]) or (f"atypical: {lg['atypical']}" if lg["atypical"] else "no legacy form")
    lines = [
        f"{state['name']!r}{'  [ACTIVE]' if state.get('active') else ''}{'  [SIGNED]' if state.get('signed') else ''}",
        f"  form        {state['form']} = {state['family'] or '?'} ({state['title']}), web engine {state['build']}"
        + ("" if state["build"] == state["knowledge_build"] else f"  [knowledge is for {state['knowledge_build']}]"),
        f"  report id   {state['report_id']}",
        f"  property    {state['drivers'] and '; '.join(f'{k}: {chr(47).join(v) or chr(45)}' for k, v in state['drivers'].items())}",
        f"  legacy      {forms}" + (f"  (reading: {lg['reading']})" if lg["reading"] else ""),
        f"  structure   {st['buildings']} building(s), {st['units']} unit(s), {st['adu_interiors']} ADU interior(s), "
        f"{st['outbuildings']} outbuilding(s), {st['manufactured_homes']} manufactured; TOTAL multi-family: {state['multi_family']}",
        "  grids       " + ", ".join(f"{k} {g['columns']} (min {g['min']})" for k, g in state["grids"].items()),
        "  approaches  " + ", ".join(f"{k.replace('ApproachIndicator', '')}={on(k)}" for k in sorted(sw)
                                     if k.endswith("ApproachIndicator")),
        f"  sections    {len(state['section_keys'])}: {', '.join(state['section_keys'])}",
    ]
    for d in state["driver_disagreements"]:
        lines.append(f"  ! {d['driver']}: {d['field']} shows {d['shows']} but the source holds {d['source_holds']}")
    for k, v in sw.items():
        if v.get("conflict"):
            lines.append(f"  ! {k}: both {v['fields'][0]} and {v['fields'][1]} are marked -- TOTAL writes no value")
    if not lg["forms"] and lg.get("nearest"):
        for n in lg["nearest"]:
            lines.append(f"  nearest {n['form']}: " + "; ".join(f"{k} {v}" for k, v in n["differs"].items()))
    return lines


def hud_context(state: dict) -> dict:
    """What the panel inside this report shows about it (bridge/hud.py)."""
    lg, st, sw = state["legacy"], state["structure"], state["switches"]
    method = "/".join(v.replace("Appraisal", "") for v in state["drivers"].get("Property Valuation Method", []))
    legacy_text = ", ".join(lg["forms"]) or (f"atypical: {lg['atypical']}" if lg["atypical"] else "no legacy form")
    near = (lg.get("nearest") or [None])[0]
    if not lg["forms"] and not lg["atypical"] and near and all(v.startswith("missing") for v in near["differs"].values()):
        legacy_text = f"{near['form']} once {' + '.join(near['differs'])} is set"
    approaches = [k.replace("ApproachIndicator", "") for k, v in sorted(sw.items())
                  if k.endswith("ApproachIndicator") and v.get("value") is True]
    return {
        "id": state["report_id"],
        "kind": " · ".join(x for x in (state["family"] or state["form"], legacy_text, method) if x),
        "config": f"{st['buildings']} bldg · {st['units']} unit · {st['adu_interiors']} ADU · "
                  + "+".join(a[:5] for a in approaches),
        "detail": "\n".join(summary(state)),
    }


_FILLED = r"""(() => { const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
  const out = [];
  const walk = o => { for (const x of (o.dataObjects || [])) {
      if ((x.dataObjects || []).length) { walk(x); continue; }
      const v = String(x.value ?? '').trim();
      if (v) out.push([x.key, x.instance ?? 0, v.slice(0, 40)]); } };
  walk(d); return out; })()"""


def freshness(report) -> dict:
    """Is this a new report (IMPORT_PROFILE P5)?  Fresh when it holds a value
    in no field a brand-new report does not already fill
    (`builds/<build>/new_report.json`, tools/new_report.py).  ``known`` is
    False when no fingerprint exists for this build -- then nobody can say."""
    build = _build_of(report.page)
    finger = _json(_build_dir(build), "new_report.json")
    if not finger:
        return {"fresh": None, "known": False, "extra": [], "build": build}
    known = set(finger["keys"])
    extra = [(k, i, v) for k, i, v in report.page.evaluate(_FILLED) or [] if f"{k}#{i}" not in known]
    return {"fresh": not extra, "known": True, "extra": extra, "build": build,
            "fingerprint": f"{finger['report']} {finger['taken']} ({finger['build']})"}
