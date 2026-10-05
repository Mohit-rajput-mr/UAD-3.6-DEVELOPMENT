"""When each URAR section displays, as Appendix B-1 says it in each chapter.

B-1 opens most chapters with the sentence that decides whether the section is
on the report at all -- "The Cost Approach section displays when
CostApproachIndicator (UID: 1000.0027, FID: Not on report) = "true"." -- and
pp29-31 summarise them.  ``spec/section_rules.json`` held each chapter's
*first* sentence instead, which for several sections is a description, not
the rule ("The Manufactured Home section displays details about the
structure..."), so the editor could not tell that a site-built house has no
Manufactured Home section.  This reads, per chapter, every sentence that
states when the section displays or repeats, and keeps them with their page.

    python -m uad.spec.extract_section_display      (from engine/)
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pymupdf

from .extract_display_rules import CHAPTER, SECTIONS
from ..paths import SPEC_ROOT

OUT = Path(__file__).resolve().parents[2] / "spec" / "section_display.json"

# a sentence ends at ". " followed by a capital or a bullet -- never inside a
# UID ("1000.0027") or an FID ("20.000")
SENTENCE = re.compile(r"(?<=[a-z\)”\"])\.\s+(?=[A-Z•])")


def _b1() -> Path:
    hits = sorted(SPEC_ROOT.rglob("Appendix B-1 URAR Implementation Guide v1.4.pdf"))
    if not hits:
        raise FileNotFoundError("Appendix B-1 URAR Implementation Guide v1.4.pdf")
    return hits[0]


def chapters(pdf: Path) -> dict[int, list[tuple[int, str]]]:
    """section number -> [(page, text)] for the pages of its chapter."""
    out: dict[int, list[tuple[int, str]]] = {}
    current = 0
    doc = pymupdf.open(str(pdf))
    for pno in range(len(doc)):
        text = doc[pno].get_text()
        for line in text.splitlines()[:8]:
            m = CHAPTER.match(line.strip())
            if m and SECTIONS.get(int(m.group(1)), "").lower() == m.group(2).strip().lower():
                current = int(m.group(1))
                break
        if current:
            out.setdefault(current, []).append((pno + 1, text))
    return out


def rules_for(number: int, pages: list[tuple[int, str]]) -> dict:
    name = SECTIONS[number]
    found = {"displays": [], "repeats": []}
    for page, text in pages:
        flat = re.sub(r"\s+", " ", text)
        # from "The <Section> section" to the first full stop that is not part
        # of a number ("UID: 1000.0027") -- the page header runs into it, so
        # sentences are found, not split
        pattern = (rf"(?:The {re.escape(name)} section|The section|This section|{re.escape(name)} displays)"
                   rf"\b(?:[^.•]|\.(?=\d))*[.•]")
        for m in re.finditer(pattern, flat):
            s = m.group(0).strip()
            if re.search(r"\b(always displays|displays (?:when|only|if)|does not display)", s):
                found["displays"].append({"page": page, "text": s.rstrip(".") + "."})
            if re.search(r"\brepeats\b", s):
                found["repeats"].append({"page": page, "text": s.rstrip(".") + "."})
    return found


def main() -> None:
    pdf = _b1()
    data = {"source": f"{pdf.name}, each chapter's own display sentences", "sections": {}}
    for number, pages in sorted(chapters(pdf).items()):
        data["sections"][SECTIONS[number]] = {"number": number, **rules_for(number, pages)}
    OUT.write_text(json.dumps(data, indent=1, ensure_ascii=False), encoding="utf-8")
    for name, r in data["sections"].items():
        first = (r["displays"][:1] or [{"text": "-"}])[0]["text"]
        print(f"{r['number']:>2} {name:34s} {len(r['displays'])}d {len(r['repeats'])}r  {first[:120]}")


if __name__ == "__main__":
    main()
