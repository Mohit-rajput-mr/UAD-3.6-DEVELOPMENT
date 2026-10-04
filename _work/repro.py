"""Run the fill the way the test does, many times in one process."""
import sys,re,shutil,tempfile,time; sys.path.insert(0,'engine')
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
keys=["sf1_appraisal_v1_4","condo1_appraisal_v1_4","mh1_appraisal_v1_4","2_to_4_unit_appraisal_v1_4"]
for round_ in range(3):
    for key in keys:
        tmp=Path(tempfile.mkdtemp()); store=Store(tmp/"cases"); api.STORE=store; api.RENDERER=None
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
            got=words(api.store().tree(case), api.store().folder(case))
            miss=sorted(want-got)
            print(f"round {round_} {key:28} failed={len(st['failed'])} missing={miss[:6]}")
            if miss:
                shutil.copy(api.store().xml_path(case), f"_work/bad_{key}.xml")
                print("   images in case folder:", len(list((api.store().folder(case)/'Images').glob('*'))),
                      "media rows:", len(api.store().media(case)),
                      "| template images:", len(tpl.images))
        store.conn.close()
