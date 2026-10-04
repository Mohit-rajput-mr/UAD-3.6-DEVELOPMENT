"""How much of a source case a filled case really reproduces."""
import sys, time, tempfile, collections
sys.path.insert(0,'engine')
from pathlib import Path
from fastapi.testclient import TestClient
from lxml import etree
from app import api
from app.cases import Store
from app.main import app
from uad import templates, compliance
from uad.report import form

key = sys.argv[1] if len(sys.argv)>1 else "sf1_appraisal_v1_4"
tmp=Path(tempfile.mkdtemp()); api.STORE=Store(tmp/"cases"); api.RENDERER=None
with TestClient(app) as c:
    __import__("app.access").access.sign_in(c)
    case=c.post("/api/cases",json={"template":key,"blank":True,"name":"fill"}).json()["case_id"]
    body=c.post(f"/api/cases/{case}/autofill", json={"source":key}).json()
    for _ in range(400):
        st=c.get(f"/api/cases/{case}/autofill").json()
        if not st["running"]: break
        time.sleep(0.2)
    print(f"{key}: {st['written']}/{st['total']} steps, {len(st['failed'])} failed")
    for f in st["failed"][:8]: print("    FAIL",f["kind"],f["fid"],"|",f["reason"][:80])

    tpl=templates.get(key)
    src=etree.parse(str(tpl.path))
    got=api.store().tree(case)
    def text_of(tree, folder):
        blocks=form.build(tree, folder=folder, edit=False)
        html=form.galley_html(blocks, edit=False)
        import re
        return re.sub(r"<[^>]+>"," ", html)
    import re
    a=set(w for w in re.findall(r"[A-Za-z0-9$,./%-]{3,}", text_of(src, tpl.path.parent)))
    b=set(w for w in re.findall(r"[A-Za-z0-9$,./%-]{3,}", text_of(got, api.store().folder(case))))
    missing=sorted(a-b)
    print(f"  report words: source {len(a)}, filled {len(b)}, reproduced {len(a&b)} ({100*len(a&b)//max(1,len(a))}%)")
    print("  missing sample:", missing[:25])
    fa=compliance.evaluate(src); fb=compliance.evaluate(got)
    def counts(f): return collections.Counter(x.severity for x in f if x.status==compliance.FINDING)
    print("  compliance source:",dict(counts(fa)),"filled:",dict(counts(fb)))

    print("\n  --- what compliance says is still missing ---")
    for f in fb:
        if f.status==compliance.FINDING:
            print(f"   {f.severity:8} {f.field_id or '-':10} {(getattr(f,"text","") or "")[:78]}")
