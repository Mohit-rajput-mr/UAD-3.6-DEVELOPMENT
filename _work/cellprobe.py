import sys; sys.path.insert(0,'engine')
from pathlib import Path
from fastapi.testclient import TestClient
from lxml import html as lhtml
from app import api
from app.cases import Store
from app.main import app
from uad.report import form
import tempfile
tmp=Path(tempfile.mkdtemp())
store=Store(tmp/"cases"); api.STORE=store; api.RENDERER=None
with TestClient(app) as c:
    __import__("app.access").access.sign_in(c)
    case=c.post("/api/cases",json={"template":"sf1_appraisal_v1_4","blank":False,"name":"probe"}).json()["case_id"]
    tree=api.store().tree(case)
    blocks=form.build(tree, folder=api.store().folder(case), edit=True)
    doc=lhtml.fromstring(form.galley_html(blocks, edit=True))
    want=sys.argv[1:] or ["10.045"]
    for el in doc.iter():
        fid=el.get("data-tf")
        if fid not in want: continue
        body={"value":"","key":el.get("data-tk") or "", "data_point":el.get("data-tdp") or "",
              "sel":el.get("data-tsel") or "", "label":el.get("data-tlab") or "",
              "cat":el.get("data-tcat") or "", "new":bool(el.get("data-tnew"))}
        from uad import edit as E
        try:
            b=E._binding_for(fid); dp=E.choose_data_point(b, body["data_point"])
            ch=form.point_choices(dp); val=ch[0][0] if ch else "Cell Test"
        except Exception as e:
            val="Cell Test"
        body["value"]=val
        r=c.patch(f"/api/cases/{case}/cells/{fid}", json=body)
        print(fid, "tdp=",body["data_point"], "key=",(body["key"] or "")[-40:], "val=",val, "->", r.status_code, r.text[:140])
