"""After import: put TOTAL's report back in step with what the file says.

TOTAL can hold a value and still leave it out of what it delivers.  Its MISMO
writer includes a comparable's value only when that grid row is visible for
that instance (``EnableForComparisonApproach`` -> ``visibilityRules.isVisible``),
and rendering the sales grid hides rows on its own -- the second building's
foundation, roof and window condition, kitchen and bath quality, levels,
disaster mitigation... -- although the comparables carry values in them.  The
data is still in the report; the delivered XML silently loses it
(knowledge/errors/CATALOG.md E-037).  Measured on the 2-4 unit D-1 sample:
structure components 8 -> 4 per comparable, adjusted rows lost.

`show_rows_with_data` makes every grid row that holds a value in some
comparable visible again, through TOTAL's own visibility rules -- the same rule
a person changes when they show a row -- and it survives later renders.  Rows
with no value anywhere are left as TOTAL set them.
"""
from __future__ import annotations

_FIND_UTIL = r"""(() => {
  if (window.__uadUtil) return true;
  const req = window.__uadReq;
  if (!req) return false;
  for (const id of Object.keys(req.m || {})) {
    let m; try { m = req(id); } catch (e) { continue; }
    if (!m) continue;
    for (const k of Object.keys(m))
      if (m[k] && typeof m[k].GetSalesCompFieldRowKey === 'function') { window.__uadUtil = m[k]; return true; }
  }
  return false;
})()"""

_SHOW = r"""(() => {
  const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
  const U = window.__uadUtil;
  const shown = [], seen = new Set();
  const walk = o => { for (const x of (o.dataObjects || [])) {
    if ((x.dataObjects || []).length) { walk(x); continue; }
    const m = /^GC\d+_(.+)$/.exec(x.key);
    const v = String(x.value ?? '').trim();
    if (!m || !v || v === '-') continue;
    const row = U.GetSalesCompFieldRowKey(m[1].replace(/_ADJ$/, ''));
    const inst = x.instance ?? 0, tag = row + '|' + inst;
    if (!row || seen.has(tag)) continue;
    seen.add(tag);
    const governed = d.visibilityRules.hasRuleFor(row, inst) || d.visibilityRules.hasRuleFor(row, -1);
    if (governed && !d.visibilityRules.isVisible(row, inst).visible) {
      d.visibilityRules.Add(row, inst, true);
      shown.push(tag);
    }
  } };
  walk(d);
  return shown;
})()"""


def show_rows_with_data(report) -> list[str]:
    """Every sales-grid row holding a comparable's value made visible; returns
    the rows changed ('row-key|instance')."""
    from . import sections
    sections.manager(report)                       # installs the bundle loader
    if not report.page.evaluate(_FIND_UTIL):
        raise RuntimeError("TOTAL's grid utilities not found in this build")
    return report.page.evaluate(_SHOW) or []


_PHANTOM_SUPERVISOR = r"""(() => {
  const d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
  const named = ['SUPERVISOR_NAME', 'SUPERVISOR_FIRST_NAME', 'SUPERVISOR_LAST_NAME', 'SUPERVISOR_CRED_ID']
    .some(k => String(d.GetDataValue(k, 0) || '').trim());
  const has = String(d.GetDataValue('HAS_SUPERVISOR', 0)) === 'true';
  const before = String(d.GetDataValue('HIDDEN_SUPERVISOR_COUNT', 0) ?? '');
  if (!named && !has && before !== '0' && before !== '') d.SetDataValue('HIDDEN_SUPERVISOR_COUNT', '0', 0);
  return {supervisor_named: named, has_supervisor: has, count_before: before,
          count_after: String(d.GetDataValue('HIDDEN_SUPERVISOR_COUNT', 0))};
})()"""


def clear_phantom_supervisor(report) -> dict:
    """No supervisor in the report, yet TOTAL about to deliver one: undo it.

    Opening the Order page raises HIDDEN_SUPERVISOR_COUNT from 0 to its
    repeatable minimum of 1, and TOTAL's writer then emits an AppraiserSupervisor
    role and AppraiserSupervisorAdditionalCertificationIndicator true for a
    supervisor that does not exist (CATALOG E-034).  When no supervisor name,
    licence or HAS_SUPERVISOR is set, the count goes back to 0; measured: the
    serialization is clean again and stays clean when the Order page is reopened.
    A real supervisor is never touched.
    """
    return report.page.evaluate(_PHANTOM_SUPERVISOR) or {}


_RECALC = r"""(() => {
  const req = window.__uadReq;
  if (!window.__uadCalcEvent) {
    for (const id of Object.keys(req.m || {})) {
      let m; try { m = req(id); } catch (e) { continue; }
      if (!m) continue;
      const keys = Object.keys(m);
      const en = keys.map(k => m[k]).find(v => v && typeof v === 'object' && 'ExecuteAllCalcs' in v && 'RenderAll' in v);
      const cls = keys.map(k => m[k]).find(v => typeof v === 'function' && /changedKey|action/.test(String(v).slice(0, 400)));
      if (en && cls) { window.__uadCalcEvent = {en, cls}; break; }
    }
  }
  const ev = window.__uadCalcEvent;
  if (!ev) return 'no event class';
  window.engine.dataLayer.NotifyObservers(new ev.cls(ev.en.ExecuteAllCalcs));
  return 'recalculated';
})()"""

#: One value-changed event per sales comparable, on its net-adjustment field and
#: addressed to the sales-comparison calcs (`fieldSectionKey`) -- what TOTAL
#: raises when a person edits any adjustment of that comparable.  The field hits
#: none of the calcs' per-field cases, so the only work done is the summary
#: (net, adjusted price, per unit / bedroom / area).
_NET_ADJUSTMENTS = r"""(() => {
  const ev = window.__uadCalcEvent;
  if (!ev) return null;
  const form = window.engine.currentForm.formName;
  const cm = window.engine.dataLayer.DataSets.get(form).compManagers.get('sales');
  if (!cm) return [];
  const net = c => cm.GetCompField(c, 'NETADJ_ADJ', 0);
  const out = [];
  for (let c = 1; c <= cm.comps; c++) {
    const f = net(c);
    if (!f) continue;
    const before = String(f.value ?? '');
    window.engine.dataLayer.NotifyObservers(new ev.cls(ev.en.ValueChanged, form, f.key, 1, 0, 'sales-comp'));
    out.push({comp: c, before, after: String(net(c).value ?? '')});
  }
  return out;
})()"""


def recalculate(report, settle: float = 2.0) -> dict:
    """Have TOTAL recompute what it computed while the file was loading.

    TOTAL's net adjustment adds only the adjustment rows that are *visible* at
    the moment it sums (`IsFieldVisibleForAdjustmentCalcs`), and it sums during
    import, while the grid still hides rows that hold adjustments.  Showing the
    rows afterwards (`show_rows_with_data`) does not re-sum, and neither does
    ExecuteAllCalcs: the sales-comparison summary only runs for a changed
    comparable field.  Measured on the 2-4 unit D-1 sample: nets short by
    exactly the site-characteristic, hazard-zone and disaster-mitigation
    adjustments, adjusted prices wrong by up to $15,000 (CATALOG E-038).

    So: TOTAL's ExecuteAllCalcs for everything else, then per comparable the
    event an edit of its adjustments raises.  Run after `show_rows_with_data`,
    before anything reads a total.  Returns each comparable's net before/after.
    """
    import time
    from . import sections
    sections.manager(report)
    status = report.page.evaluate(_RECALC) or ""
    time.sleep(settle)
    nets = report.page.evaluate(_NET_ADJUSTMENTS)
    if nets is None:
        raise RuntimeError("TOTAL's data-changed event class not found in this build")
    return {"all_calcs": status, "net_adjustments": nets}


def package_identifiers(xml_text: str) -> dict:
    """The subject's building and unit identifiers, in document order."""
    from lxml import etree
    root = etree.fromstring(xml_text.encode("utf-8"), etree.XMLParser(huge_tree=True))
    subject = next((p for p in root.iter("{*}PROPERTY") if p.get("ValuationUseType") == "SubjectProperty"), None)
    out = {"buildings": [], "units": []}
    if subject is None:
        return out
    for imp in subject.iter("{*}IMPROVEMENT"):
        kind = (imp.findtext("{*}IMPROVEMENT_DETAIL/{*}ImprovementType") or "").strip()
        sid = (imp.findtext("{*}STRUCTURE/{*}STRUCTURE_DETAIL/{*}StructureIdentifier") or "").strip()
        units = [(u.findtext("{*}PROPERTY_UNIT_DETAIL/{*}UnitIdentifier") or "").strip()
                 for u in imp.iter("{*}PROPERTY_UNIT")]
        if kind in ("", "Dwelling") and (sid or units):
            out["buildings"].append(sid)
            out["units"].extend(units)
    return out


_SET_IDS = r"""((ids) => {
  const m = window.__uadSectionManager;
  const done = {buildings: [], units: []};
  const setAll = (s, v) => { s.SectionIdentifier = v; s.SectionCaption = v; s.Description = v; };
  const dws = m.GetSections('dwelling-exterior') || [];
  dws.forEach((s, i) => { const v = ids.buildings[i]; if (v) { setAll(s, v); done.buildings.push(v); } });
  const units = m.GetSections('interior') || [];
  units.forEach((s, i) => { const v = ids.units[i]; if (v) { setAll(s, v); done.units.push(v); } });
  m.SaveSections();
  return done;
})"""


def set_identifiers(report, xml_text: str) -> dict:
    """Buildings and units named as the package names them.

    TOTAL writes StructureIdentifier and UnitIdentifier from its *section*
    descriptions, not from fields; its import leaves buildings unnamed (UAD-1091,
    CATALOG E-006) and calls unit 1 "Primary Dwelling".  Set the way TOTAL's
    own importer sets them: identifier, caption and description, then saved.
    """
    import json
    from . import sections
    ids = package_identifiers(xml_text)
    if not (any(ids["buildings"]) or any(ids["units"])):
        return {"buildings": [], "units": []}
    sections.manager(report)
    return report.page.evaluate(f"({_SET_IDS})({json.dumps(ids)})") or {}
