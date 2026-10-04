"""Import a UAD 3.6 MISMO XML into TOTAL through the 3.6 form engine itself.

TOTAL's *menu* import handles MISMO 2.6 only -- that is what a la mode support
says and the File/Data menus bear it out.  This is a different path: the UAD 3.6
web form is its own engine (CefSharp, https://uadwebengine.alamode.com) and that
engine carries ``ImportMismoXml``, which runs its own MismoDeserializer.  The
capability ships; nothing surfaces it.

The XML is sent to the page in chunks -- a single Runtime.evaluate with a
multi-megabyte string literal is unreliable -- assembled there, then handed to
the engine.  A non-empty return value is the engine's own error message.
"""
from __future__ import annotations

import json
import sys
import time
from pathlib import Path
sys.path.insert(0, "_work")

import cdp

CHUNK = 60_000


def main(xml_path: str, mode: str = "replace") -> int:
    path = Path(xml_path)
    xml = path.read_text(encoding="utf-8")
    print(f"source : {path}")
    print(f"size   : {len(xml):,} chars")

    fn = {"replace": "ImportMismoXml",
          "merge": "ImportMismoKeepExisting",
          "partial": "ImportMismoPartial"}[mode]
    print(f"engine.{fn}()\n")

    page = cdp.open_form(0)
    try:
        page.evaluate("window.__uadXml = '';")
        parts = [xml[i:i + CHUNK] for i in range(0, len(xml), CHUNK)]
        for n, part in enumerate(parts, 1):
            page.evaluate(f"window.__uadXml += {json.dumps(part)};")
            print(f"\r  sending {n}/{len(parts)}", end="", flush=True)
        sent = page.evaluate("window.__uadXml.length")
        print(f"\r  sent {sent:,} chars" + " " * 20)
        if sent != len(xml):
            print(f"  MISMATCH: page holds {sent}, file has {len(xml)}")
            return 1

        print("\n  calling the engine (this can take a while) ...")
        start = time.time()
        result = page.evaluate(
            f"window.engine.{fn}(window.__uadXml)", await_promise=True)
        print(f"  returned after {time.time() - start:.1f}s: {result!r}")

        page.evaluate("delete window.__uadXml;")
        if result:
            print("\n  -> the engine reported a problem (above)")
            return 1
        print("\n  -> engine reported no error")
        return 0
    finally:
        page.close()


if __name__ == "__main__":
    sys.exit(main(sys.argv[1] if len(sys.argv) > 1 else
                  r"C:\18 NORTH ST BEDFORD\18_North_St_Bedford_Hills_UAD36_roundtrip.xml",
                  sys.argv[2] if len(sys.argv) > 2 else "replace"))
