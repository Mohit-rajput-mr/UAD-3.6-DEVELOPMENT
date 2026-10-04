"""Round-trip MISMO 3.6 files through TOTAL and measure what survives.

For each file: TOTAL's own import (replace) into a scratch report, then TOTAL
serializes its report back to MISMO, and the two documents are compared value
by value, per property.  Also recorded: the structure TOTAL built (buildings,
units, outbuildings, manufactured home, comparables per grid), the sections it
shows, and TOTAL's own E&O result (field validation, or schema, or UAD rules).

It writes into the report it is given -- use a scratch report only.

    python tools/roundtrip.py --report "sample blank" --out ../knowledge/total/roundtrip FILE.xml ...

Per file it writes <out>/<name>/: total.xml (TOTAL's serialization), diff.json,
state.json; and <out>/summary.json across all files.

The pipeline is the Import Module's own (`bridge/deliver.py`), so the samples
measure exactly what a real case gets; the comparison model is
`bridge/compare.py`'s.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from bridge import deliver, sections        # noqa: E402
from bridge.compare import compare, facts   # noqa: E402,F401  (facts: kept for callers of this tool)
from bridge.review import eando             # noqa: E402,F401
from bridge.total import Report, without_schema_location   # noqa: E402

PLACE_PHOTOS = False


_STATE = r"""(() => {
  const m = window.__uadSectionManager, d = window.engine.dataLayer.DataSets.get(window.engine.currentForm.formName);
  const secs = {};
  for (const k of ['dwelling-exterior','interior','outbuilding','manufactured'])
    secs[k] = (m.GetSections(k) || []).map(s => ({instance: s.SectionInstance, identifier: s.SectionIdentifier,
                                                 caption: s.SectionCaption, description: s.Description}));
  const grids = [...d.compManagers.entries()].map(([k, c]) => [k, c.comps]);
  const nav = [...document.querySelectorAll('#report-sections li, .report-sections li, [data-section-key]')]
      .filter(e => e.offsetParent !== null).map(e => (e.getAttribute('data-section-key') || e.textContent || '').trim()).filter(Boolean);
  const get = k => d.GetDataValue(k, 0);
  return {sections: secs, grids: Object.fromEntries(grids), nav: [...new Set(nav)],
          drivers: {APPRAISER_SPI_EXTERIOR: get('APPRAISER_SPI_EXTERIOR'), APPRAISER_SPI_INTERIOR: get('APPRAISER_SPI_INTERIOR'),
                    ATTACHMENT_TYPE: get('ATTACHMENT_TYPE'), UNIT_EXCL_ADU: get('UNIT_EXCL_ADU'),
                    PUD_YES: get('PUD_YES'), PROPRIGHTSAPPR: get('PROPRIGHTSAPPR'), GOV_AGENCY: get('GOV_AGENCY'),
                    HAS_SUPERVISOR: get('HAS_SUPERVISOR')}};
})()"""


def reset_blank(report) -> dict:
    """Make the scratch report a new, empty report again.

    A replace-import does not clear what an earlier import left (sections,
    columns, values), so every file must start from a blank report.  TOTAL
    opens reports from its own report file (`OpenReportXml`, the path WinTOTAL
    uses); a blank one is this report's own header with only the fields that
    define a new report's structure -- one building holding one unit, the order
    page -- and nothing else.  Built from the live report each time (its own
    header and IDs), never from a stored file.  (A file with *no* fields leaves
    TOTAL without a data store, so the structure fields are required.)
    """
    import uuid
    full = report.page.evaluate("window.engine.SaveReportXml(false)", await_promise=True) or ""
    if "<Fields>" not in full:
        raise RuntimeError("could not read the report file")

    def value(name):
        m = re.search(r'<Field FieldName="%s" Instance="0">.*?<EditContent>([^<]*)</EditContent>' % re.escape(name),
                      full, re.S)
        return m.group(1) if m else ""

    def field(name, val):
        return (f'<Field FieldName="{name}" Instance="0"><FieldData><DataValue>'
                f'<EditContent>{val}</EditContent></DataValue></FieldData></Field>')

    de_guid = value("DE1_SECTION_GUID") or str(uuid.uuid4())
    fields = [
        field("ORD_REPORT_DESC", value("ORD_REPORT_DESC")),
        # a new WinTOTAL report carries one order contact (Lender, the client);
        # without it the import does not keep the management-company party
        field("ORD_IS_CONTACT_CLIENT", "X"), field("ORD_CONTACT_DESC", "Lender"),
        field("DE1_SECTION_KEY", "dwelling-exterior"), field("DE1_SECTION_GUID", de_guid),
        field("DE1_HIDDEN_MOBILE_STATUS_SECTION_INSTANCE_DWELLING", "0"),
        field("UI1_SECTION_KEY", "interior"), field("UI1_SECTION_GUID", value("UI1_SECTION_GUID") or str(uuid.uuid4())),
        field("UI1_SECTION_PARENT_GUID", de_guid), field("UI1_HIDDEN_MOBILE_STATUS_SECTION_INSTANCE_UNIT", "0"),
        field("SSDE1_SECTION_KEY", value("SSDE1_SECTION_KEY") or "ssde1"),
        field("ORD_SECTION_KEY", value("ORD_SECTION_KEY") or "order"),
        field("ORD_SECTION_GUID", value("ORD_SECTION_GUID") or str(uuid.uuid4())),
    ]
    blank = re.sub(r"<Fields>.*?</Fields>", "<Fields>" + "".join(fields) + "</Fields>", full, count=1, flags=re.S)
    blank = re.sub(r"<VisiblityRules>.*?</VisiblityRules>", "<VisiblityRules></VisiblityRules>", blank,
                   count=1, flags=re.S)
    ok = report.page.evaluate(f"window.engine.OpenReportXml({json.dumps(blank)})", await_promise=True)
    time.sleep(4)
    sections.manager(report)
    tree = report.page.evaluate("(window.__uadSectionManager.GetSectionTree()||[]).map(s=>s.SectionKey+'#'+s.SectionInstance+'>'+(s.Children||[]).length)")
    if not ok or tree != ["dwelling-exterior#1>1"]:
        # put the report back as it was rather than leave it half-open
        report.page.evaluate(f"window.engine.OpenReportXml({json.dumps(full)})", await_promise=True)
        raise RuntimeError(f"blank reset failed (opened={ok}, structure={tree}); report restored")
    return {"structure": tree}


def run_one(report, path: Path, out: Path) -> dict:
    # an engine export is <sample>/portable.xml: name it by its folder
    name = path.parent.name if path.stem == "portable" else path.stem
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    reset_blank(report)                                           # CATALOG E-029
    r = deliver.run(report, path, photos=PLACE_PHOTOS)
    err = r.get("import_error", "")
    (d / "import_log.json").write_text(json.dumps(r.get("import_log", []), indent=1, ensure_ascii=False),
                                       encoding="utf-8")
    if err:
        raise RuntimeError(f"TOTAL's import refused the file: {err}")
    photos = r.get("photos", {})
    if photos:
        (d / "photos.json").write_text(json.dumps(photos, indent=1, ensure_ascii=False), encoding="utf-8")
    supervisor = dict(r["supervisor"], identifiers=r["identifiers"])
    (d / "supervisor.json").write_text(json.dumps(supervisor, indent=1), encoding="utf-8")
    (d / "rows_shown.json").write_text(json.dumps(r["rows_shown"], indent=1), encoding="utf-8")
    (d / "recalc.json").write_text(json.dumps(r["recalc"], indent=1), encoding="utf-8")
    state = json.loads(json.dumps(report.page.evaluate(_STATE)))
    (d / "total.xml").write_text(r["total_xml"], encoding="utf-8")
    diff, eo, value_diffs = r["diff"], r["eando"], r["value_diffs"]
    (d / "value_diffs.json").write_text(json.dumps(value_diffs, indent=1, ensure_ascii=False), encoding="utf-8")
    state.update({"file": str(path), "import_seconds": r["import_seconds"], "import_error": err})
    (d / "state.json").write_text(json.dumps(state, indent=1), encoding="utf-8")
    (d / "diff.json").write_text(json.dumps(diff, indent=1, ensure_ascii=False), encoding="utf-8")
    (d / "eando.json").write_text(json.dumps(eo, indent=1, ensure_ascii=False), encoding="utf-8")
    row = {"file": name, "import_error": err, "import_seconds": r["import_seconds"],
           "structure": {k: len(v) for k, v in state["sections"].items()}, "grids": state["grids"],
           "drivers": state["drivers"],
           "photos": {k: (len(v) if isinstance(v, list) else v) for k, v in photos.items()},
           "grid_rows_reshown": len(r["rows_shown"]),
           "nets_corrected": sum(1 for n in r["recalc"]["net_adjustments"] if n["before"] != n["after"]),
           "values": {k: diff[k] for k in ("source_values", "kept", "changed", "dropped", "added")},
           "value_affecting_diffs": len(value_diffs),
           "eando": {"stage": eo["stage"], "field_validation": len(eo["field_validation"]),
                     "uad_rules": Counter(x["severity"] for x in eo["uad_rules"]),
                     "panel_uad_errors": eo["panel_uad_errors"]}}
    print(json.dumps(row), flush=True)
    return row


def summarize(out: Path) -> int:
    """SUMMARY.md for a round-trip folder: per file, and the data points lost most."""
    lost = Counter()
    lines = ["# Import round trips (generated by `tools/roundtrip.py --summarize`)", "",
             "Each file imported into a freshly blanked scratch report (`reset_blank`, CATALOG E-029) with "
             "`xsi:schemaLocation` removed (E-028), serialized back by TOTAL, compared per property and path.", "",
             "| File | Structure DE/UI/OB/MH | Inspection ext/int | Kept | Dropped | Changed | Added | Value-affecting | E&O stage | Field validation |",
             "|---|---|---|---|---|---|---|---|---|---|"]
    for d in sorted(p for p in out.iterdir() if (p / "diff.json").exists() and (p / "state.json").exists()):
        diff = json.loads((d / "diff.json").read_text(encoding="utf-8"))
        state = json.loads((d / "state.json").read_text(encoding="utf-8"))
        eo = json.loads((d / "eando.json").read_text(encoding="utf-8")) if (d / "eando.json").exists() else {}
        s = {k: len(v) for k, v in state["sections"].items()}
        dr = state.get("drivers", {})
        n = diff["source_values"] or 1
        vd = (json.loads((d / "value_diffs.json").read_text(encoding="utf-8"))
              if (d / "value_diffs.json").exists() else None)
        lines.append(f"| {d.name} | {s.get('dwelling-exterior')}/{s.get('interior')}/{s.get('outbuilding')}/"
                     f"{s.get('manufactured')} | {dr.get('APPRAISER_SPI_EXTERIOR')}/{dr.get('APPRAISER_SPI_INTERIOR')} | "
                     f"{diff['kept']}/{diff['source_values']} ({100 * diff['kept'] / n:.1f}%) | {diff['dropped']} | "
                     f"{diff['changed']} | {diff['added']} | {'' if vd is None else len(vd)} | {eo.get('stage', '')} | "
                     f"{len(eo.get('field_validation', []))} |")
        for r in diff["rows"]:
            if r["kind"] in ("dropped", "changed") and "VALUATION_SOFTWARE" not in r["path"]:
                role = re.sub(r"[@#].*", "", r["scope"])
                lost[(role, r["path"].split("/")[-1], r["kind"])] += len(r["file"])
    lines += ["", "## Data points most often dropped or changed (all files)", "",
              "| Role | Data point | Kind | Values |", "|---|---|---|---|"]
    for (role, dp, kind), c in lost.most_common(60):
        lines.append(f"| {role} | {dp} | {kind} | {c} |")
    (out / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("\n".join(lines[:20]))
    return 0


def recompare(out: Path) -> int:
    """Re-run the comparison offline, from each case's saved total.xml."""
    for d in sorted(p for p in out.iterdir() if (p / "total.xml").exists()):
        state = json.loads((d / "state.json").read_text(encoding="utf-8"))
        src = without_schema_location(Path(state["file"]).read_text(encoding="utf-8")).encode("utf-8")
        diff = compare(src, (d / "total.xml").read_bytes())
        (d / "diff.json").write_text(json.dumps(diff, indent=1, ensure_ascii=False), encoding="utf-8")
        print(f"{d.name:<44} kept {diff['kept']:>5}/{diff['source_values']:<5} dropped {diff['dropped']:>4} "
              f"changed {diff['changed']:>4} added {diff['added']:>4}")
    return 0


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", required=True, help="a SCRATCH report open in TOTAL (it is overwritten)")
    ap.add_argument("--out", required=True)
    ap.add_argument("--recompare", action="store_true",
                    help="recompute diff.json for every case under --out from its saved total.xml")
    ap.add_argument("--summarize", action="store_true", help="write SUMMARY.md for --out from saved results")
    ap.add_argument("--photos", action="store_true", help="also place every picture the file carries, and read back")
    ap.add_argument("files", nargs="*")
    a = ap.parse_args(argv)
    global PLACE_PHOTOS
    PLACE_PHOTOS = a.photos
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    if a.recompare:
        return recompare(out)
    if a.summarize:
        return summarize(out)
    summary = []
    with Report.attach(a.report) as report:
        for f in a.files:
            if not report.page.alive():
                # the report's renderer died (E-040): nothing more can run until
                # the report is reopened in TOTAL -- stop, do not hang
                summary.append({"file": Path(f).stem, "failed": "report page gone (renderer crashed?) -- "
                                "reopen the report in TOTAL (restart TOTAL after a long session), then re-run"})
                print(json.dumps(summary[-1]), flush=True)
                break
            try:
                summary.append(run_one(report, Path(f), out))
            except Exception as e:                      # record and keep going
                summary.append({"file": Path(f).stem, "failed": repr(e)[:400]})
                print(json.dumps(summary[-1]), flush=True)
            # the renderer's memory after each file, with a collection first
            # (E-040: it died out of memory mid-batch; learn the limit)
            try:
                summary[-1]["heap_mb_after"] = report.page.heap_mb(collect=True)
                print(json.dumps({"file": summary[-1]["file"], "heap_mb_after": summary[-1]["heap_mb_after"]}),
                      flush=True)
            except Exception as e:
                print(json.dumps({"file": summary[-1]["file"], "heap_mb_after": f"unreadable: {e!r}"[:200]}),
                      flush=True)
    (out / "summary.json").write_text(json.dumps(summary, indent=1, default=dict), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
