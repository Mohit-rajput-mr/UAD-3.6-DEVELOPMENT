"""Official D-1 sample ZIP -> engine case -> portable UAD 3.6 XML (pictures embedded).

The engine end of the end-to-end test: each official sample (its XML, its
comparables, its data and its Images/) goes in through the same import a real
appraisal takes (`POST /api/import`), and out through the same export the
Import Module consumes (`GET /api/cases/{id}/portable.xml`).  The engine's own
review of the case is saved beside it.

    python engine/tools/d1_portable.py --out <dir> "C:/3.6 uad zips/Appendix D-1 SF1_Appraisal.zip" ...

Writes <dir>/<sample>/portable.xml, engine_review.json and import.json; the
case is deleted afterwards unless --keep.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


def client():
    from fastapi.testclient import TestClient
    from app import api
    api.RENDERER = None                     # no browser: nothing here renders
    from app.main import app
    c = TestClient(app)
    c.__enter__()
    c.post("/access", data={"code": "kech"})
    return c


def one(c, zip_path: Path, out: Path, keep: bool) -> dict:
    name = zip_path.stem.replace("Appendix D-1 ", "")
    d = out / name
    d.mkdir(parents=True, exist_ok=True)
    with open(zip_path, "rb") as fh:
        r = c.post("/api/import", params={"name": f"E2E {name}"},
                   files=[("files", (zip_path.name, fh.read(), "application/zip"))])
    if r.status_code != 200:
        row = {"sample": name, "import_failed": r.status_code, "detail": r.text[:400]}
        print(json.dumps(row), flush=True)
        return row
    info = r.json()
    (d / "import.json").write_text(json.dumps(info, indent=1), encoding="utf-8")
    case = info.get("case_id") or (info.get("case") or {}).get("case_id")
    p = c.get(f"/api/cases/{case}/portable.xml")
    (d / "portable.xml").write_bytes(p.content)
    review = c.get(f"/api/cases/{case}/review").json()
    (d / "engine_review.json").write_text(json.dumps(review, indent=1), encoding="utf-8")
    row = {"sample": name, "case": case, "portable_bytes": len(p.content),
           "pictures_embedded": p.headers.get("X-Embedded-Pictures"),
           "pictures_missing": p.headers.get("X-Missing-Pictures"),
           "engine_review": review.get("counts"), "blockers": review.get("blockers")}
    if not keep:
        c.delete(f"/api/cases/{case}")
    print(json.dumps(row), flush=True)
    return row


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", required=True)
    ap.add_argument("--keep", action="store_true", help="keep the engine cases")
    ap.add_argument("zips", nargs="+")
    a = ap.parse_args(argv)
    out = Path(a.out)
    out.mkdir(parents=True, exist_ok=True)
    c = client()
    rows = [one(c, Path(z), out, a.keep) for z in a.zips]
    (out / "engine_summary.json").write_text(json.dumps(rows, indent=1), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
