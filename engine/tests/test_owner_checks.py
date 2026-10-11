"""The owner's validation-as-you-type checks (T-510, DR 6.5) -- warnings that
say they are not a GSE rule, silent on all twelve D-1 samples, raised by a
copy broken the way each describes.

Run:  python -m pytest -q engine/tests/test_owner_checks.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest
from lxml import etree

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from uad import bind, owner_checks, review, templates

M = f"{{{bind.MISMO}}}"
KEYS = [t.key if hasattr(t, "key") else t for t in templates.catalogue()]


def _tree(key):
    return etree.parse(str(templates.get(key).path))


@pytest.mark.parametrize("key", KEYS)
def test_no_published_sample_is_faulted(key):
    assert owner_checks.check(_tree(key)) == []


def _party(root, role):
    return next(p for p in root.iter(M + "PARTY") if role in {r.text for r in p.iter(M + "PartyRoleType")})


def test_a_seller_who_is_not_the_owner():
    tree = _tree("sf1_appraisal_v1_4")              # purchase; Jane Doe sells and owns
    seller = _party(tree.getroot(), "PropertySeller")
    roles = [r for r in seller.iter(M + "PartyRoleType") if r.text == "PropertyOwner"]
    roles[0].getparent().getparent().remove(roles[0].getparent())  # she sells, someone else owns
    owner = etree.fromstring(etree.tostring(seller))
    owner.find(f".//{M}FirstName").text = "John"
    for r in owner.iter(M + "PartyRoleType"):
        r.text = "PropertyOwner"
    seller.addnext(owner)
    found = owner_checks.check(tree)
    assert [(f.code, f.field_id) for f in found] == [("O1", "2.002")]
    assert "Jane Doe" in found[0].message and "John Doe" in found[0].message
    assert "not a GSE rule" in found[0].detail
    owner.find(f".//{M}FirstName").text = "JANE"      # the same person, entered twice
    assert owner_checks.check(tree) == []


def test_a_refinance_by_someone_not_on_title():
    tree = _tree("mh1_appraisal_v1_4")              # refinance; Harry James borrows and owns
    for p in list(tree.getroot().iter(M + "PARTY")):
        if "Borrower" in {r.text for r in p.iter(M + "PartyRoleType")}:
            for r in [r for r in p.iter(M + "PartyRoleType") if r.text == "PropertyOwner"]:
                role = next(a for a in r.iterancestors() if etree.QName(a).localname == "ROLE")
                role.getparent().remove(role)          # no longer on title
    found = owner_checks.check(tree)
    assert [(f.code, f.field_id) for f in found] == [("O2", "2.001")]


def test_a_comparable_sold_after_the_effective_date():
    tree = _tree("sf1_appraisal_v1_4")              # effective 2019-09-20
    comp = next(p for p in tree.getroot().iter(M + "PROPERTY") if p.get("ValuationUseType") == "SalesComparable")
    dates = sorted(comp.iter(M + "OwnershipTransferDate"), key=lambda d: d.text)
    dates[-1].text = "2019-10-01"
    found = owner_checks.check(tree)
    assert [(f.code, f.field_id) for f in found] == [("O3", "22.01.32")]
    assert "Comparable 1 sold 2019-10-01" in found[0].message
    report = review.build(tree)
    items = [i for i in report.items if i.source == review.OWNER]
    assert [(i.code, i.severity) for i in items] == [("O3", "Warning")] and not set(map(id, items)) & set(map(id, report.fatal))
