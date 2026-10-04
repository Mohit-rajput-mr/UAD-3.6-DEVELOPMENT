"""No content may land below the body rule -- on any sample, at any image load.

This is the check behind T-100.  It builds each D-1 scenario through the real
engine and reads the rendered page back, because the only trustworthy statement
about where content sits is the one the browser makes after laying it out.
"""
import sys
sys.path.insert(0, "engine")
from pathlib import Path

from lxml import etree

from uad.report import flow, form

SAMPLES = Path(__import__("os").environ.get("UAD36_SPECS")
               or Path(__file__).resolve().parents[2] / "specs" / "official")


def cases():
    seen = {}
    for x in SAMPLES.glob("Appendix D-1 *_Appraisal/*_v1.4.xml"):
        seen.setdefault(x.stem.lower(), x)
    return [seen[k] for k in sorted(seen)]


def sections_of(xml):
    out = []
    for b in form.build(etree.parse(str(xml)), folder=xml.parent, media=[]):
        s = getattr(b, "section", "")
        if s and s not in out:
            out.append(s)
    return out


def main(image_counts=(0, 8)):
    ok = True
    for xml in cases():
        pics = [p for p in xml.parent.rglob("*")
                if p.suffix.lower() in (".jpg", ".jpeg", ".png")]
        secs = sections_of(xml)
        for count in image_counts:
            media = [{"section_name": secs[i % len(secs)],
                      "path": str(pics[i % len(pics)]), "caption": f"Photo {i + 1}"}
                     for i in range(count)] if pics else []
            if count and not pics:
                continue
            d = {}
            flow.build(etree.parse(str(xml)), folder=xml.parent, media=media,
                       diagnostics=d)
            bad = bool(d["overflow"])
            ok &= not bad
            print(f"{'FAIL' if bad else 'ok  '}  {xml.stem:<28} {count:>2} images  "
                  f"{d['pages']:>2} pages  {d['attempts']} pass(es)  "
                  f"drift {d['drift']:+.2f}pt"
                  + (f"  OVERFLOW {d['overflow']}" if bad else ""))
    print("\nT-100:", "PASS -- no page overflows" if ok else "FAIL")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
