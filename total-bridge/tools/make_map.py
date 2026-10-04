"""Generate data/uad36_map.json from the published Appendix A-1 specification.

A build-time tool, not part of the shipped application.  For each Report Field
ID it records three things the bridge needs:

* **where the value lives** in a MISMO document;
* **how it prints** -- A-1's format type and precision, because TOTAL's form
  expects "$650,000" where the document holds "650000";
* **its enumeration**, because the document holds ``SettledSale`` and the form
  offers "Settled Sale".  Without this the bridge types a value no pick list
  contains, and the field silently stays empty.

Run from the repository root:

    python total-bridge/tools/make_map.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "engine"))

OUT = Path(__file__).resolve().parents[1] / "data" / "uad36_map.json"


def main() -> int:
    from uad import bind                       # noqa: E402

    # page_model is keyed by section *number*; the photograph categories name
    # their section in words.  Both halves of the map have to speak the same
    # language or nothing joins -- so the number is resolved to its name here.
    names = dict(bind.SECTIONS)

    # Every field the standard has, not only the ones the older page model
    # laid out: the legal description, the reconciliation and every commentary
    # box live outside it, and a map without them reads them as empty -- which
    # is how the report came back with its commentaries blank.
    out: dict[str, dict] = {}
    laid_out = {pf.field_id for fields in bind.page_model().values() for pf in fields}
    everything = [(section, pf) for section, fields in bind.page_model().items()
                  for pf in fields]
    for fid in sorted({loc.field_id for loc in bind.locations()} - laid_out):
        binding = bind.binding_for(fid)
        if binding is None:
            continue
        everything.append((binding.section, bind.PageField(
            field_id=fid, label=binding.label, section=binding.section,
            subsection=binding.subsection, column=0, indent=0, binding=binding)))

    for section, pf in everything:
        section_name = names.get(section, str(section) if isinstance(section, int)
                                 else str(section))
        if True:
            points = []
            for dp in pf.binding.data_points:
                if not isinstance(dp, dict) or not dp.get("mismo"):
                    continue
                points.append({
                    "mismo": dp["mismo"],
                    "attribute": dp.get("attribute") or "",
                    "format_type": dp.get("format_type") or "",
                    "format_details": dp.get("format_details") or "",
                    # Where the value lives, and what identifies the block it
                    # lives in.  Without these the bridge reads the first
                    # element in the file that happens to carry the name --
                    # and the appraiser's "Name" was filled with the
                    # borrower's first name, the appraiser's company address
                    # with the subject's street.
                    "xpath": dp.get("xpath") or "",
                    "requires": {k: v for k, v in (dp.get("requires") or {}).items()
                                 if not k.startswith(("@", "__"))},
                    # Which party this belongs to.  A-1 states it in the
                    # Additional Context ("Assignment Information: Appraiser")
                    # rather than in the conditionality, so the engine's own
                    # reading of that column is what answers it.
                    "party_role": bind.party_marks(dp).get("PartyRoleType", ""),
                    "context": dp.get("context") or "",
                    # Every commentary box in the report writes the same
                    # element, ValuationCommentText, into the same kind of
                    # block.  What tells one from another is the category
                    # beside it, so without this the first comment in the file
                    # is read back into every box on the form.
                    "category": bind.commentary_category(pf.field_id) or "",
                })
            if not points:
                continue

            entry = out.setdefault(pf.field_id, {
                "label": str(pf.label),
                "section": section_name,
                "points": [],
                "enum": {},
            })
            seen = {(p["mismo"], p["attribute"]) for p in entry["points"]}
            for p in points:
                if (p["mismo"], p["attribute"]) not in seen:
                    entry["points"].append(p)
                    seen.add((p["mismo"], p["attribute"]))

            for option in (getattr(pf.binding, "enumerations", None) or []):
                if not isinstance(option, dict):
                    continue
                value, display = option.get("value"), option.get("display")
                if value and display:
                    entry["enum"].setdefault(str(value), str(display))

    # Which section each kind of photograph belongs to.  A-1 gives every
    # ImageCategoryType a Report Location, and that location names the section
    # -- so where a picture goes is published, not decided here.
    from uad.report import form                     # noqa: E402
    categories = {}
    for value, (section, caption) in form.image_categories().items():
        categories[value] = {"section": section, "caption": caption}

    payload = {"fields": out, "image_categories": categories}
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(payload, indent=1), encoding="utf-8")

    points = sum(len(v["points"]) for v in out.values())
    enumerated = sum(1 for v in out.values() if v["enum"])
    options = sum(len(v["enum"]) for v in out.values())
    print(f"{len(out)} Report Field IDs")
    print(f"  {points} data points")
    print(f"  {enumerated} enumerated fields, {options} permitted values")
    print(f"  {len(categories)} photograph categories, "
          f"{sum(1 for c in categories.values() if c['section'])} with a section")
    print(f"-> {OUT}  ({OUT.stat().st_size / 1024:.0f} KB)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
