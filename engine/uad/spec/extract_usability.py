"""The checks Appendix B-1's Usability supplement states precisely enough to run.

"Appendix B-1 URAR Implementation Guide - Supplement - Usability and
Implementation Guidance" v1.0 asks software for twelve behaviours.  Three of
them are checks with an exact statement (T-909, T-910):

* item 6 -- discrete data fields rather than "See attached addendum", "See
  Addenda" or variations of those terms;
* item 10, example 1 -- a Recommended Action of "Subject to Completion",
  "Inspection" or "Repair" for any defect, damage or deficiency rules out a
  Market Value Condition of "As Is";
* item 10, example 2 -- an Overall Condition (FID 15.005) of "C1" must be
  supported by the data the supplement lists, each named by data point, FID
  and value.

This reads those sentences and resolves every label, display text and room
name in them against A-1 (field_index.json, enumerations.json); nothing here
is a hand-typed list.  Item 9 (prohibited / veiled language) points at the
GSE Selling Guides, which are not in the repository: it is not read here.

    python -m uad.spec.extract_usability      (from engine/)
"""
from __future__ import annotations

import json
import os
import re
from pathlib import Path

import pymupdf

SPEC = Path(__file__).resolve().parents[2] / "spec"
OUT = SPEC / "usability.json"
ROOT = Path(__file__).resolve().parents[3]
NAME = "Appendix B-1 URAR Implementation Guide - Supplement - Usability and Implementation Guidance.pdf"

Q = "[\u201c\"]([^\u201d\"]+)[\u201d\"]"          # a quoted value, curly or straight


def _pdf() -> Path:
    roots = [Path(os.environ["UAD_SPEC_ROOT"])] if os.environ.get("UAD_SPEC_ROOT") else []
    roots += [ROOT / "specs" / "official", Path(r"C:\3.6 uad zips\_UNZIPPED_ALL")]
    for r in roots:
        hits = sorted(r.rglob(NAME)) if r.exists() else []
        if hits:
            return hits[0]
    raise FileNotFoundError(NAME)


def _squash(v: str) -> str:
    return re.sub(r"[^a-z0-9]", "", v.lower())


def _index() -> dict:
    return json.loads((SPEC / "field_index.json").read_text(encoding="utf-8"))["fields"]


def _enums() -> dict[str, list[tuple[str, str]]]:
    """data point -> [(value, display text)], first-seen order, no repeats."""
    rows = json.loads((SPEC / "enumerations.json").read_text(encoding="utf-8"))
    shown = next(k for k in rows[0] if k.startswith("Output Report Display"))
    out: dict[str, list[tuple[str, str]]] = {}
    for r in rows:
        name, value = r.get("MISMO Data Point / Attribute Name"), r.get("Supported Enumerations")
        pair = (value, str(r.get(shown, "")).split("\n")[0].strip())
        if name and value and pair not in out.setdefault(name, []):
            out[name].append(pair)
    return out


def _point_of_label(label: str) -> tuple[str, list[str]]:
    """The data point a report label names, and the fields that carry it --
    the field the appraiser enters first, the Summary's redisplay last."""
    fids, points = [], set()
    for fid, entry in _index().items():
        if any(loc.get("label") == label for loc in entry.get("locations") or []):
            fids.append(fid)
            points |= {dp.get("mismo") for dp in entry.get("data_points") or []}
    if len(points) != 1:
        raise ValueError(f"label {label!r} names {sorted(points)}, not one data point")
    summary = {f for f in fids if f.startswith("1.")}
    return points.pop(), sorted(set(fids) - summary) + sorted(summary)


def _value_for(point: str, text: str) -> str:
    """A-1's value for a display text the supplement quotes -- "Subject to
    Completion" is the Recommended Action "Completion"."""
    pairs = _enums()[point]
    for value, shown in pairs:
        if _squash(text) in (_squash(value), _squash(shown)):
            return value
    for value, shown in pairs:
        if _squash(text).endswith(_squash(shown)) and shown:
            return value
    raise ValueError(f"{text!r} is not a value of {point}")


def _addendum(flat: str) -> dict:
    m = re.search(r"6\. (Check that the section commentary.*?variations of those terms\.)", flat)
    text = m.group(1)
    phrases = re.findall(Q, text)
    words = [p.split() for p in phrases]
    first = {w[0].lower() for w in words}
    last = [w[-1].lower() for w in words]
    stem = os.path.commonprefix(last)
    if len(first) != 1 or len(stem) < 5:
        raise ValueError(f"item 6 phrases changed: {phrases}")
    # "variations of those terms": the phrases differ by the words between
    # their first and last ("See [attached] addendum"); allow two more than
    # the most they put there ("Please see the attached addendum")
    gap = max(len(w) - 2 for w in words) + 2
    pattern = rf"\b{first.pop()}\b(?:\W+\w+){{0,{gap}}}?\W+{stem}\w*"
    return {"item": 6, "text": text, "phrases": phrases, "pattern": pattern}


def _as_is(flat: str) -> dict:
    m = re.search(r"Example 1 (When Recommended Action is .*?cannot be " + Q + r"\.)", flat)
    text = m.group(1)
    head, _, tail = text.partition("the Market Value Condition cannot be")
    action_point, action_fids = _point_of_label("Recommended Action")
    condition_point, condition_fids = _point_of_label("Market Value Condition")
    return {"item": 10, "example": 1, "text": text,
            "action_point": action_point, "action_fids": action_fids,
            "actions": [_value_for(action_point, a) for a in re.findall(Q, head)],
            "condition_point": condition_point, "condition_fids": condition_fids,
            "not": _value_for(condition_point, re.findall(Q, tail)[0])}


def _rating(flat: str) -> dict:
    m = re.search(r"Example 2 (.*?)(?:Appendix B-1|Data Entry Aid)", flat)
    text = m.group(1).strip()
    trig = re.search(r"when (.+?) \(FID: ([\d.]+)\) is " + Q, text)
    rating_fid, rating = trig.group(2), trig.group(3)
    point = _index()[rating_fid]["data_points"][0]["mismo"]
    display = re.search(r"must also display in (.*?), and the following", text).group(1)
    display_fids = re.findall(r"FID: ([\d.]+)", display)
    for fid in display_fids:             # one data point, so one entry shows everywhere
        if _index()[fid]["data_points"][0]["mismo"] != point:
            raise ValueError(f"{fid} does not redisplay {point}")
    room_values = list(dict.fromkeys(v for v, _s in _enums()["RoomType"]))
    requires = []
    for name, fid, rooms, value in re.findall(
            r"(\w+) \(FID: ([\d.]+)\)(?: for each ([A-Za-z ]+?))? must be " + Q, text):
        if _index()[fid]["data_points"][0]["mismo"] != name:
            raise ValueError(f"FID {fid} is not {name}")
        kinds = [v for word in re.split(r",\s*|\s+and\s+", rooms) if word
                 for v in room_values if v.endswith(word.strip())]
        requires.append({"fid": fid, "point": name, "value": value, "rooms": kinds})
    return {"item": 10, "example": 2, "text": text, "rating_fid": rating_fid,
            "rating_point": point, "rating": rating, "display_fids": display_fids,
            "requires": requires}


def main() -> None:
    pdf = _pdf()
    doc = pymupdf.open(str(pdf))
    flat = re.sub(r"\s+", " ", " ".join(p.get_text() for p in doc)).replace("\uf0b7", "")
    out = {"source": f"{pdf.name} v1.0", "addendum": _addendum(flat),
           "as_is": _as_is(flat), "ratings": [_rating(flat)]}
    OUT.write_text(json.dumps(out, indent=1, ensure_ascii=False), encoding="utf-8")
    print(f"-> {OUT}")
    print(f"  item 6   {out['addendum']['phrases']} -> /{out['addendum']['pattern']}/i")
    a = out["as_is"]
    print(f"  item 10a {a['action_point']} in {a['actions']} rules out {a['condition_point']} {a['not']}")
    for r in out["ratings"]:
        print(f"  item 10b {r['rating_point']} {r['rating']} needs "
              + "; ".join(f"{q['point']}={q['value']}" + (f" ({'/'.join(q['rooms'])})" if q["rooms"] else "")
                          for q in r["requires"]))


if __name__ == "__main__":
    main()
