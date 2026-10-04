import sys; sys.path.insert(0,'engine')
from lxml import etree
from uad import templates
from uad.report import comparables
key=sys.argv[1]
tpl=templates.get(key); tree=etree.parse(str(tpl.path))
gs=comparables.build(tree,"sales")
for g in gs:
    for r in g.rows:
        print(("##" if r.heading else "  "), r.label, "|", r.subject[:28], "|", " ; ".join((c.text or "")[:18] for c in r.cells))
