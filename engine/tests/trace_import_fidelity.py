"""Import each D-1 zip and compare the imported case's report with the
scenario rendered straight from its own XML: same words, and every picture
shown.  python engine/tests/trace_import_fidelity.py"""
import difflib
import glob
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from fastapi.testclient import TestClient  # noqa: E402
from lxml import etree, html  # noqa: E402

from app.main import app  # noqa: E402
from app import api  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import templates  # noqa: E402
from uad.report import form  # noqa: E402

# the official D-1 zips ship in the folder's root
ZIPS = sorted(glob.glob(str(Path(__file__).resolve().parents[2] / "Appendix D-1 *_Appraisal.zip")))


def words(h: str) -> list[str]:
    doc = html.fromstring(h)
    for bad in doc.xpath("//script|//style"):
        bad.getparent().remove(bad)
    return " ".join(doc.text_content().split()).split(" ")


with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
    api.STORE = Store(Path(tmp) / "cases")
    api.RENDERER = None
    api.renderer = lambda: type("R", (), {"request": lambda *a, **k: None, "changed": lambda *a, **k: None})()
    with TestClient(app) as c:
        __import__("app.access").access.sign_in(c)
        for z in ZIPS:
            r = c.post("/api/import", files=[("files", (Path(z).name, open(z, "rb").read(), "application/zip"))])
            case = r.json()["case"]["case_id"]
            st = api.STORE
            media = api._media_for_render(case)
            ours = form.galley_html(form.build(st.tree(case), folder=st.folder(case), media=media))
            key = next(t.key for t in templates.catalogue() if Path(t.path).stem.lower().replace(".", "_")[:6]
                       in Path(z).stem.lower().replace("-", "").replace(" ", "_")) if False else None
            src = next(p for p in Path(tmp).glob("*") if False) if False else None
            # the same scenario straight from the official XML, with its own pictures
            tpl = next(t for t in templates.catalogue()
                       if Path(t.path).stem.split("_Appraisal")[0].lower().replace("-", "").replace(" ", "")
                       == Path(z).stem.replace("Appendix D-1 ", "").split("_Appraisal")[0].lower().replace("-", "").replace(" ", ""))
            ref_tree = etree.parse(str(tpl.path))
            ref = form.galley_html(form.build(ref_tree, folder=tpl.path.parent))
            a, b = words(ref), words(ours)
            diff = [d for d in difflib.ndiff(a, b) if d[:1] in "+-"]
            shown = len(re.findall(r"<img src='data:", ours))
            empty = ours.count("photo would display")
            ref_shown = len(re.findall(r"<img src='data:", ref))
            print(f"{tpl.key:40} words {len(a)}/{len(b)} diff={len(diff)} pictures shown {shown} (ref {ref_shown}) empty boxes {empty}")
            if diff:
                print("   ", " ".join(diff[:30])[:400])
    api.STORE.conn.close()
