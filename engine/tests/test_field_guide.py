"""Field guidance: what UAD 3.6 asks of a field, and whether it passes now.

GET /api/cases/{id}/guide/{fid} reads A-1 (required, required when, optional;
the definition and format) and H-1 (the rules on the field) and gives each
rule's live status for the open report (knowledge/competitors/WINTOTAL_UAD36.md
row 1).  A-1's condition language is read by uad/conditions.py.

Run:  python -m pytest -q engine/tests/test_field_guide.py
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest
from fastapi import HTTPException

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app import api
from app.cases import Store
from uad import conditions, edit, templates

SPEC = Path(__file__).resolve().parents[1] / "spec"


def _all_conditions() -> list[str]:
    seen = []
    for fid in json.loads((SPEC / "field_index.json").read_text(encoding="utf-8"))["fields"]:
        try:
            pf = edit.field(fid)
        except KeyError:
            continue
        for d in pf.binding.data_points:
            t = (d.get("conditionality_details") or "").strip()
            if t and t not in seen:
                seen.append(t)
    return seen


# ------------------------------------------------------------ the language
@pytest.mark.parametrize("text,said,scope", [
    ('IF @ValuationUseType = "SalesComparable" AND ListingStatusType = "Pending" OR "SettledSale"',
     "Listing Status is Pending or Settled Sale", ["each Sales Comparable"]),
    ('IF PartyRoleType = "Borrower" AND Exists', "there is one", ["the Borrower"]),
    ('IF PartyRoleType = "AppraiserSupervisor"', "", ["the Appraiser Supervisor"]),
    ('IF ValuationAssignmentType = "Other"', "Valuation Assignment is Other", []),
    ('IF AddressUnitIdentifier Is Present', "Address Unit is given", []),
    ('IF LivingUnitExcludingADUCount > 1 OR AccessoryDwellingUnitTotalCount > 0',
     "Living Unit Excluding ADU is more than 1 or Accessory Dwelling Unit Total is more than 0", []),
    ('IF MarketingOrExposureLowRangeDaysCount AND MarketingOrExposureHighRangeDaysCount Is Not Present',
     "Marketing Or Exposure Low Range Days and Marketing Or Exposure High Range Days are not given", []),
    ('IF (@ValuationUseType = "SubjectProperty" AND HazardZoneType != "None") OR '
     '(@ValuationUseType = "SalesComparable" AND CostApproachIndicator = "true")',
     "for the Subject Property: Hazard Zone is not None; or for each Sales Comparable: Cost Approach is Yes", []),
])
def test_conditions_read_as_sentences(text, said, scope):
    assert conditions.read(text) == (said, scope)


def test_every_a1_condition_reads_without_its_syntax():
    """All of A-1's conditions, not a hand-picked few: none may leak a
    parenthesis, quote, operator, keyword or a CamelCase name, and none may
    read as nothing at all."""
    texts = _all_conditions()
    assert len(texts) > 500
    leaky = []
    for t in texts:
        said, scope = conditions.read(t)
        if re.search(r'[()"@=<>]|\b(IF|AND|OR)\b|[a-z][A-Z]', said) or not (said or scope):
            leaky.append((t, said))
    assert not leaky, leaky[:5]


# ------------------------------------------------------------ the endpoint
@pytest.fixture(scope="module")
def cases(tmp_path_factory):
    store = Store(tmp_path_factory.mktemp("guide") / "cases")
    saved = api.STORE
    api.STORE = store
    filled = store.create(template="sf1_appraisal_v1_4", blank=False).case_id
    blank = store.create(template="sf1_appraisal_v1_4", blank=True).case_id
    yield store, filled, blank
    api.STORE = saved
    store.conn.close()


def _status(g):
    return {r["id"]: r["status"] for r in g["rules"]}


def test_a_failing_rule_is_shown_failing_and_passes_once_answered(cases):
    _, filled, blank = cases
    empty = api.field_guide(blank, "3.002")
    assert empty["label"] == "County" and empty["requirement"] == "R"
    assert _status(empty)["UAD1003"] == "fail"
    assert [p["code"] for p in empty["problems"]] == ["UAD1003"]
    assert _status(api.field_guide(filled, "3.002"))["UAD1003"] == "ok"


def test_a_value_printed_twice_fails_in_both_places(cases):
    """The Summary's 1.001 repeats Reconciliation's 26.007; the finding is
    filed under one of them, the guidance shows it on both."""
    _, _, blank = cases
    assert _status(api.field_guide(blank, "1.001"))["UAD1262"] == "fail"
    assert _status(api.field_guide(blank, "26.007"))["UAD1262"] == "fail"


def test_rules_belong_to_the_field_not_only_its_data_point(cases):
    """AddressLineText is checked for the subject and for every comparable;
    the comparable grid's address row shows the comparable rules only."""
    _, _, blank = cases
    grid = api.field_guide(blank, "22.01.17")
    assert grid["scope"] == ["each Sales Comparable"]
    assert {"UAD1390", "UAD1391", "UAD1392", "UAD1393"} <= set(_status(grid))
    subject = api.field_guide(blank, "3.000")             # the subject's Physical Address
    assert subject["rules"] and not {"UAD1390", "UAD1391"} & set(_status(subject))


def test_requirement_scope_and_conditions(cases):
    _, filled, _ = cases
    g = api.field_guide(filled, "22.01.30")
    assert g["label"] == "Contract Date" and g["requirement"] == "CR"
    assert "Contract Date Unknown: when Listing Status is Pending or Settled Sale" in g["conditions"]
    # required in its block, which may not be there: not "always required"
    d = api.field_guide(filled, "2.048")
    assert d["requirement"] == "R" and d["scope"] == ["the Significant Real Property Appraisal Assistance"]
    assert d["max"] == 2500                     # A-1 String format, the comment counter's limit


def test_an_unknown_field_is_404(cases):
    _, filled, _ = cases
    with pytest.raises(HTTPException) as e:
        api.field_guide(filled, "99.999")
    assert e.value.status_code == 404


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_guidance_agrees_with_review_master_on_every_sample(key, tmp_path, monkeypatch):
    """Validate the validator: on each official D-1 sample, a rule the
    guidance shows failing is a Review Master finding, and every Fatal or
    Warning finding filed under a field shows as failing in its guidance."""
    store = Store(tmp_path / "cases")
    monkeypatch.setattr(api, "STORE", store)
    cid = store.create(template=key, blank=False).case_id
    items = store.review(cid).to_json()["items"]
    found = {(i["field_id"], i["code"]) for i in items if i["severity"] in ("Fatal", "Warning")}
    codes = {i["code"] for i in items if i["severity"] in ("Fatal", "Warning")}
    fields = sorted({f for f, _ in found if f}) or ["3.002"]
    for fid in fields:
        g = api.field_guide(cid, fid)
        failing = {r["id"] for r in g["rules"] if r["status"] == "fail"}
        assert failing <= codes, (fid, failing - codes)
        shown = {p["code"] for p in g["problems"]}
        assert {c for f, c in found if f == fid} <= shown, fid
    store.conn.close()
