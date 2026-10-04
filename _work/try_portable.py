"""The real test: one XML into a blank case's Fill the report."""
import sys, time, tempfile, collections
sys.path.insert(0, "engine")
from pathlib import Path
from fastapi.testclient import TestClient
from app import api
from app.cases import Store
from app.main import app
from uad import compliance, schema

src = Path(sys.argv[1]); template = sys.argv[2] if len(sys.argv) > 2 else "sf3_appraisal_v1_4"
tmp = Path(tempfile.mkdtemp()); api.STORE = Store(tmp / "cases"); api.RENDERER = None
with TestClient(app) as c:
    c.post("/access", data={"code": "kech"})
    case = c.post("/api/cases", json={"template": template, "blank": True,
                                      "name": "portable test"}).json()["case_id"]
    r = c.post(f"/api/cases/{case}/autofill/source",
               files={"files": (src.name, src.read_bytes(), "application/xml")})
    print("staged:", r.status_code, {k: v for k, v in r.json().items() if k != "source"})
    source = r.json()["source"]
    body = c.post(f"/api/cases/{case}/autofill", json={"source": source}).json()
    for _ in range(900):
        st = c.get(f"/api/cases/{case}/autofill").json()
        if not st["running"]:
            break
        time.sleep(0.1)
    print("steps:", body["total"], collections.Counter(s["kind"] for s in body["steps"]))
    print("written:", st["written"], "failed:", len(st["failed"]))
    tree = api.store().tree(case)
    print("schema:", len(schema.validate(tree)), "| fatal:",
          len([f for f in compliance.evaluate(tree)
               if f.status == compliance.FINDING and f.severity == "Fatal"]))
    media = c.get(f"/api/cases/{case}/media").json()["media"]
    folder = api.store().media_dir(case)
    here = sum(1 for m in media if (folder / m["filename"]).exists())
    print("pictures:", len(media), "on disk:", here,
          "| sketch:", any("Sketch" in m["filename"] for m in media),
          "| exhibits:", sum(1 for m in media if m["category"] not in ("subject", "comparable")))
    grid = c.get(f"/api/cases/{case}/comparables?kind=sales").json()
    print("comparables:", [g["address"].split("\n")[0] for g in grid["comparables"]])
