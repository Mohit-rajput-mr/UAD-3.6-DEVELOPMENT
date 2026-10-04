import sys, pymupdf
sys.path.insert(0, "engine"); sys.path.insert(0, "engine/tests")
from uad import bind, templates
from harness import report_start
names = set(bind.SECTION_NAME.values()) | {"Sales Comparison Approach", "Reconciliation", "Exhibits", "Addenda", "Appraiser Certification", "Assignment Information"}
def heads(path, skip=0):
    d = pymupdf.open(path); out = []
    for i in range(skip, d.page_count):
        hs = []; nlines = 0
        for b in d[i].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                nlines += 1
                t = "".join(s["text"] for s in l["spans"]).strip()
                bold = any("Bold" in s["font"] or s["flags"] & 16 for s in l["spans"])
                if bold and t in names and t not in hs: hs.append(t)
        out.append((hs, nlines))
    return out
key = sys.argv[1]
tpl = [t for t in templates.catalogue() if t.key == key][0]
ours = heads(f"_work/harness/{key}.pdf"); theirs = heads(tpl.pdf, report_start(tpl.pdf))
for i in range(max(len(ours), len(theirs))):
    a = ours[i] if i < len(ours) else ([], 0); b = theirs[i] if i < len(theirs) else ([], 0)
    print(f"{i+1:>2} OURS {a[1]:>3}l {', '.join(a[0])[:70]:<70} | GSE {b[1]:>3}l {', '.join(b[0])[:70]}")
