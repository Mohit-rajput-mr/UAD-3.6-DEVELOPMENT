"""H-1 rules executed by sentence shape (uad/compliance_shapes.py).

Each shape must leave every D-1 sample alone (they are compliant) and must
fire on a copy of a sample broken in exactly the way the rule describes.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, compliance, compliance_shapes as cs, templates  # noqa: E402

M = f"{{{bind.MISMO}}}"


def _rule(mid):
    return next(r for r in compliance.rules() if r.message_id == mid)


@pytest.mark.parametrize("key", [t.key for t in templates.catalogue()])
def test_no_shape_faults_a_published_sample(key):
    root = templates.load(key).getroot()
    fired = [r.message_id for r in compliance.rules() if not r.executable and cs.decide(root, r)]
    assert fired == []


def _subject(root):
    return bind.subject(root)


def _set(root, name, value):
    node = next(_subject(root).iter(f"{M}{name}"))
    node.text = value


BREAKS = {
    "UAD1005": lambda r: _set(r, "PostalCode", "1234"),
    "UAD1007": lambda r: _set(r, "StateCode", "ZZ"),
    "UAD1011": lambda r: _set(r, "AccessoryDwellingUnitTotalCount", "3"),
    "UAD1015": lambda r: _set(r, "DwellingCount", "5"),
    "UAD1016": lambda r: _set(r, "DwellingCount", "2"),
    "UAD1019": lambda r: _set(r, "LivingUnitExcludingADUCount", "4"),
}


@pytest.mark.parametrize("mid", sorted(BREAKS))
def test_each_shape_fires_on_a_broken_sample(mid):
    root = templates.load("sf1_appraisal_v1_4").getroot()
    assert cs.decide(root, _rule(mid)) is False
    BREAKS[mid](root)
    assert cs.decide(root, _rule(mid)) is True


def test_an_instance_rule_fires_when_its_instance_is_missing():
    # UAD1624: subject to repair, but no defect asks for a repair (SF1's roof does)
    root = templates.load("sf1_appraisal_v1_4").getroot()
    rule = _rule("UAD1624")
    assert cs.decide(root, rule) is False
    for n in root.iter(f"{M}DefectItemRecommendedActionType"):
        if n.text == "Repair":
            n.text = "None"
    assert cs.decide(root, rule) is True


def test_shapes_run_inside_evaluate():
    root = templates.load("sf1_appraisal_v1_4").getroot()
    _set(root, "PostalCode", "1234")
    hit = [f for f in compliance.evaluate(root) if f.message_id == "UAD1005"]
    assert hit and hit[0].status == compliance.FINDING


def _drop(node):
    node.getparent().remove(node)


def _sample(key="sf1_appraisal_v1_4"):
    return templates.load(key).getroot()


def test_child_required_fires_when_a_child_lacks_its_value():
    root = _sample()
    rule = _rule("UAD1150")             # Flooring needs FLOOR_COVERING with FlooringType
    assert cs.decide(root, rule) is False
    _drop(next(_subject(root).iter(f"{M}FlooringType")))
    assert cs.decide(root, rule) is True


def test_none_provided_fires_without_the_utility():
    root = _sample()
    rule = _rule("UAD1346")             # Water
    assert cs.decide(root, rule) is False
    for d in list(_subject(root).iter(f"{M}SITE_UTILITY_DETAIL")):
        if d.findtext(f"{M}UtilityType") == "Water":
            _drop(d.getparent())
    assert cs.decide(root, rule) is True


def test_no_property_fires_without_rental_comparables():
    root = _sample("2_to_4_unit_appraisal_v1_4")
    rule = _rule("UAD1217")
    assert cs.decide(root, rule) is False
    for p in [p for p in root.iter(f"{M}PROPERTY") if p.get("ValuationUseType") == "RentalComparable"]:
        _drop(p)
    assert cs.decide(root, rule) is True


def test_arcrole_fires_without_the_link():
    root = _sample()
    rule = _rule("UAD1183")             # a data source for the unit's area
    assert cs.decide(root, rule) is False
    for r in list(root.iter(f"{M}RELATIONSHIP")):
        if r.get("{http://www.w3.org/1999/xlink}arcrole", "").endswith("PROPERTY_UNIT_AREA"):
            _drop(r)
    assert cs.decide(root, rule) is True


def test_dates_compare():
    root = _sample()
    rule = _rule("UAD1131")             # contract after the effective date
    assert cs.decide(root, rule) is False
    next(root.iter(f"{M}SalesContractDate")).text = "2030-01-01"
    assert cs.decide(root, rule) is True


def test_a_party_condition_is_read_party_by_party():
    root = _sample()
    rule = _rule("UAD1534")             # trainee appraiser needs a supervisor
    assert cs.decide(root, rule) is False          # SF1: the trainee is the assistant
    for party in root.iter(f"{M}PARTY"):
        if any(n.text == "Appraiser" for n in party.iter(f"{M}PartyRoleType")):
            for n in party.iter(f"{M}AppraiserLicenseType"):
                n.text = "TraineeAppraiser"
    for party in list(root.iter(f"{M}PARTY")):
        if any(n.text == "AppraiserSupervisor" for n in party.iter(f"{M}PartyRoleType")):
            _drop(party)
    assert cs.decide(root, rule) is True


def test_a_bare_condition_fires_when_it_holds():
    root = _sample()
    rule = _rule("UAD1512")             # traditional appraisal certified as exterior-only
    assert cs.decide(root, rule) is False
    next(root.iter(f"{M}ValuationReportInspectionCertificationType")).text = "Exterior"
    assert cs.decide(root, rule) is True


def test_market_inventory_must_be_there():
    root = _sample()
    rule = _rule("UAD1638")
    assert cs.decide(root, rule) is False
    for inv in list(root.iter(f"{M}MARKET_INVENTORY")):
        if inv.findtext(f".//{M}MarketInventoryType") == "ActiveListings":
            _drop(inv)
    assert cs.decide(root, rule) is True


def test_a_party_needs_a_name():
    root = _sample()
    rule = _rule("UAD1701")             # Borrower
    assert cs.decide(root, rule) is False
    for party in root.iter(f"{M}PARTY"):
        if any(n.text == "Borrower" for n in party.iter(f"{M}PartyRoleType")):
            for n in list(party.iter(f"{M}FullName")) + list(party.iter(f"{M}LastName")):
                _drop(n)
            break
    assert cs.decide(root, rule) is True


def test_unit_count_per_improvement():
    root = _sample()
    rule = _rule("UAD1086")
    assert cs.decide(root, rule) is False
    next(_subject(root).iter(f"{M}LivingUnitCount")).text = "3"
    assert cs.decide(root, rule) is True
