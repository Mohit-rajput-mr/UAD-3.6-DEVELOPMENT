"""The owner's validation-as-you-type checks no GSE rule states (T-510).

The owner's desktop-rebuild brief (DR section 6.5) asks for warnings, never
blocks, on: a name that does not match between borrower, owner of public
record and seller; impossible dates; a gross living area total that does not
match the units; comparables sold after the effective date.  Two of them are
already H-1's and are not repeated here:

* signature before inspection -- UAD1536 (ExecutionDate before the effective
  date) and UAD1557 (InspectionDate after it) together leave no signature
  before the inspection;
* the area total -- A-1 defines TotalFinishedAreaOfAllLivingUnitsIncludingADU
  AreaMeasure as the units' finished area *plus common area*, so it need not
  equal the units' sum; a check that it does would be wrong.

What is left is checked here.  None of it is a specification rule, and every
finding says so; each is a Warning in the Review Master and holds on all
twelve D-1 samples (tests/test_owner_checks.py):

``O1``  on a purchase, a seller who is not an owner of public record (one
        MISMO party carries both roles when they are the same person; a
        second party of the same name counts as the same person);
``O2``  on a refinance, no borrower among the owners of public record;
``O3``  a comparable sale dated after the effective date.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from . import bind

M = f"{{{bind.MISMO}}}"
NOT_A_RULE = "The owner's check (DR 6.5), not a GSE rule: confirm, and explain in the commentary if it is right."


@dataclass
class Finding:
    code: str
    message: str
    field_id: str = ""
    path: str = ""
    detail: str = NOT_A_RULE


def _name(party) -> str:
    full = party.findtext(f".//{M}FullName")
    if full:
        return full.strip()
    parts = [party.findtext(f".//{M}NAME/{M}{p}") for p in ("FirstName", "MiddleName", "LastName", "SuffixName")]
    return " ".join(p.strip() for p in parts if p and p.strip())


def _key(name: str) -> str:
    return re.sub(r"[^a-z0-9]", "", name.casefold())


def _parties(root) -> dict[str, list[tuple[str, object]]]:
    """role -> [(name, party)] for the deal's parties."""
    out: dict[str, list] = {}
    for party in root.iter(M + "PARTY"):
        name = _name(party)
        for role in {r.text for r in party.iter(M + "PartyRoleType") if r.text}:
            out.setdefault(role, []).append((name, party))
    return out


def names(root) -> list[Finding]:
    kind = next((e.text for e in root.iter(M + "ValuationAssignmentType") if e.text), "")
    parties = _parties(root)
    owners = {_key(n) for n, _p in parties.get("PropertyOwner", []) if n}
    if not owners:
        return []                    # nobody entered as owner: H-1 asks for that, not this
    out = []
    if kind == "Purchase":
        for name, party in parties.get("PropertySeller", []):
            if name and _key(name) not in owners:
                out.append(Finding(
                    code="O1", field_id="2.002", path=bind.stable_path(party),
                    message=(f"The seller, {name}, is not an owner of public record "
                             f"({', '.join(n for n, _p in parties['PropertyOwner'] if n)})")))
    elif kind == "Refinance":
        borrowers = [(n, p) for n, p in parties.get("Borrower", []) if n]
        if borrowers and not any(_key(n) in owners for n, _p in borrowers):
            out.append(Finding(
                code="O2", field_id="2.001", path=bind.stable_path(borrowers[0][1]),
                message=(f"On a refinance no borrower ({', '.join(n for n, _p in borrowers)}) "
                         "is an owner of public record")))
    return out


def sale_dates(root) -> list[Finding]:
    effective = next((e.text.strip() for e in root.iter(M + "AppraisalReportEffectiveDate") if e.text), "")
    if not effective:
        return []
    out = []
    number = 0
    for prop in root.iter(M + "PROPERTY"):
        if prop.get("ValuationUseType") != "SalesComparable":
            continue
        number += 1
        dates = [d for d in prop.iter(M + "OwnershipTransferDate") if (d.text or "").strip()]
        latest = max((d.text.strip()[:10] for d in dates), default="")
        for date in dates:
            text = date.text.strip()[:10]
            if text > effective[:10]:
                # the latest is the sale in the grid (22.01.32); an earlier one
                # is in its transfer history (21.009)
                out.append(Finding(
                    code="O3", field_id="22.01.32" if text == latest else "21.009",
                    path=bind.stable_path(date),
                    message=f"Comparable {number} sold {text}, after the effective date {effective[:10]}"))
    return out


def check(tree) -> list[Finding]:
    from . import report_types
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    if report_types.kind_of(root) != report_types.URAR:
        return []
    return names(root) + sale_dates(root)
