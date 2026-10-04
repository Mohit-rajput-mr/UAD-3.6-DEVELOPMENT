"""Fill 2-to-4 unit and report any word the case prints and the fill does not."""
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
    return set(WORD.findall(re.sub(r"<[^>]+>"," ",html)))
key="2_to_4_unit_appraisal_v1_4"
tmp=Path(tempfile.mkdtemp()); api.STORE=Store(tmp/"cases"); api.RENDERER=None
with TestClient(app) as c:
    __import__("app.access").access.sign_in(c)
    case=c.post("/api/cases",json={"template":key,"blank":True,"name":"x"}).json()["case_id"]
    c.post(f"/api/cases/{case}/autofill", json={"source":key})
    for _ in range(600):
        st=c.get(f"/api/cases/{case}/autofill").json()
        if not st["running"]: break
        time.sleep(0.05)
    tpl=templates.get(key)
    want=words(etree.parse(str(tpl.path)), tpl.path.parent)
    tree=api.store().tree(case); folder=api.store().folder(case)
    a=words(tree, folder); b=words(tree, folder)
    print("missing:", sorted(want-a)[:8], "| same twice:", a==b,
          "| case imgs:", len(list((folder/'Images').glob('*'))), "| tpl imgs:", len(tpl.images))

