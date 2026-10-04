"""Snapshot what TOTAL currently holds, before anything is imported into it."""
import sys
import time
from pathlib import Path
sys.path.insert(0, "_work")

import cdp

OUT = Path("_work/total_backup")
OUT.mkdir(parents=True, exist_ok=True)

page = cdp.open_form(0)

info = page.evaluate("""
(() => ({
  sections: window.engine.GetAllSectionKeys(),
  reportInfo: JSON.parse(JSON.stringify(window.engine.ReportInfo || {})),
  signed: (() => { try { return window.engine.IsSigned(); } catch (e) { return 'n/a'; } })(),
}))()
""")
print("report:", {k: v for k, v in (info.get("reportInfo") or {}).items()
                  if isinstance(v, (str, int, bool)) and str(v)[:60]}.__repr__()[:300])
print("signed:", info.get("signed"))
print(f"sections ({len(info.get('sections') or [])}):", (info.get("sections") or [])[:40])

print("\nserialising current report to MISMO XML ...")
xml = page.evaluate("window.engine.CreateAndReturnMismoXML()", await_promise=True)
if isinstance(xml, str) and xml.strip():
    stamp = time.strftime("%Y%m%d-%H%M%S")
    path = OUT / f"before-import-{stamp}.xml"
    path.write_text(xml, encoding="utf-8")
    print(f"  saved {len(xml):,} chars -> {path}")
else:
    print("  serialiser returned nothing:", repr(xml)[:200])

page.close()
