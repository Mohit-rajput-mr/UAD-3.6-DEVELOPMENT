"""Field by field: what the documentation says, and what the editor really does.

For one section of the report, every Report Field ID in page order, with

* **A-1**  each data point: MISMO name, format and length, conditionality
  (R / CR / O and its condition), enumerations, XML container;
* **B-1**  the display rule;
* **H-1**  the compliance rules on its data points (severity and message);
* **shape** the kind of field it is, which decides the control it needs --
  a list with an "Other" that requires a description, a name made of parts or
  a legal entity's full name, an indicator with detail, a measure with a unit,
  a repeating row;
* **live** a value sent through the editor's own route for every control the
  report draws for it (the same request the page makes), and what came back:
  saved, read back, shown in print, and whether the MISMO document still
  validates.

Run it::

    python engine/uad/dossier.py 2            # section 2, printed
    python engine/uad/dossier.py 2 --json     # and _work/dossier/02.json
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from collections import defaultdict
from dataclasses import asdict, dataclass, field
from functools import lru_cache
from pathlib import Path

from lxml import html as lhtml

ENGINE = Path(__file__).resolve().parents[1]
if str(ENGINE) not in sys.path:
    sys.path.insert(0, str(ENGINE))

from uad import bind, edit, schema  # noqa: E402
from uad.report import form  # noqa: E402

SPEC = ENGINE / "spec"
WORK = ENGINE.parent / "_work" / "dossier"


@dataclass
class Point:
    uid: str
    mismo: str
    format: str
    length: str
    cond: str
    cond_details: str
    context: str
    container: str
    enums: list[str]
    requires: dict


@dataclass
class Live:
    control: str               # text / pick / check / cell / grid / derived
    key: str = ""
    sent: str = ""
    status: int = 0
    shown: str = ""
    printed: bool = False
    detail: str = ""


@dataclass
class Dossier:
    fid: str
    label: str
    subsection: str
    points: list[Point]
    display: list[str]
    rules: list[str]
    shapes: list[str]
    live: list[Live] = field(default_factory=list)
    verdict: str = ""


# ------------------------------------------------------------------ the spec
@lru_cache(maxsize=1)
def _rules_by_uid() -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = defaultdict(list)
    for r in json.loads((SPEC / "compliance_rules.json").read_text(encoding="utf-8")):
        out[r.get("Unique ID", "")].append(r)
    return out


def shapes(points: list[Point]) -> list[str]:
    """The kinds of field these data points make, from their names and A-1."""
    names = [p.mismo for p in points]
    out = []
    if any("Other" in e for p in points for e in p.enums) and any(n.endswith("OtherDescription") for n in names):
        out.append("enum+other-description")
    contexts = {p.context for p in points if p.context}
    if len(contexts) > 1:
        out.append("alternatives:" + " / ".join(sorted(contexts)))
    parts = [p for p in points if p.format != "Enumerated" and not p.mismo.endswith("OtherDescription")]
    if len({p.mismo for p in parts}) > 1 and len({p.container for p in parts}) <= 2:
        out.append("composite:" + "+".join(dict.fromkeys(p.mismo for p in parts)))
    if any(p.format == "Boolean" for p in points) and len(points) > 1:
        out.append("indicator+detail")
    if any(n.endswith(("Measure", "Count")) for n in names) and any(p.enums for p in points):
        out.append("measure+unit")
    if any(p.format == "Enumerated" and p.enums and len(p.enums) > 1 for p in points) and len(points) == 1:
        out.append("list")
    return out


def dossiers(section: int) -> list[Dossier]:
    out = []
    for pf in bind.page_model().get(section, []):
        pts = []
        rules = []
        for dp in pf.binding.data_points:
            if not dp.get("mismo"):
                continue
            pts.append(Point(dp.get("unique_id", ""), dp["mismo"] + (f"@{dp['attribute']}" if dp.get("attribute") else ""),
                             dp.get("format_type") or "", dp.get("format_details") or "",
                             dp.get("conditionality") or "", dp.get("conditionality_details") or "",
                             dp.get("context") or "", dp.get("container") or "",
                             [e.get("value", "") for e in dp.get("enumerations") or []],
                             dp.get("requires") or {}))
            for r in _rules_by_uid().get(dp.get("unique_id", ""), []):
                rules.append(f"{r.get('Message ID')} [{r.get('Severity')}] {r.get('Message Text')}"
                             f"  <= {r.get('Rule Logic')}")
        display = [s.get("rule", "") for s in pf.binding.display_rules]
        out.append(Dossier(pf.field_id, pf.label, pf.subsection, pts, display,
                           list(dict.fromkeys(rules)), shapes(pts)))
    return out


# ------------------------------------------------------------------ live test
def _value_for(dp: dict, current: str = "") -> str:
    kind = (dp.get("format_type") or "String").strip()
    options = [e["value"] for e in dp.get("enumerations") or [] if e.get("value")]
    if options:
        pick = [o for o in options if o != "Other" and o != current] or options
        return pick[0]
    if kind == "Boolean":
        return "false" if current == "true" else "true"
    if kind == "Amount":
        return "123457"
    if kind == "Numeric":
        return "7"
    if kind == "Date":
        return "2026-03-04"
    if kind == "Datetime":
        return "2026-03-04T10:00:00Z"
    if kind == "Percent":
        return "7"
    return "Zq" + re.sub(r"\D", "", dp.get("unique_id", "") or "1")[-6:]


def live(section: int, template: str = "sf1_appraisal_v1_4") -> dict[str, list[Live]]:
    """Every control the editor draws for the section, exercised through the API."""
    from fastapi.testclient import TestClient
    from app import api
    from app.cases import Store

    results: dict[str, list[Live]] = defaultdict(list)
    from app.main import app              # before STORE: main sets its own
    with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as tmp:
        store = Store(Path(tmp) / "cases")
        api.STORE = store
        api.RENDERER = None
        with TestClient(app) as client:
            client.post("/access", data={"code": "kech"})
            case = client.post("/api/cases", json={"template": template, "blank": False,
                                                    "name": "dossier"}).json()["case_id"]
            tree = store.tree(case)
            doc = lhtml.fromstring(form.galley_html(form.build(tree, folder=store.folder(case), edit=True), edit=True))
            mine = lambda fid: fid and fid.split(".")[0] == str(section)     # noqa: E731
            seen = set()
            grid_rows = None
            for el in doc.iter():
                if not isinstance(el.tag, str):
                    continue
                fid = el.get("data-fid") or el.get("data-tf") or el.get("data-gf") or el.get("data-derived") or ""
                if not mine(fid):
                    continue
                if el.get("data-derived"):
                    kind = "derived"
                elif el.get("data-tf") is not None:
                    kind = "cell"
                elif el.get("data-gf") is not None:
                    kind = "grid"
                elif "bx" in (el.get("class") or "").split():
                    kind = "check"
                elif "pick" in (el.get("class") or "").split():
                    kind = "pick"
                else:
                    kind = "text"
                sig = (fid, kind, el.get("data-tk"), el.get("data-tsel"), el.get("data-tnew"), el.get("data-gc"))
                if sig in seen or (kind == "check" and el.get("data-pick") != "true"):
                    continue
                seen.add(sig)
                rec = Live(kind, key=(el.get("data-tk") or el.get("data-gc") or "")[-50:])
                if kind == "derived":
                    results[fid].append(rec)
                    continue
                try:
                    binding = edit._binding_for(fid)
                    dp = edit.choose_data_point(binding, el.get("data-tdp") or "")
                except KeyError as exc:
                    rec.detail = f"no binding: {exc}"
                    results[fid].append(rec)
                    continue
                current = (el.text_content() or "").strip()
                if kind == "check":
                    rec.sent = "true" if current != "" else "false"
                elif el.get("data-tval"):
                    rec.sent = el.get("data-tval")
                else:
                    rec.sent = _value_for(dp, current)
                if kind == "grid":
                    n = int(el.get("data-gc") or 0)
                    if grid_rows is None:
                        grid_rows = client.get(f"/api/cases/{case}/comparables?kind=sales").json()["rows"]
                    row = next((r for r in grid_rows if (r["subject_fid"] if n == 0 else r["comp_fid"]) == fid), None)
                    pts = ((row or {}).get("subject_points" if n == 0 else "comp_points") or [{}])
                    point = pts[0].get("data_point", "")
                    if pts[0].get("options"):
                        rec.sent = pts[0]["options"][0]["value"]
                    r = client.patch(f"/api/cases/{case}/comparables/{n}/fields/{fid}",
                                     json={"kind": "sales", "data_point": point, "value": rec.sent})
                elif kind == "cell":
                    body = {"value": rec.sent, "key": el.get("data-tk") or "", "data_point": el.get("data-tdp") or "",
                            "sel": el.get("data-tsel") or "", "label": el.get("data-tlab") or "",
                            "new": bool(el.get("data-tnew")), "scope": el.get("data-tscope") or "",
                            "cat": el.get("data-tcat") or ""}
                    r = client.patch(f"/api/cases/{case}/cells/{fid}", json=body)
                elif el.get("data-route"):
                    r = client.patch(f"/api/cases/{case}/{el.get('data-route')}", json={"value": rec.sent})
                else:
                    r = client.patch(f"/api/cases/{case}/fields/{fid}", json={"value": rec.sent})
                rec.status = r.status_code
                try:
                    data = r.json()
                except ValueError:
                    data = {}
                rec.shown = str(data.get("value", ""))[:80]
                if r.status_code != 200:
                    rec.detail = str(data.get("detail", r.text))[:200]
                results[fid].append(rec)
            # what prints now
            tree = store.tree(case)
            printed = lhtml.fromstring(form.galley_html(form.build(tree, folder=store.folder(case)))).text_content()
            printed = " ".join(printed.split())
            for fid, recs in results.items():
                for rec in recs:
                    if rec.status == 200 and rec.shown:
                        rec.printed = rec.shown.split(" | ")[0] in printed
            problems = schema.validate(tree)
            results["__schema__"] = [Live("schema", detail=p.message[:200]) for p in problems[:10]]
        store.conn.close()
    return results


def judge(d: Dossier) -> str:
    recs = [r for r in d.live if r.control != "derived"]
    if not recs:
        if any(r.control == "derived" for r in d.live):
            return "derived (Summary redisplay)"
        return "NO CONTROL"
    bad = [r for r in recs if r.status != 200]
    if bad:
        return f"SAVE FAILS ({len(bad)}/{len(recs)})"
    unprinted = [r for r in recs if r.shown and not r.printed]
    if unprinted:
        return "saved, NOT IN PRINT"
    return "ok"


def report(section: int, as_json: bool = False) -> list[Dossier]:
    ds = dossiers(section)
    got = live(section)
    for d in ds:
        d.live = got.get(d.fid, [])
        d.verdict = judge(d)
    if as_json:
        WORK.mkdir(parents=True, exist_ok=True)
        (WORK / f"{section:02d}.json").write_text(
            json.dumps({"fields": [asdict(d) for d in ds],
                        "schema": [asdict(x) for x in got.get("__schema__", [])]}, indent=1),
            encoding="utf-8")
    for d in ds:
        print(f"\n== {d.fid}  {d.label}  [{d.subsection or '-'}]  -> {d.verdict}")
        if d.shapes:
            print("   shape:", "; ".join(d.shapes))
        for p in d.points:
            en = f" enums={len(p.enums)}" if p.enums else ""
            cond = p.cond + (f" ({p.cond_details})" if p.cond_details else "")
            print(f"   {p.uid} {p.mismo} {p.format}{'(' + p.length + ')' if p.length else ''} {cond}"
                  f"{en} ctx={p.context!r} in {p.container}")
        for r in d.display:
            print("   B-1:", r[:220])
        for r in d.rules[:6]:
            print("   H-1:", r[:220])
        for r in d.live:
            print(f"   live {r.control} key={r.key!r} sent={r.sent!r} -> {r.status} shown={r.shown!r}"
                  f" printed={r.printed} {r.detail}")
    for s in got.get("__schema__", []):
        print("SCHEMA:", s.detail)
    return ds


if __name__ == "__main__":
    report(int(sys.argv[1]), "--json" in sys.argv)
