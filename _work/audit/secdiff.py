import sys, pymupdf, collections
sys.path.insert(0, "engine"); sys.path.insert(0, "engine/tests")
from uad import bind, templates
from harness import report_start
NAMES = set(bind.SECTION_NAME.values()) | {"Sales Comparison Approach", "Reconciliation", "Assignment Information", "Cost Approach", "Income Approach"}
SKIP = ("Uniform Residential Appraisal Report", "Page ", "Appraisal Version", "Fannie Mae", "September 2024", "Freddie Mac")
def sections(path, skip):
    d = pymupdf.open(path); cur = "(front)"; out = collections.OrderedDict(); seen = collections.Counter()
    for i in range(skip, d.page_count):
        for b in d[i].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = " ".join("".join(s["text"] for s in l["spans"]).split())
                if not t or t.startswith(SKIP): continue
                bold = any("Bold" in s["font"] or s["flags"] & 16 for s in l["spans"])
                if bold and t in NAMES:
                    seen[t] += 1; cur = t if seen[t] == 1 else f"{t} #{seen[t]}"; out.setdefault(cur, []); continue
                out.setdefault(cur, []).append(t)
    return out
key = sys.argv[1]; only = sys.argv[2:] 
tpl = [t for t in templates.catalogue() if t.key == key][0]
O = sections(f"_work/harness/{key}.pdf", 0); G = sections(tpl.pdf, report_start(tpl.pdf))
for name in list(dict.fromkeys(list(G) + list(O))):
    if only and name not in only: continue
    o, g = O.get(name, []), G.get(name, [])
    co, cg = collections.Counter(o), collections.Counter(g)
    a = [k + (f" x{v-cg[k]}" if v-cg[k] > 1 else "") for k, v in co.items() if v > cg[k]]
    b = [k + (f" x{v-co[k]}" if v-co[k] > 1 else "") for k, v in cg.items() if v > co[k]]
    print(f"== {name}: ours {len(o)} / GSE {len(g)}  (+{len(a)} -{len(b)})")
    if only or len(a) + len(b):
        if a: print("   ONLY OURS:", a[:25])
        if b: print("   ONLY GSE :", b[:25])
