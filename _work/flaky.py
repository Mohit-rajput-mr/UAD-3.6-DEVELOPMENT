import sys,tempfile,time,re,hashlib; sys.path.insert(0,'engine')
from pathlib import Path
from fastapi.testclient import TestClient
from lxml import etree
from app import api
from app.cases import Store
from app.main import app
from uad import templates
from uad.report import form
key=sys.argv[1]
WORD=re.compile(r"[A-Za-z0-9$,./%-]{3,}")
def words(tree, folder):
    html=form.galley_html(form.build(tree, folder=folder, edit=False), edit=False)
    return set(WORD.findall(re.sub(r"<[^>]+>"," ",html)))
tpl=templates.get(key)
want=words(etree.parse(str(tpl.path)), tpl.path.parent)
for run in range(4):
    tmp=Path(tempfile.mkdtemp()); api.STORE=Store(tmp/"cases"); api.RENDERER=None
    with TestClient(app) as c:
        c.post("/access", data={"code":"kech"})
        case=c.post("/api/cases",json={"template":key,"blank":True,"name":"x"}).json()["case_id"]
        c.post(f"/api/cases/{case}/autofill", json={"source":key})
        for _ in range(600):
            st=c.get(f"/api/cases/{case}/autofill").json()
            if not st["running"]: break
            time.sleep(0.05)
        tree=api.store().tree(case)
        got=words(tree, api.store().folder(case))
        xml=etree.tostring(tree)
        print(f"run {run}: failed={len(st['failed'])} missing={sorted(want-got)[:6]} xml={hashlib.sha1(xml).hexdigest()[:10]} len={len(xml)}")
    api.STORE.conn.close()
