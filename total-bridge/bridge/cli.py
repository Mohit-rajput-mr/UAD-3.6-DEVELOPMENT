"""Command line for the UAD 3.6 -> TOTAL bridge."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import cdp, hud, place as placer
from .images import photos as read_photos, summarise
from .fill import column_of, run, verify
from .mismo import Case
from .total import Report

BACKUPS = Path.home() / ".uad36-bridge" / "backups"


def _snapshot(report: Report) -> Path | None:
    """Keep what TOTAL holds before anything is changed."""
    try:
        xml = report.mismo()
    except Exception as exc:
        print(f"  could not snapshot the report first: {exc}")
        return None
    if not xml:
        return None
    BACKUPS.mkdir(parents=True, exist_ok=True)
    safe = "".join(c if c.isalnum() or c in "-_ " else "_" for c in report.name)
    path = BACKUPS / f"{safe}-{time.strftime('%Y%m%d-%H%M%S')}.xml"
    path.write_text(xml, encoding="utf-8")
    print(f"  snapshot: {path}")
    return path


# ---------------------------------------------------------------- commands
def cmd_reports(args) -> int:
    found = Report.open_reports(args.host, args.port)
    if not found:
        print("no UAD 3.6 report is open in TOTAL")
        return 1
    print(f"{len(found)} report(s) open in TOTAL:\n")
    for r in found:
        mark = "  [SIGNED - will not be written to]" if r["signed"] else ""
        print(f"  {r['name']!r}{mark}")
        print(f"      form {r.get('form')}")
    return 0


def cmd_detect(args) -> int:
    """Which report is open and active, and what kind of report it is."""
    from . import detect
    if args.xml:
        found = detect.drivers_from_xml(args.xml)
        lg = detect.legacy(found)
        print(f"{args.xml}\n  property    {found.as_text()}")
        print(f"  legacy      {', '.join(lg['forms']) or 'no legacy form'}"
              + (f"  (reading: {lg['reading']})" if lg["reading"] else "")
              + (f"; atypical: {lg['atypical']}" if lg["atypical"] else ""))
        for n in lg.get("nearest") or []:
            print(f"  nearest {n['form']}: " + "; ".join(f"{k} {v}" for k, v in n["differs"].items()))
        print(f"  source      {lg['source']}")
        return 0
    found = detect.open_reports(args.host, args.port)
    if args.report:
        found = [r for r in found if args.report.lower() in r["name"].lower()]
    if not found:
        print("no UAD 3.6 report is open in TOTAL")
        return 1
    if args.json:
        import json
        print(json.dumps([{k: v for k, v in r.items() if k != "ws"} for r in found], indent=1, default=str))
        return 0
    for r in found:
        print("\n".join(detect.summary(r)) + "\n")
    return 0


def cmd_diagnose(args) -> int:
    """One list of what is wrong, before import (a package) or after (a report)."""
    import json
    from . import diagnose
    found = []
    if args.xml and not args.report:
        found = diagnose.before(args.xml)
    else:
        package = Path(args.xml).read_bytes() if args.xml else None
        if package is not None:
            from .total import without_schema_location
            package = without_schema_location(package.decode("utf-8")).encode("utf-8")
        with Report.attach(args.report, allow_signed=True, host=args.host, port=args.port) as report:
            found = diagnose.after(report, package=package, uad=not args.no_uad)
            if args.hud:
                hud.install(report.page)
                hud.push_diagnostics(report.page, found)
                print("  the list is in the bridge's panel inside TOTAL: click an item to go to its field")
    print(diagnose.report_text(found))
    if args.json:
        Path(args.json).write_text(json.dumps(diagnose.as_json(found), indent=1), encoding="utf-8")
        print(f"\n{len(found)} item(s) -> {args.json}")
    return 1 if any(d.severity in ("fatal", "severe") for d in found) else 0


def cmd_read(args) -> int:
    with Report.attach(args.report, allow_signed=True,
                       host=args.host, port=args.port) as report:
        print(f"{report.name!r}{'  [signed]' if report.signed else ''}\n")
        report.render_all()
        values = report.values()
        filled = {k: v for k, v in values.items() if v}
        print(f"{len(filled)} of {len(values)} controls hold a value\n")
        for key, value in sorted(filled.items()):
            print(f"  {key:<38} {value[:52]!r}")
    return 0


def cmd_verify(args) -> int:
    case = Case(args.xml)
    print(f"file   : {case.describe()}")
    with Report.attach(args.report, allow_signed=True,
                       host=args.host, port=args.port) as report:
        print(f"report : {report.name!r}\n")
        result = verify(case, report)
        print(f"{result['confirmed']} of {result['checked']} values from the file "
              f"are present in what TOTAL would deliver "
              f"({result['delivered_chars']:,} chars)")
        if result["missing"]:
            print(f"\nnot found in TOTAL's delivery ({len(result['missing'])}):")
            for row in result["missing"][:40]:
                print(f"   {row['fmid']:<10} {row['fn']:<28} {row['wanted'][:34]!r}")
    return 0


def cmd_fill(args) -> int:
    case = Case(args.xml)
    described = case.describe()
    print(f"file   : {described['file']}")
    print(f"         {described['address']}")
    print(f"         {described['comparables']} comparable(s)\n")

    with Report.attach(args.report, host=args.host, port=args.port) as report:
        print(f"report : {report.name!r}")
        if not args.dry_run:
            _snapshot(report)

        def progress(n, total, fn, value, what):
            if args.quiet:
                return
            col = column_of(fn)
            where = "" if col is None else (" subject" if col == 0 else f" comp {col}")
            print(f"  [{n:>4}/{total}] {fn:<30}{where:<8} {what:<22} {value[:34]!r}")

        print("\nfilling ..." if not args.dry_run else "\nrehearsing (nothing written) ...")
        out = run(case, report, dry_run=args.dry_run, progress=progress)
        print(f"\n{out.summary()}")

        if out.refused:
            print(f"\nrefused ({len(out.refused)}):")
            for fmid, fn, why in out.refused[:20]:
                print(f"   {fmid:<10} {fn:<28} {why}")
        if out.mismatched:
            print(f"\ndid not hold the value ({len(out.mismatched)}) -- "
                  "these need the control's own interaction, not a text write:")
            for fmid, fn, wanted, got in out.mismatched[:20]:
                print(f"   {fmid:<10} {fn:<28} wanted {wanted[:22]!r} kept {got[:22]!r}")

        if not args.dry_run and not args.no_verify:
            print("\nverifying against what TOTAL would deliver ...")
            result = verify(case, report)
            print(f"  {result['confirmed']} of {result['checked']} confirmed")
            if result["missing"]:
                print(f"  {len(result['missing'])} not present:")
                for row in result["missing"][:20]:
                    print(f"     {row['fmid']:<10} {row['fn']:<28} {row['wanted'][:30]!r}")
    return 0


def cmd_deliver(args) -> int:
    """The Import Module (knowledge/ARCHITECTURE.md §5), in the order it has to
    happen: TOTAL's own import of the package, every picture into its slot, what
    TOTAL's rendering changes put back, then verification -- TOTAL's own XML
    against the package, and TOTAL's E&O read from a neutral section.  What is
    said at the end is what TOTAL says, not what this thought it did.

    ``--fill`` adds the older field-by-field fill and validation answering after
    that: a repair tool, off by default.  On a 2-4 unit report it read rental
    values from the wrong properties (_work/HANDOFF.md, 2026-09-26).
    """
    import json
    from . import deliver

    xml = Path(args.xml)
    out_dir = Path(args.out) if args.out else xml.parent / f"{xml.stem}_TOTAL_check"
    print(f"file    : {xml}")

    with Report.attach(args.report, allow_signed=False, **_where(args)) as report:
        print(f"report  : {report.name!r}")
        _snapshot(report)
        r = deliver.run(report, xml, photos=not args.no_photos,
                        progress=lambda text: print(f"\n{text}", flush=True))
        if r["import_error"]:
            print(f"   TOTAL refused the file: {r['import_error']}")
            return 1
        print(f"   imported in {r['import_seconds']}s")

        ph = r.get("photos")
        if ph:
            print(f"   pictures: {ph['placed']} placed of {ph['in_file']} in the file; "
                  f"{len(ph['slots_still_empty'])} slot(s) still empty, {len(ph['failed'])} failed, "
                  f"{len(ph['no_section']) + len(ph['no_slot'])} with nowhere to go")
        print(f"   grid rows shown again: {len(r['rows_shown'])}")
        for n in r["recalc"]["net_adjustments"]:
            if n["before"] != n["after"]:
                print(f"   comparable {n['comp']}: net adjustment {n['before']} -> {n['after']} (recomputed)")
        if r["supervisor"].get("count_before") != r["supervisor"].get("count_after"):
            print("   phantom supervisor removed")

        if args.fill:
            from . import fill as filler, fixer
            case = Case(args.xml)
            print("\nfilling every control the file has a value for ...", flush=True)
            print(f"   {filler.run(case, report).summary()}")
            print("\nanswering the validations, and the ones they open ...", flush=True)
            fixed = fixer.fix(report, case, rounds=args.rounds,
                              progress=lambda field, value, source: print(
                                  f"   {field:52} {value[:26]:26} ({source})", flush=True))
            print(f"\n{fixed.summary()}")
            print("\nverifying again ...", flush=True)
            from .total import without_schema_location
            r.update(deliver.verify(report, without_schema_location(xml.read_text(encoding="utf-8")).encode("utf-8")))

    diff, vd, eo = r["diff"], r["value_diffs"], r["eando"]
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "total.xml").write_text(r["total_xml"], encoding="utf-8")
    for name, data in (("diff.json", diff), ("value_diffs.json", vd), ("eando.json", eo),
                       ("import_log.json", r.get("import_log", [])), ("photos.json", r.get("photos", {}))):
        (out_dir / name).write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")

    n = diff["source_values"] or 1
    print(f"\nTOTAL's own XML against the package: kept {diff['kept']}/{diff['source_values']} "
          f"({100 * diff['kept'] / n:.1f}%), dropped {diff['dropped']}, changed {diff['changed']}, "
          f"added {diff['added']}")
    if vd:
        print(f"\nVALUE-AFFECTING differences ({len(vd)}) -- check before signing:")
        for row in vd:
            print(f"   {row['scope']:<40} {row['data_point']:<36} file {row['file']} -> TOTAL {row['total']}")
    else:
        print("   no difference in any adjustment, net, adjusted price, multiplier or value")
    lost = [row for row in diff["rows"] if row["kind"] in ("dropped", "changed")]
    if lost:
        print(f"\nvalues TOTAL did not keep as the file has them ({len(lost)} rows; all in {out_dir / 'diff.json'}):")
        for row in lost[:args.show]:
            print(f"   {row['kind']:<8} {row['scope'][:34]:<34} {row['data_point'][:40]:<40} {row['file'][:2]} -> {row['total'][:2]}")
        if len(lost) > args.show:
            print(f"   ... {len(lost) - args.show} more")

    print(f"\nTOTAL's E&O (from a neutral section): stage {eo['stage']}")
    for f in eo["field_validation"]:
        print(f"   {f['section'] or '':<24} {f['field'] or '':<40} {f['message']}")
    for u in eo["uad_rules"]:
        print(f"   {u['severity'] or '':<8} {u['rule'] or '':<10} {u['message']}")
    print(f"\nresults: {out_dir}")
    return 0


def _where(args) -> dict:
    """The endpoint arguments, leaving the defaults alone when unset."""
    out = {}
    if getattr(args, "host", None):
        out["host"] = args.host
    if getattr(args, "port", None):
        out["port"] = args.port
    return out


def cmd_check(args) -> int:
    """List every field validation error TOTAL itself reports."""
    from . import validate

    with Report.attach(args.report, allow_signed=True,
                       **_where(args)) as report:
        sweep = validate.sweep(
            report, on_section=lambda key, part: print(
                f"   {key:24} {len(part.problems):3} of {part.checked}", flush=True))
        print()
        print(sweep.summary())
        print()
        for problem in sweep.problems:
            print(f"   {problem}")
    return 0


def cmd_fix(args) -> int:
    """Answer what can be answered, then look again for what that opened."""
    from . import fixer

    case = Case(args.xml) if args.xml else None
    with Report.attach(args.report, allow_signed=False, **_where(args)) as report:
        out = fixer.fix(report, case,
                        rounds=args.rounds,
                        progress=lambda field, value, source: print(
                            f"   {field:52} {value[:28]:28} ({source})", flush=True))
    print()
    print(out.summary())
    if out.refused:
        print()
        print("refused by the form:")
        for field, value, why in out.refused:
            print(f"   {field:52} {value[:24]:24} {why[:40]}")
    if out.unanswered:
        print()
        print("still open -- the file does not answer these:")
        for field, message, why in out.unanswered:
            print(f"   {field:52} {message[:46]:46} {why}")
    return 0


def cmd_hud(args) -> int:
    """Put the bridge's panel into TOTAL, or take it away, or keep it there."""
    if args.watch:
        print("watching TOTAL. The panel goes on to each UAD 3.6 report as it")
        print("opens, including a report opened in its own window after you")
        print("close another. Ctrl+C to stop.")
        print(flush=True)

        def event(what, name):
            # Flushed: a watcher that buffers its output tells you nothing
            # while it is the only thing you have to watch.
            stamp = time.strftime("%H:%M:%S")
            if what == "attached":
                print(f"  {stamp}  taken over  {name!r}", flush=True)
            elif what == "gone":
                print(f"  {stamp}  closed      {name!r}", flush=True)
            elif what == "import":
                print(f"  {stamp}  import      {name}", flush=True)
            elif what == "detect-failed":
                print(f"  {stamp}  detection failed  {name}", flush=True)
            elif what == "closed":
                print(f"  {stamp}  TOTAL is not reachable; still waiting",
                      flush=True)

        try:
            hud.watch(host=args.host, port=args.port, on_event=event)
        except KeyboardInterrupt:
            print()
            print("stopped watching. Panels already installed stay put.")
        return 0

    with Report.attach(args.report, allow_signed=True,
                       host=args.host, port=args.port) as report:
        if args.remove:
            gone = hud.remove(report.page)
            print("bar removed" if gone else "no bar was installed")
            return 0
        result = hud.install(report.page)
        try:
            state = hud.push_context(report.page, report.name)
            from . import detect
            print("  " + "\n  ".join(detect.summary(state)))
        except Exception as exc:
            print(f"  (could not tell the panel what kind of report this is: {exc})")
        where = result.get("report") or report.name
        print("bar refreshed" if result.get("already") else "bar installed")
        print(f"  attached to {where!r}"
              f"{'  [SIGNED - import disabled]' if result.get('signed') else ''}")
        print()
        print("It stays until TOTAL is restarted, and reinstalls itself when")
        print("the form rebuilds. Import runs inside TOTAL, so nothing needs")
        print("to be running out here for it to work.")
    return 0


def cmd_photos(args) -> int:
    """Put the file's photographs into the report."""
    case = Case(args.xml)
    found = read_photos(args.xml)
    print(f"file   : {case.describe()['file']}")
    print(summarise(found))
    print()

    with Report.attach(args.report, host=args.host, port=args.port) as report:
        print(f"report : {report.name!r}")
        print()
        print("placing ..." if not args.dry_run
              else "rehearsing (nothing placed) ...")

        def progress(photo, key, slot, what):
            if args.quiet:
                return
            print(f"  {photo.category:<34} -> {key:<22} "
                  f"{(slot or '-'):<30} {what}")

        out = placer.place(report, case, found, dry_run=args.dry_run,
                           progress=progress)
        print()
        print(out.summary())
        for label, rows in (("no section claims them", out.no_section),
                            ("no free slot", out.no_slot),
                            ("not in the file", out.unavailable)):
            if rows:
                print()
                print(f"{label} ({len(rows)}):")
                for row in rows[:12]:
                    print(f"   {row[0]:<34} {row[1]}")
        if out.failed:
            print()
            print(f"failed ({len(out.failed)}):")
            for cat, name, why in out.failed[:12]:
                print(f"   {cat:<30} {name:<24} {why}")
    return 0


def cmd_import(args) -> int:
    xml = Path(args.xml).read_text(encoding="utf-8")
    print(f"file   : {args.xml}  ({len(xml):,} chars)")
    with Report.attach(args.report, host=args.host, port=args.port) as report:
        print(f"report : {report.name!r}")
        _snapshot(report)
        print(f"\nhanding the file to TOTAL's own deserializer ({args.mode}) ...")
        start = time.time()
        error = report.import_mismo(xml, args.mode)
        print(f"  returned after {time.time() - start:.1f}s")
        if error:
            print(f"  the engine reported: {error}")
            return 1
        print("  the engine reported no error")
    return 0


def cmd_case(args) -> int:
    """Fill a single-family URAR from case.json (or compare, with --dry-run)."""
    from . import casekit
    case = casekit.load(args.json)
    base = Path(case.get("photos_base") or Path(args.json).parent)
    report = Report.attach(args.report or case["report"])
    problems = casekit.guard(report, case)
    if problems:
        print("REFUSING:", *problems, sep="\n  ")
        return 1
    if args.dry_run:
        res = casekit.dry_run(report, case, base)
        print(f"same as the report: {res['same']}   differ: {len(res['diffs'])}   "
              f"field not present yet: {len(res['absent'])}")
        for title, key, have, want in res["diffs"]:
            print(f"   [{title}] {key}: report {have!r}  plan {want!r}")
        if res["absent"]:
            print("   not present (rows not created yet, or a key this build lacks):",
                  ", ".join(res["absent"][:40]))
        print("structural steps:", *res["structural"], sep="\n   ")
        print("adjustments:")
        for n, a in res["adjustments"].items():
            print(f"   comp {n}: net {a['net']:+,}  {a['lines']}")
        return 0
    verdict = casekit.run(report, case, base)
    print(verdict)
    return 0 if verdict.ready else 1


def cmd_certify(args) -> int:
    """Field validation, schema and UAD rules, measured honestly."""
    from . import certify
    verdict = certify.run(Report.attach(args.report), sweep=not args.no_sweep)
    print(verdict)
    return 0 if verdict.ready else 1


def cmd_audit(args) -> int:
    """The delivered XML against the case file: one value everywhere, adjusted
    prices = the kit's nets, a real reconciliation comment, sourced DOM."""
    from . import audit, casekit
    case = casekit.load(args.json)
    report = Report.attach(args.report or case["report"], allow_signed=True)
    result = audit.for_case(report.mismo(), case)
    print(result)
    return 0 if result.ok else 1


def cmd_sheets(args) -> int:
    """Contact sheets of every picture in a case folder -- VIEW them before placing."""
    from . import exhibits
    for p in exhibits.contact_sheets(args.folder, args.out):
        print(p)
    return 0


def main(argv=None) -> int:
    p = argparse.ArgumentParser(
        prog="bridge",
        description="Fill a UAD 3.6 report in TOTAL from a MISMO 3.6 file.")
    p.add_argument("--host", default=cdp.DEFAULT_HOST)
    p.add_argument("--port", type=int, default=cdp.DEFAULT_PORT)
    sub = p.add_subparsers(dest="cmd", required=True)

    s = sub.add_parser("reports", help="list the UAD 3.6 reports open in TOTAL")
    s.set_defaults(fn=cmd_reports)

    s = sub.add_parser("detect", help="which report is open and active, and what kind of report it is (reads only)")
    s.add_argument("--report")
    s.add_argument("--xml", help="detect a MISMO file (a package) instead of a live report")
    s.add_argument("--json", action="store_true")
    s.set_defaults(fn=cmd_detect)

    s = sub.add_parser("diagnose", help="one list of what is wrong: a package before import (--xml), "
                                        "or a report after (--report [--xml package])")
    s.add_argument("--report")
    s.add_argument("--xml")
    s.add_argument("--no-uad", action="store_true", help="skip TOTAL's UAD rules (they need a neutral section and ~20 s)")
    s.add_argument("--hud", action="store_true", help="also show the list in the bridge's panel, clickable")
    s.add_argument("--json")
    s.set_defaults(fn=cmd_diagnose)

    s = sub.add_parser("read", help="dump what a report currently holds")
    s.add_argument("--report")
    s.set_defaults(fn=cmd_read)

    s = sub.add_parser("verify", help="compare a file against a report, writing nothing")
    s.add_argument("--xml", required=True)
    s.add_argument("--report")
    s.set_defaults(fn=cmd_verify)

    s = sub.add_parser("fill", help="fill a report from a file")
    s.add_argument("--xml", required=True)
    s.add_argument("--report")
    s.add_argument("--dry-run", action="store_true",
                   help="say what would be written, write nothing")
    s.add_argument("--no-verify", action="store_true")
    s.add_argument("--quiet", action="store_true")
    s.set_defaults(fn=cmd_fill)

    s = sub.add_parser("deliver", help="import the package, place its pictures, reconcile, verify (the Import Module)")
    s.add_argument("--xml", required=True, help="the portable UAD 3.6 file")
    s.add_argument("--report", help="the report's name in TOTAL -- a new report: an import does not reset one")
    s.add_argument("--no-photos", action="store_true", help="leave the pictures out")
    s.add_argument("--fill", action="store_true",
                   help="also run the field-by-field fill and validation answers (repair tool; not for 2-4 unit)")
    s.add_argument("--rounds", type=int, default=4, help="with --fill: how many times to look again")
    s.add_argument("--out", help="where the results go (default: <file>_TOTAL_check beside the file)")
    s.add_argument("--show", type=int, default=40, help="how many lost values to list")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.set_defaults(fn=cmd_deliver)

    s = sub.add_parser("check", help="what TOTAL says is still wrong with the report")
    s.add_argument("--report", help="the report's name in TOTAL")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.set_defaults(fn=cmd_check)

    s = sub.add_parser("fix", help="answer TOTAL's field validation errors")
    s.add_argument("--xml", help="the UAD 3.6 file the answers come from")
    s.add_argument("--report", help="the report's name in TOTAL")
    s.add_argument("--rounds", type=int, default=4,
                   help="how many times to look again (answers open new questions)")
    s.add_argument("--host")
    s.add_argument("--port", type=int)
    s.set_defaults(fn=cmd_fix)

    s = sub.add_parser("hud", help="install the bridge's panel inside TOTAL")
    s.add_argument("--report")
    s.add_argument("--remove", action="store_true")
    s.add_argument("--watch", action="store_true",
                   help="stay running and take over each report as it opens")
    s.set_defaults(fn=cmd_hud)

    s = sub.add_parser("photos", help="place the file's photographs in the report")
    s.add_argument("--xml", required=True)
    s.add_argument("--report")
    s.add_argument("--dry-run", action="store_true")
    s.add_argument("--quiet", action="store_true")
    s.set_defaults(fn=cmd_photos)

    s = sub.add_parser("import", help="hand the whole file to TOTAL's deserializer")
    s.add_argument("--xml", required=True)
    s.add_argument("--report")
    s.add_argument("--mode", choices=("replace", "merge", "partial"),
                   default="merge")
    s.set_defaults(fn=cmd_import)

    s = sub.add_parser("case", help="fill a URAR (1 unit or 2-4 units) from case.json (knowledge/PLAYBOOK.md)")
    s.add_argument("--json", required=True, help="the case file the agent wrote")
    s.add_argument("--report", help="report name (default: the case's \"report\")")
    s.add_argument("--dry-run", action="store_true",
                   help="compare the plan with the open report; write nothing")
    s.set_defaults(fn=cmd_case)

    s = sub.add_parser("certify", help="ready to sign? field validation, schema x2, UAD rules")
    s.add_argument("--report", required=True)
    s.add_argument("--no-sweep", action="store_true", help="skip rendering every section first")
    s.set_defaults(fn=cmd_certify)

    s = sub.add_parser("audit", help="after certify: the delivered XML against the case file (reads only)")
    s.add_argument("--json", required=True)
    s.add_argument("--report")
    s.set_defaults(fn=cmd_audit)

    s = sub.add_parser("sheets", help="contact sheets of a case folder's pictures, to view before placing")
    s.add_argument("--folder", required=True)
    s.add_argument("--out", required=True)
    s.set_defaults(fn=cmd_sheets)

    args = p.parse_args(argv)
    try:
        return args.fn(args)
    except cdp.NotRunning as exc:
        print(exc)
        return 2


if __name__ == "__main__":
    sys.exit(main())
