"""The structure engine: dwellings, units, ADUs and outbuildings as a tree,
counts derived from it (owner's brief T-1035; knowledge/blueprint/STUDY.md s4).

Acceptance (owner's brief): start from a blank new report, apply only setup
answers and structure operations through the API, and arrive at each D-1
sample's structure -- same dwellings, units per dwelling, ADUs, outbuildings
(by type) and counts -- with no schema error the published sample does not
have.  Plus: a unit added on a 2-unit report gives every sales comparable a
linked unit row; removing it shows the loss first and takes those rows away.

Run:  python -m pytest -q engine/tests/test_structure_engine.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api  # noqa: E402
from app.access import sign_in  # noqa: E402
from app.cases import Store  # noqa: E402
from uad import schema, structure, templates  # noqa: E402

M = "{http://www.mismo.org/residential/2009/schemas}"
XL = "{http://www.w3.org/1999/xlink}"


@pytest.fixture(scope="module")
def client(tmp_path_factory):
    from app.main import app
    api.STORE = Store(tmp_path_factory.mktemp("cases"))
    api.RENDERER = None
    api.LAYOUTS = None
    with TestClient(app) as c:
        sign_in(c)
        yield c


def shape_of(t: dict) -> dict:
    return {"dwellings": sorted(len(d["units"]) for d in t["dwellings"]),
            "adus_in_dwellings": sum(u["adu"] for d in t["dwellings"] for u in d["units"]),
            "outbuildings": sorted((o["type"], len(o["units"])) for o in t["outbuildings"]),
            "counts": {k: v for k, v in t["counts"].items()}}


@pytest.mark.parametrize("template", [t.key for t in templates.catalogue()])
def test_every_sample_structure_can_be_built_from_a_new_report(client, template):
    sample = templates.load(template).getroot()
    want = structure.tree(sample)
    t = templates.get(template)
    cid = client.post("/api/cases", json={}).json()["case_id"]
    # setup answers: the determinants that shape the report (B-1: data drives the type)
    for fid, name in (("3.011", "project_legal_structure"), ("3.006", None), ("3.005", "units_excluding_adus")):
        pass
    det = t.determinants
    if det.get("project_legal_structure"):
        fid = {"Condominium": "3.011", "Cooperative": "3.012"}.get(det["project_legal_structure"], "3.013")
        assert client.patch(f"/api/cases/{cid}/fields/{fid}",
                            json={"value": det["project_legal_structure"]}).status_code == 200
    if det.get("construction_method") == "Manufactured":
        assert client.patch(f"/api/cases/{cid}/fields/1.012" if False else f"/api/cases/{cid}/extra/0300.0034",
                            json={"value": "Manufactured"}).status_code in (200, 404, 422)
    # structure operations: dwellings, then units in each, ADUs, outbuildings
    have = client.get(f"/api/cases/{cid}/structure").json()
    for d in have["outbuildings"]:
        assert client.delete(f"/api/cases/{cid}/structure", params={"key": d["key"]}).status_code == 200
    while len(client.get(f"/api/cases/{cid}/structure").json()["dwellings"]) < len(want["dwellings"]):
        client.post(f"/api/cases/{cid}/structure", json={"add": "dwelling"})
    for i, d in enumerate(want["dwellings"]):
        need_units = [u for u in d["units"] if not u["adu"]]
        need_adus = [u for u in d["units"] if u["adu"]]
        cur = client.get(f"/api/cases/{cid}/structure").json()["dwellings"][i]
        for _ in range(len(need_units) - sum(not u["adu"] for u in cur["units"])):
            assert client.post(f"/api/cases/{cid}/structure", json={"add": "unit", "dwelling": i}).status_code == 200
        for _ in range(len(need_adus) - sum(u["adu"] for u in cur["units"])):
            assert client.post(f"/api/cases/{cid}/structure",
                               json={"add": "adu", "dwelling": i}).status_code == 200
    for o in want["outbuildings"]:
        body = {"add": "adu", "location": "outbuilding", "type": o["type"]} if o["units"] \
            else {"add": "outbuilding", "type": o["type"] if o["type"] in ("Barn",) else "Other",
                  "other": "" if o["type"] in ("Barn",) else o["type"]}
        assert client.post(f"/api/cases/{cid}/structure", json=body).status_code == 200, body
    got = client.get(f"/api/cases/{cid}/structure").json()
    assert shape_of(got)["dwellings"] == shape_of(want)["dwellings"], (template, got, want)
    assert shape_of(got)["counts"]["units_excluding_adus"] == want["counts"]["units_excluding_adus"]
    assert shape_of(got)["counts"]["adus"] == want["counts"]["adus"]
    assert len(got["outbuildings"]) == len(want["outbuildings"])
    # the counts in the document are the tree's
    root = api.store().tree(cid).getroot()
    subj = structure._subject(root)
    assert subj.findtext(f".//{M}LivingUnitExcludingADUCount") == str(want["counts"]["units_excluding_adus"])
    assert subj.findtext(f".//{M}AccessoryDwellingUnitTotalCount") == str(want["counts"]["adus"])


def test_typing_the_unit_count_builds_the_units_and_the_comparable_rows(client):
    cid = client.post("/api/cases", json={}).json()["case_id"]
    r = client.patch(f"/api/cases/{cid}/fields/3.005", json={"value": "3"})
    assert r.status_code == 200, r.text
    t = client.get(f"/api/cases/{cid}/structure").json()
    assert t["counts"]["units_excluding_adus"] == 3
    root = api.store().tree(cid).getroot()
    subject_units = {u.get(f"{XL}label") for u in structure.all_units(structure._subject(root))}
    for comp in structure._comparables(root):
        linked = {r.get(f"{XL}to") for r in root.iter(f"{M}RELATIONSHIP")
                  if r.get(f"{XL}arcrole", "").endswith("PROPERTY_UNIT_IsComparableFor_PROPERTY_UNIT")
                  and r.get(f"{XL}from") in {u.get(f"{XL}label") for u in comp.iter(f"{M}PROPERTY_UNIT")}}
        assert linked == subject_units
    idents = [u["identifier"] for d in t["dwellings"] for u in d["units"]]
    assert len(set(idents)) == len(idents) and all(idents)       # F-1 10.002: unique
    assert not [e for e in schema.validate(api.store().tree(cid)) if "PROPERTY_UNIT" in str(e.message)]


def test_removing_a_unit_says_what_goes_first(client):
    cid = client.post("/api/cases", json={"template": "2_to_4_unit_appraisal_v1_4", "blank": False}).json()["case_id"]
    t = client.get(f"/api/cases/{cid}/structure").json()
    unit = t["dwellings"][1]["units"][0]
    lost = client.get(f"/api/cases/{cid}/structure/loss", params={"key": unit["key"]}).json()["lost"]
    assert lost                                     # the sample unit holds answers
    # typing a smaller count does not drop them silently
    r = client.patch(f"/api/cases/{cid}/fields/3.005", json={"value": "1"})
    assert r.status_code == 409 and r.json()["lost"]
    r = client.delete(f"/api/cases/{cid}/structure", params={"key": unit["key"]})
    assert r.status_code == 200, r.text
    root = api.store().tree(cid).getroot()
    assert not any(r_.get(f"{XL}to") == unit["label"] for r_ in root.iter(f"{M}RELATIONSHIP"))
    for comp in structure._comparables(root):
        assert len(list(comp.iter(f"{M}PROPERTY_UNIT"))) == 1
    assert r.json()["counts"]["units_excluding_adus"] == 1


def test_the_last_living_unit_and_dwelling_stay(client):
    cid = client.post("/api/cases", json={}).json()["case_id"]
    t = client.get(f"/api/cases/{cid}/structure").json()
    r = client.delete(f"/api/cases/{cid}/structure", params={"key": t["dwellings"][0]["units"][0]["key"]})
    assert r.status_code == 422
    r = client.delete(f"/api/cases/{cid}/structure", params={"key": t["dwellings"][0]["key"]})
    assert r.status_code == 422
