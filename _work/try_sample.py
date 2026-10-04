"""Upload the sample bundle into a blank case and fill it, as the user will."""
import sys, time, tempfile
sys.path.insert(0, "engine")
from pathlib import Path
from fastapi.testclient import TestClient
from app import api
from app.cases import Store
from app.main import app
from uad import schema, compliance

bundle = Path(sys.argv[1])
template = sys.argv[2] if len(sys.argv) > 2 else "sf1_appraisal_v1_4"
tmp = Path(tempfile.mkdtemp()); api.STORE = Store(tmp / "cases"); api.RENDERER = None
with TestClient(app) as c:
    __import__("app.access").access.sign_in(c)
    case = c.post("/api/cases", json={"template": template, "blank": True,
                                      "name": "sample test"}).json()["case_id"]
    r = c.post(f"/api/cases/{case}/autofill/source",
               files={"files": (bundle.name, bundle.read_bytes(), "application/zip")})
    print("stage:", r.status_code, {k: v for k, v in r.json().items() if k != "source"}
          if r.status_code == 200 else r.text[:300])
    if r.status_code != 200:
        raise SystemExit(1)
    source = r.json()["source"]
    body = c.post(f"/api/cases/{case}/autofill", json={"source": source}).json()
    for _ in range(900):
        st = c.get(f"/api/cases/{case}/autofill").json()
        if not st["running"]:
            break
        time.sleep(0.1)
    import collections
    print("steps:", body["total"], collections.Counter(s["kind"] for s in body["steps"]))
    print("written:", st["written"], "failed:", len(st["failed"]))
    for f in st["failed"][:5]:
        print("   FAIL", f.get("kind"), f.get("fid"), f.get("reason", "")[:90])
    tree = api.store().tree(case)
    print("schema:", len(schema.validate(tree)),
          "| fatal:", len([f for f in compliance.evaluate(tree)
                           if f.status == compliance.FINDING and f.severity == "Fatal"]))
    media = c.get(f"/api/cases/{case}/media").json()["media"]
    grid = c.get(f"/api/cases/{case}/comparables?kind=sales").json()
    print("media:", len(media), "| comparables:", [g["address"].split("\n")[0] for g in grid["comparables"]])
    xml = c.get(f"/api/cases/{case}/mismo.xml").text
    for probe in ("418 Willowmere Ln", "Maple Grove", "Rowan", "Harbor Point Bank", "MG_Sketch"):
        print(f"   {probe:24} in the filled case: {probe in xml}")
    c.delete(f"/api/cases/{case}/autofill/source?source={source}")
    print("--- fatal findings ---")
    for f in compliance.evaluate(tree):
        if f.status == compliance.FINDING and f.severity == "Fatal":
            print("   ", f.message_id, f.field_id or "-", (getattr(f, "text", "") or "")[:90])
