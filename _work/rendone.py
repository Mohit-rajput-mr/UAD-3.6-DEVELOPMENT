import sys,re; sys.path.insert(0,'engine')
from lxml import etree
from uad.report import form
tree=etree.parse(sys.argv[1])
html=form.galley_html(form.build(tree, edit=False), edit=False)
words=sorted(set(re.findall(r"[A-Za-z0-9$,./%-]{3,}", re.sub(r"<[^>]+>"," ",html))))
open(sys.argv[2],"w",encoding="utf-8").write("\n".join(words))
print(len(words))
