import sys, time, tempfile; sys.path.insert(0,"engine")
from pathlib import Path
from fastapi.testclient import TestClient
from lxml import etree
from app import api
from app.cases import Store
from app.main import app
from uad import compliance
M="{http://www.mismo.org/residential/2009/schemas}"
bundle=Path(sys.argv[1]); template=sys.argv[2]
tmp=Path(tempfile.mkdtemp()); api.STORE=Store(tmp/"cases"); api.RENDERER=None
with TestClient(app) as c:
    c.post("/access", data={"code":"kech"})
    case=c.post("/api/cases",json={"template":template,"blank":True,"name":"diag"}).json()["case_id"]
    r=c.post(f"/api/cases/{case}/autofill/source", files={"files":(bundle.name,bundle.read_bytes(),"application/zip")})
    source=r.json()["source"]
    c.post(f"/api/cases/{case}/autofill", json={"source":source})
    for _ in range(900):
        st=c.get(f"/api/cases/{case}/autofill").json()
        if not st["running"]: break
        time.sleep(0.1)
    got=api.store().tree(case).getroot(); src=api.store().tree(source).getroot()
    for tag in ("PROJECT","PROJECT_DETAIL","ROOM","DEFECT"):
        a=[n for n in got.iter(f"{M}{tag}")]; b=[n for n in src.iter(f"{M}{tag}")]
        print(f"{tag:16} target {len(a):3}  source {len(b):3}")
    for n in got.iter(f"{M}PROJECT_DETAIL"):
        print("  PROJECT_DETAIL:", [(etree.QName(x).localname,(x.text or '')[:16]) for x in n][:8])
    for n in list(got.iter(f"{M}ROOM"))[:3]:
        print("  ROOM:", [(etree.QName(x).localname,(x.text or '')[:14]) for x in n.iter() if x is not n][:8])
    for n in list(got.iter(f"{M}DEFECT"))[:2]:
        print("  DEFECT:", [(etree.QName(x).localname,(x.text or '')[:14]) for x in n.iter() if x is not n][:8])
    print("job dropped:", st.get("dropped"))
    from app import autofill
    tree2=api.store().tree(case)
    n=autofill._drop_leftovers(tree2.getroot(), src)
    print("drop_leftovers on the saved tree removed:", n)
    print("PROJECT now:", len(list(tree2.getroot().iter(f"{M}PROJECT"))),
          "ROOM:", len(list(tree2.getroot().iter(f"{M}ROOM"))),
          "DEFECT:", len(list(tree2.getroot().iter(f"{M}DEFECT"))))
    from uad import schema as _schema
    for pr in _schema.validate(api.store().tree(case))[:3]:
        print("SCHEMA:", pr.message[:160])
    print("PUD indicator:", [ (x.text or '') for x in got.iter(f"{M}ProjectLegalStructureType")])
    for n in got.iter(f"{M}PROJECT"):
        print("PROJECT children:", [etree.QName(x).localname for x in n])
