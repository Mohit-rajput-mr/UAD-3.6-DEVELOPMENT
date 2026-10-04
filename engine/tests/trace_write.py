"""Trace one field write on a fresh sample: where it lands, whether it reads
back, and what the schema says.  python engine/tests/trace_write.py 2.028 VALUE"""
import sys
from copy import deepcopy
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from lxml import etree  # noqa: E402

from uad import bind, edit, schema, templates  # noqa: E402

fid, value = sys.argv[1], sys.argv[2]
point = sys.argv[3] if len(sys.argv) > 3 else ""
tree = etree.parse(str(templates.get("sf1_appraisal_v1_4").path))
before = {e.message for e in schema.validate(tree)}
b = edit._binding_for(fid)
dp = edit.choose_data_point(b, point)
print("dp:", dp["mismo"], dp.get("requires"), dp.get("xpath", "")[-120:])
t = deepcopy(tree)
try:
    w = edit.write(t, fid, value, binding=b, data_point=point)
    print("written:", w)
except Exception as exc:
    print("write raised:", exc)
    raise SystemExit
node = bind.locate(t.getroot(), b, w.data_point)
print("read back:", None if node is None else node.text)
for n in t.getroot().iter(f"{{{bind.MISMO}}}{dp['mismo']}"):
    if (n.text or "") == w.new:
        path = []
        cur = n
        while cur is not None:
            path.append(etree.QName(cur).localname)
            cur = cur.getparent()
        print("landed at:", "/".join(reversed(path))[-200:])
        anc = n
        for _ in range(4):
            if anc.getparent() is not None:
                anc = anc.getparent()
        print(etree.tostring(anc, pretty_print=True).decode()[:1500])
new = [e.message for e in schema.validate(t) if e.message not in before]
print("new schema errors:", new[:3])
