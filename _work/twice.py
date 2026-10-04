import sys,re,tempfile,time; sys.path.insert(0,'engine')
from pathlib import Path
from fastapi.testclient import TestClient
from lxml import etree
from app import api
from app.cases import Store
from app.main import app
from uad import templates
from uad.report import form
WORD=re.compile(r"[A-Za-z0-9$,./%-]{3,}")
def words(tree, folder):
    html=form.galley_html(form.build(tree, folder=folder, edit=False), edit=False)
    return set(WORD.findall(re.sub(r"<[^>]+>"," ",html))), html
key="2_to_4_unit_appraisal_v1_4"
tpl=templates.get(key)
# the sample itself, rendered twice from one tree
tree=etree.parse(str(tpl.path))
a,ha=words(tree, tpl.path.parent)
b,hb=words(tree, tpl.path.parent)
print("sample, one tree twice:", a==b, "| lost:", sorted(a-b)[:8], "| gained:", sorted(b-a)[:8])
tree2=etree.parse(str(tpl.path))
cnt=len(list(tree.getroot().iter()))
cnt2=len(list(tree2.getroot().iter()))
print("elements after two renders:", cnt, "| fresh parse:", cnt2)
