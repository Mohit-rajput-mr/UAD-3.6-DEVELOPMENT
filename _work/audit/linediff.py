"""Whole-report text diff, ours vs the official D-1 PDF, per sample and in total.

    python _work/audit/linediff.py [-v] [-l] [-n N] [sample_key ...]

Compares the multiset of printed WORDS (page furniture dropped), so neither a
different page break nor a different line wrap counts -- only text that is
printed differently or not at all.  `-l` compares whole lines instead (noisy:
the substitute font wraps differently).  `-v` lists the differences; the
total is the number to drive down.  Ours is read from _work/harness/
(render_all.py writes it).
"""
import sys, collections, pymupdf
sys.path.insert(0, "engine"); sys.path.insert(0, "engine/tests")
from uad import templates
from harness import report_start

FURNITURE = ("Uniform Residential Appraisal Report", "Page ", "Appraisal Version", "Fannie Mae",
             "Freddie Mac", "September 2024", "File #", "File No", "Appraiser Reference ID",
             "Client Reference ID")

BY_LINE = "-l" in sys.argv


def lines(path, skip=0):
    out = collections.Counter()
    d = pymupdf.open(path)
    for i in range(skip, d.page_count):
        for b in d[i].get_text("dict")["blocks"]:
            for l in b.get("lines", []):
                t = " ".join("".join(s["text"] for s in l["spans"]).split())
                if t and not t.startswith(FURNITURE):
                    for unit in ([t] if BY_LINE else t.replace("|", " | ").split()):
                        out[unit] += 1
    return out

args = sys.argv[1:]; verbose = "-v" in args; args = [a for a in args if a not in ("-v", "-l")]
limit = 40
if "-n" in args:
    i = args.index("-n"); limit = int(args[i + 1]); del args[i:i + 2]
tot_o = tot_g = 0
for tpl in templates.catalogue():
    if args and tpl.key not in args:
        continue
    O = lines(f"_work/harness/{tpl.key}.pdf"); G = lines(tpl.pdf, report_start(tpl.pdf))
    only_o = O - G; only_g = G - O
    no, ng = sum(only_o.values()), sum(only_g.values())
    tot_o += no; tot_g += ng
    print(f"{tpl.key:42} units ours {sum(O.values()):5} / GSE {sum(G.values()):5}   only-ours {no:4}  only-GSE {ng:4}")
    if verbose:
        print("   ONLY OURS:", [f"{k} x{v}" if v > 1 else k for k, v in only_o.most_common(limit)])
        print("   ONLY GSE :", [f"{k} x{v}" if v > 1 else k for k, v in only_g.most_common(limit)])
print(f"\nTOTAL only-ours {tot_o}  only-GSE {tot_g}  sum {tot_o + tot_g}")
