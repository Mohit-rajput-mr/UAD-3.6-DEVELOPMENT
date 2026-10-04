import sys,tempfile,time; sys.path.insert(0,'engine')
from pathlib import Path
from fastapi.testclient import TestClient
from app import api
from app.cases import Store
from app.main import app
key=sys.argv[1]
tmp=Path(tempfile.mkdtemp()); api.STORE=Store(tmp/"cases"); api.RENDERER=None
with TestClient(app) as c:
    __import__("app.access").access.sign_in(c)
    case=c.post("/api/cases",json={"template":key,"blank":True,"name":"x"}).json()["case_id"]
    c.post(f"/api/cases/{case}/autofill", json={"source":key})
    for _ in range(600):
        st=c.get(f"/api/cases/{case}/autofill").json()
        if not st["running"]: break
        time.sleep(0.05)
    import shutil
    shutil.copy(api.store().xml_path(case), sys.argv[2])
    print("saved", sys.argv[2], "failed", len(st["failed"]))
