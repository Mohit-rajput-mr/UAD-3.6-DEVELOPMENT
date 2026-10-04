"""Import every D-1 delivery zip through the API and report what came in.
python engine/tests/trace_import.py"""
import glob
import sys
import tempfile
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app import api  # noqa: E402
from app.cases import Store  # noqa: E402

# the official D-1 zips ship in the folder's root
ZIPS = sorted(glob.glob(str(Path(__file__).resolve().parents[2] / "Appendix D-1*.zip")))
with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    api.STORE = Store(Path(tmp) / "cases")
    api.RENDERER = None
    with TestClient(app) as c:
        c.post("/access", data={"code": "kech"})
        for z in ZIPS:
            t = time.time()
            r = c.post("/api/import", files=[("files", (Path(z).name, open(z, "rb").read(), "application/zip"))])
            if r.status_code != 200:
                print(Path(z).name, r.status_code, r.text[:300])
                continue
            rep = r.json()["report"]
            print(f"{Path(z).name[:44]:44} {rep['property_type']:18} values={rep['values']} shown={rep['on_report']}"
                  f" comps={rep['comparables']} pics={len(rep['pictures_placed'])} missing={len(rep['pictures_missing'])}"
                  f" unref={len(rep['pictures_unreferenced'])} norm={rep['normalised_count']} invalid={rep['invalid_count']}"
                  f" dropped={rep['dropped_count']} schema={len(rep['schema_errors'])} comp={rep['compliance']}"
                  f" {time.time() - t:.1f}s")
            for m in rep["pictures_missing"][:3]:
                print("   missing:", m)
            for d in (rep["invalid"] + rep["dropped"])[:3]:
                print("   ", d)
    api.STORE.conn.close()
