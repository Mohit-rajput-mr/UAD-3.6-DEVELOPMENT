import sys,re; sys.path.insert(0,'engine')
from lxml import etree
from uad import templates
from uad.report import form
key=sys.argv[1]
tpl=templates.get(key)
tree=etree.parse(str(tpl.path))
html=form.galley_html(form.build(tree, folder=tpl.path.parent, edit=False), edit=False)
open(sys.argv[2],"w",encoding="utf-8").write(html)
print(len(html))
