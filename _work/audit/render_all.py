"""Render the official samples to _work/harness/<key>.pdf (what linediff.py / secdiff.py read).

    python _work/audit/render_all.py [sample_key ...]     # default: all 12, ~1 min

Faster than the full harness (no schema/compliance checks).  Restore the
tracked PDFs afterwards:  git checkout -- _work/harness/
"""
import sys, time
sys.path.insert(0, "engine"); sys.path.insert(0, "engine/tests")
from lxml import etree
from uad import templates
from uad.report import flow
import harness

only = set(sys.argv[1:])
for tpl in templates.catalogue():
    if only and tpl.key not in only:
        continue
    t0 = time.time()
    tree = etree.parse(str(tpl.path))
    html = flow.build(tree, folder=tpl.path.parent, screen=False, diagnostics={})
    flow.to_pdf(html, harness.OUT / f"{tpl.key}.pdf")
    print(f"{tpl.key:42} {time.time() - t0:4.0f}s", flush=True)
