"""The Certifications and Scope of Work pages print what the official reports
print (T-1039, T-115): for each of the twelve D-1 samples, every line of the
GSE's PDF from "Scope of Work" on is in our report, and we print nothing the
PDF does not -- which alternative of a certification (#10 inspection, #21
assistance, #29 prior services), whether the supervisor's block, the
FHA / USDA / VA intended users.

What the comparison leaves aside, and why:
  * page furniture (header, footer, reference IDs): drawn by flow, not blocks;
  * "this report" / "this appraisal report" in the Intended User sentence:
    B-1 v1.4 29.008 says the latter, C-1 and ten of the twelve samples the
    former (CATALOG E-098);
  * the lead-in "This appraisal report is subject to the following ...",
    which the PDF wraps across a column break.
"""
from __future__ import annotations

import html
import re
import subprocess
import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad.report import form  # noqa: E402

D1 = sorted((Path(__file__).resolve().parents[2] / "specs" / "official").glob("Appendix D-1 *_Appraisal/*_v1.*.xml"))
FURNITURE = re.compile(r"^(Page \d+ of \d+|Uniform Residential Appraisal Report|Fannie Mae \| Freddie Mac|"
                       r"September 2024|Appraisal Version #\d+|Appraiser Reference ID|Client Reference ID|"
                       r"AMC Reference ID|Agency Case File ID|.*\(continued\)|[A-Z0-9 -]*\d[A-Z0-9 -]*)$")
ASIDE = ("intended user of this", "This appraisal report is subject to the following")


def _norm(t: str) -> str:
    return re.sub(r"[^a-z0-9$]", "", t.lower())


def _ours(xml: Path) -> list[str]:
    out, on = [], False
    for b in form.build(etree.parse(str(xml)), folder=xml.parent):
        on = on or b.section.startswith("Certifications")
        if not on or not b.visible:
            continue
        if b.left or b.right:
            out += [i.label + " " + " ".join(i.values) for i in b.left + b.right if i.visible]
        elif "class='sg'" in (b.html or ""):
            out += [html.unescape(t) for t in re.findall(r">([^<>]+)<", b.html) if t.strip()]
        else:
            out.append(html.unescape(re.sub("<[^>]+>", " ", b.html or b.title)))
    return out


def _theirs(xml: Path) -> str:
    pdf = next(xml.parent.glob("*.pdf"))
    txt = subprocess.run(["pdftotext", "-layout", str(pdf), "-"], capture_output=True, text=True).stdout
    starts = [m.start() for m in re.finditer(r"\n *Scope of Work *\n", txt)]
    return txt[starts[-1]:] if starts else txt


@pytest.mark.parametrize("xml", D1, ids=[p.stem for p in D1])
def test_the_certifications_print_what_the_official_report_prints(xml):
    ours, theirs = _ours(xml), _theirs(xml)
    have, pdf = _norm(" ".join(ours)), _norm(theirs)
    missing = [p.strip() for line in theirs.splitlines() for p in re.split(r"\s{3,}", line.strip())
               if p.strip() and not FURNITURE.match(p.strip()) and not any(a in p for a in ASIDE)
               and _norm(p) not in have]
    extra = [o.strip()[:90] for o in ours if _norm(o) and _norm(o) not in pdf
             and not any(a in o for a in ASIDE) and not o.strip().startswith(("Level", "ID", "State", "Expires"))]
    assert missing == [] and extra == [], (missing[:5], extra[:5])
