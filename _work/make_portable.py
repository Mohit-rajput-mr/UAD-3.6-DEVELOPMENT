"""Import the sample bundle and export the one portable XML it becomes."""
import sys, tempfile
sys.path.insert(0, "engine")
from pathlib import Path
from fastapi.testclient import TestClient
from lxml import etree
from app import api
from app.cases import Store
from app.main import app
from uad import compliance, schema

bundle = Path(sys.argv[1]); out = Path(sys.argv[2])
tmp = Path(tempfile.mkdtemp()); api.STORE = Store(tmp / "cases"); api.RENDERER = None
with TestClient(app) as c:
    c.post("/access", data={"code": "kech"})
    r = c.post("/api/import", files=[("files", (bundle.name, bundle.read_bytes(),
                                                "application/zip"))])
    if r.status_code != 200:
        print("import failed:", r.status_code, r.text[:400]); raise SystemExit(1)
    body = r.json()
    case = (body.get("case") or {}).get("case_id")
    rep = body.get("report") or {}
    print("imported:", {k: rep.get(k) for k in ("values", "pictures", "placed", "missing")},
          "case:", case)
    p = c.get(f"/api/cases/{case}/portable.xml")
    out.write_bytes(p.content)
    tree = etree.fromstring(p.content).getroottree()
    print("portable:", out, f"{out.stat().st_size/1e6:.1f} MB")
    print("schema:", len(schema.validate(tree)),
          "| fatal:", len([f for f in compliance.evaluate(tree)
                           if f.status == compliance.FINDING and f.severity == "Fatal"]))
