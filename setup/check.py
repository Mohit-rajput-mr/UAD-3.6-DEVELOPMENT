"""Is this device ready to run a case?  Prints one line per requirement.

    python setup/check.py            # everything except the test suite
    python setup/check.py --tests    # also run the MOD's tests (about a minute)

Run it first on any new device, and again whenever something misbehaves.
Every FAIL line says what to do.  Nothing here changes anything.
"""
from __future__ import annotations

import argparse
import importlib
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BRIDGE = ROOT / "total-bridge"
sys.path.insert(0, str(BRIDGE))

rows: list[tuple[str, str, str]] = []


def ok(what, detail=""):
    rows.append(("PASS", what, detail))


def bad(what, fix):
    rows.append(("FAIL", what, fix))


def warn(what, note):
    rows.append(("WARN", what, note))


def memory_dir() -> Path:
    # Claude Code keys a project's memory by its path, every non-alphanumeric -> "-"
    slug = re.sub(r"[^A-Za-z0-9]", "-", str(ROOT))
    return Path.home() / ".claude" / "projects" / slug / "memory"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tests", action="store_true")
    args = ap.parse_args()

    # 1. Python
    v = sys.version_info
    (ok if v >= (3, 11) else bad)("Python >= 3.11", f"{v.major}.{v.minor}.{v.micro}" if v >= (3, 11) else
                                  "install Python 3.11+ (winget install -e --id Python.Python.3.12), tick 'Add to PATH'")

    # 2. packages
    missing = []
    for mod in ("lxml", "websocket", "pymupdf", "PIL", "pytest", "openpyxl", "fontTools"):
        try:
            importlib.import_module(mod)
        except Exception:
            missing.append(mod)
    if missing:
        bad("Python packages", f"missing {missing}: python -m pip install -r setup/requirements.txt")
    else:
        ok("Python packages", "lxml websocket-client pymupdf Pillow pytest openpyxl fontTools")

    # 3. specifications inside the folder
    xsd = ROOT / "specs" / "official" / "GSE_UAD_3.6.0_v1.3 (1)" / "GSE_UAD_3.6.0_v1.3" / "Combined" / "GSE_UAD_3.6.0_v1.3.xsd"
    (ok if xsd.exists() else bad)("official specs in specs/official",
                                  "present" if xsd.exists() else
                                  "specs/official missing -- copy it from the source device, or unzip the Appendix "
                                  "zips in the folder root into specs/official/<zip name>/")

    # 4. appraiser profile and documents
    prof = ROOT / "profiles" / "appraiser.json"
    if prof.exists():
        p = json.loads(prof.read_text(encoding="utf-8"))
        ok("appraiser profile", f"{p.get('name')} {p.get('designation', '')}, {p.get('level')} "
                                f"{p.get('credential_state')} -- CONFIRM with the user this is who signs on this device")
        ex = p.get("assignment_exhibits") or {}
        for k in ("licence", "eo_insurance"):
            f = ROOT / ex.get(k, "")
            if not ex.get(k) or not f.exists():
                warn(f"assignment exhibit: {k}", f"put the file at {ex.get(k) or 'profiles/documents/'} "
                                                 "(standing rule: licence + E&O in Assignment Information)")
            else:
                ok(f"assignment exhibit: {k}", str(f.relative_to(ROOT)))
    else:
        bad("appraiser profile", "profiles/appraiser.json missing")

    # 5. agent memory seeded
    md = memory_dir()
    if (md / "MEMORY.md").exists():
        ok("agent memory seeded", str(md))
    else:
        warn("agent memory not seeded", "powershell -ExecutionPolicy Bypass -File setup\\seed_memory.ps1 "
                                        "(optional: CLAUDE.md already points the agent at knowledge/)")

    # 6. WinTOTAL reachable through the MOD
    try:
        from bridge import detect
        found = detect.open_reports()
        if not found:
            warn("WinTOTAL", "TOTAL answers but no UAD 3.6 report is open -- open (or create) the case's "
                             "UAD 3.6 report in TOTAL")
        else:
            names = ", ".join(f"{r['name']}{' [ACTIVE]' if r.get('active') else ''}" for r in found)
            ok("WinTOTAL reachable (CDP 127.0.0.1:8088)", names)
            build = found[0].get("build") or ""
            kb = found[0].get("knowledge_build") or ""
            if build and build != kb:
                warn("TOTAL web-engine build", f"this TOTAL runs {build}; the extracted model is for {kb}. "
                     "Re-extract: python total-bridge/tools/form_model.py --report \"<open report>\" then "
                     "python total-bridge/tools/diff_builds.py " + kb + " " + build +
                     " and read the diff before filling (knowledge/README.md)")
            else:
                ok("TOTAL web-engine build", build or "unknown")
    except Exception as exc:
        msg = str(exc).splitlines()[0][:160]
        bad("WinTOTAL reachable", f"{msg} -- start TOTAL and open a UAD 3.6 report. The debugging port "
                                  "(127.0.0.1:8088) ships enabled in TOTAL's CEF wrapper; nothing in TOTAL is modified.")

    # 7. tests
    if args.tests:
        r = subprocess.run([sys.executable, "-m", "pytest", "-q", "tests"], cwd=BRIDGE,
                           capture_output=True, text=True)
        tail = (r.stdout.strip().splitlines() or ["?"])[-1]
        (ok if r.returncode == 0 else bad)("MOD test suite", tail)

    width = max(len(w) for _, w, _ in rows)
    for status, what, detail in rows:
        print(f"{status:4}  {what:<{width}}  {detail}")
    fails = sum(1 for s, *_ in rows if s == "FAIL")
    print(f"\n{'READY' if not fails else f'{fails} item(s) to fix'} -- see START_HERE.md")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
