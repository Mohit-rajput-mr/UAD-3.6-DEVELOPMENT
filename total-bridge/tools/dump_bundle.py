"""Keep a copy of TOTAL's form-engine code for the build that is open, to read offline.

The UAD 3.6 form is one webpack bundle served by a la mode for each web-engine
build.  Understanding how TOTAL imports, calculates, hides rows and writes its
MISMO (knowledge/errors/CATALOG.md E-037, E-038 ...) means reading that code;
reading it through a live report holds the report open and costs its renderer
memory (E-040).  This writes each module once to a local folder -- outside the
repository: it is a la mode's code, not ours, and never goes into git.

    python tools/dump_bundle.py --report "sample"          (read-only)

Writes <out>/<build>/modules/<id>.js and <out>/<build>/index.json (module id,
size, exported names, the class and function names it defines).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))

from bridge import sections                 # noqa: E402
from bridge.total import Report             # noqa: E402

DEFAULT_OUT = Path(os.environ.get("LOCALAPPDATA", str(Path.home()))) / "uad36-bridge" / "bundle"

_IDS = "Object.keys(window.__uadReq.m || {})"
_SRC = "((ids) => ids.map(id => [id, String(window.__uadReq.m[id])]))"


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--report", required=True)
    ap.add_argument("--out", default=str(DEFAULT_OUT))
    a = ap.parse_args(argv)
    with Report.attach(a.report, allow_signed=True) as r:
        sections.manager(r)                     # installs the bundle loader
        url = r.page.evaluate("location.href")
        m = re.search(r"/(\d+\.\d+\.\d+\.\d+)/", url)
        build = m.group(1) if m else "unknown"
        root = Path(a.out) / build
        mods = root / "modules"
        mods.mkdir(parents=True, exist_ok=True)
        ids = r.page.evaluate(_IDS) or []
        index = []
        for i in range(0, len(ids), 200):
            for mid, src in r.page.evaluate(f"({_SRC})({json.dumps(ids[i:i + 200])})") or []:
                (mods / f"{mid}.js").write_text(src, encoding="utf-8")
                index.append({"id": mid, "chars": len(src),
                              "exports": re.findall(r"(\w+):\(\)=>(\w+)", src[:3000])[:20],
                              "classes": sorted(set(re.findall(r"\bclass (\w+)", src)))[:40]})
    (root / "index.json").write_text(json.dumps({"build": build, "url": url, "modules": index}, indent=1),
                                     encoding="utf-8")
    print(f"{len(index)} modules, {sum(x['chars'] for x in index):,} chars -> {root}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
