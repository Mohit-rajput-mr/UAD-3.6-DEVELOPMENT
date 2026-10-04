"""The Import Module: a portable UAD 3.6 package into an open TOTAL report.

knowledge/ARCHITECTURE.md §5, in the order it has to happen:

  b  TOTAL's own import (full), of the file as TOTAL's importer needs it --
     no xsi:schemaLocation, TOTAL's xlink label conventions (`Report.import_mismo`
     -> `prepare_for_total`; CATALOG E-028, E-032, E-036)
  e  every picture into the slot TOTAL's import made for it, then the rest by
     category (TOTAL makes the slots and loads none: E-019, E-033)
  c  structure TOTAL's rendering and importer get wrong: grid rows hidden
     although they hold values (E-037), totals summed while they were hidden
     (E-038), a supervisor nobody named (E-034), unnamed buildings and units
     (E-006)
  f  verification: TOTAL serializes the report and it is compared with the
     package value by value (`compare`), value-affecting differences listed
     on their own; then TOTAL's E&O, read from a neutral section (E-035)

The same function is what `tools/roundtrip.py` runs on the twelve D-1 samples,
so what the samples measure is what a real case gets.  Value reconciliation by
UID (§5d) is not built yet: what the comparison reports as dropped or changed
is listed, not repaired.

A replace-import does not reset a report (E-029): deliver into a new report.
"""
from __future__ import annotations

import time
from pathlib import Path

from . import compare as cmp, place as placer, reconcile, review, sections


def _say(progress, text: str) -> None:
    if progress:
        progress(text)


# The importer reports what it could not place only through the console.  Its
# messages are captured for the import alone -- this page session only, nothing
# persistent -- and the console is restored right after.  TOTAL's importer also
# has its own narration (`MISMODeserializerHelpers.SetLogging`: every
# categorisation, every field populated, every image it could not map); it is
# switched on for the import and back to what it was after.
_CAPTURE_ON = r"""(() => {
  if (window.__rtOrig) return;
  const req = window.__uadReq;
  if (req && !window.__uadDeser) {
    for (const id of Object.keys(req.m || {})) {
      let m; try { m = req(id); } catch (e) { continue; }
      if (!m) continue;
      for (const k of Object.keys(m)) {
        const v = m[k];
        if (typeof v === 'function' && typeof v.SetLogging === 'function' && typeof v.Log === 'function'
            && typeof v.Group === 'function') { window.__uadDeser = v; break; }
      }
      if (window.__uadDeser) break;
    }
  }
  if (window.__uadDeser) { window.__rtDeserWas = !!window.__uadDeser.ENABLE_LOGGING; window.__uadDeser.SetLogging(true); }
  window.__rtLogs = [];
  window.__rtOrig = {log: console.log, warn: console.warn, error: console.error};
  for (const lvl of ['log', 'warn', 'error']) {
    const orig = window.__rtOrig[lvl];
    console[lvl] = (...a) => {
      try { if (window.__rtLogs.length < 20000) window.__rtLogs.push([lvl, a.map(x => {
        if (x instanceof Error) return x.message + ' @ ' + (x.stack || '').split('\n').slice(0, 3).join(' | ');
        if (typeof x === 'string') return x.slice(0, 600);
        try { return JSON.stringify(x).slice(0, 300); } catch (e) { return String(x).slice(0, 300); } }).join(' ')]); } catch (e) {}
      return orig.apply(console, a);
    };
  }
})()"""

_CAPTURE_OFF = r"""(() => {
  const logs = window.__rtLogs || [];
  if (window.__uadDeser) window.__uadDeser.SetLogging(!!window.__rtDeserWas);
  if (window.__rtOrig) { Object.assign(console, window.__rtOrig); delete window.__rtOrig; }
  delete window.__rtLogs;
  return logs;
})()"""


def pictures(report, xml_path: Path) -> dict:
    """Every picture the file carries, into its TOTAL slot, then read back
    which slots hold one."""
    from .images import photos as read_photos
    from .mismo import Case
    case = Case(str(xml_path))
    found = read_photos(xml_path)
    t0 = time.time()
    # first every slot TOTAL's import already made for a named file (E-033),
    # then the rest by category
    named = {(e["fn"], e["instance"]): placer._file_key(e["file"]) for e in placer.expected_files(report)}
    by_file, rest = placer.place_by_file(report, found)
    done = placer.place(report, case, rest, known=found)
    after = placer.expected_files(report)
    # a slot now holding another picture than the one TOTAL's import named for
    # it: either the file's own more specific picture (the subject photo over
    # TOTAL's front-photo stand-in) or a misplacement (E-039) -- listed, and
    # the round-trip comparison says which
    differs = [f"{e['fn']}#{e['instance']}: import named {named[(e['fn'], e['instance'])]}, holds "
               f"{placer._file_key(e['file'])}" for e in after
               if (e["fn"], e["instance"]) in named and e["loaded"]
               and placer._file_key(e["file"]) != named[(e["fn"], e["instance"])]]
    return {"in_file": len(found), "placed_by_file": by_file.placed, "placed_by_category": done.placed,
            "placed": by_file.placed + done.placed, "seconds": round(time.time() - t0, 1),
            "slots_naming_a_file": len(after), "slots_still_empty": [e["fn"] + "#" + e["instance"] + " " + e["file"]
                                                                      for e in after if not e["loaded"]],
            "differs_from_import": differs,
            "total_owned": [list(x) for x in done.total_owned],
            "failed": [list(x) for x in by_file.failed + done.failed],
            "no_slot": [list(x) for x in by_file.no_slot + done.no_slot],
            "no_section": [list(x) for x in done.no_section],
            "unavailable": [list(x) for x in by_file.unavailable + done.unavailable]}


def reconcile_structure(report, xml_text: str) -> dict:
    """What TOTAL's rendering and importer leave wrong, put back through
    TOTAL's own rules and events."""
    # every section has been rendered by now (pictures) or will be by the
    # appraiser: rows TOTAL hid although they hold values are shown again, or
    # the delivered XML loses them (E-037) ...
    report.goto("sxs-section-key", settle=2.5)
    rows_shown = reconcile.show_rows_with_data(report)
    # ... and the totals TOTAL summed while they were hidden are summed again (E-038)
    recalc = reconcile.recalculate(report)
    supervisor = reconcile.clear_phantom_supervisor(report)                  # E-034
    identifiers = reconcile.set_identifiers(report, xml_text)                # E-006
    return {"rows_shown": rows_shown, "recalc": recalc, "supervisor": supervisor, "identifiers": identifiers}


def verify(report, package: bytes) -> dict:
    """TOTAL's serialization against the package, and TOTAL's E&O."""
    tot = report.page.evaluate("window.engine.CreateAndReturnMismoXML()", await_promise=True) or ""
    diff = cmp.compare(package, tot.encode("utf-8"))
    return {"total_xml": tot, "diff": diff, "value_diffs": cmp.value_diffs(diff), "eando": review.eando(report)}


def run(report, xml_path, *, photos: bool = True, mode: str = "replace", progress=None) -> dict:
    """Import the package, place its pictures, reconcile, verify.  Returns
    every step's result; nothing is repaired that is not a CATALOG mechanism."""
    from .total import without_schema_location
    xml_path = Path(xml_path)
    text = xml_path.read_text(encoding="utf-8")
    out: dict = {"file": str(xml_path)}

    _say(progress, "importing with TOTAL's own importer ...")
    sections.manager(report)                    # the bundle loader, for the importer's own log switch
    report.page.evaluate(_CAPTURE_ON)
    t0 = time.time()
    try:
        out["import_error"] = report.import_mismo(text, mode) or ""
        out["import_seconds"] = round(time.time() - t0, 1)
        time.sleep(3)
    finally:
        out["import_log"] = report.page.evaluate(_CAPTURE_OFF) or []
    sections.manager(report)
    if out["import_error"]:
        return out

    if photos:
        _say(progress, "placing the pictures ...")
        out["photos"] = pictures(report, xml_path)

    _say(progress, "reconciling what TOTAL's rendering changed ...")
    out.update(reconcile_structure(report, text))

    _say(progress, "verifying: TOTAL's own XML against the package, then TOTAL's E&O ...")
    # compared with the file TOTAL was given, less the attribute it cannot read
    # (E-028); the xlink relabel is invisible to the comparison
    out.update(verify(report, without_schema_location(text).encode("utf-8")))
    return out
