"""H-1 rules whose consequent is not "X is not provided", executed by shape.

H-1 writes most of its 728 rules as a presence requirement, which
``compliance.evaluate`` runs directly.  The rest it writes in a handful of
recurring sentence shapes -- a count that must equal the number of instances,
one value that must not exceed another, an instance that must exist, a value
that must have a given format.  Each shape below is recognised from the rule's
own Logic text and executed against the document; a rule no shape recognises
stays for review, exactly as before.

Every shape is checked against the twelve D-1 samples, which are compliant by
construction: a shape that faults a published sample is a broken shape
(CLAUDE.md "Validate your validators"), and tests/test_compliance_shapes.py
holds it to that and to a deliberately broken copy of each sample.

``decide`` answers True (the rule fires), False (it holds) or None (no shape
applies, or the document does not let the shape decide).
"""
from __future__ import annotations

import re
from datetime import date

from lxml import etree

from . import bind

M = f"{{{bind.MISMO}}}"
X = "{http://www.w3.org/1999/xlink}"

#: role words H-1 uses in "Property Affected" -> @ValuationUseType
ROLE = {"SubjectProperty": "SubjectProperty"}

# "If AccessoryDwellingUnitTotalCount <> the number of instances of
# PROPERTY_UNIT_DETAIL with AccessoryDwellingUnitIndicator = "true""
COUNT_EQ = re.compile(
    r'^If (?P<a>\w+) (?:<>|does not equal) the number of instances of (?P<c>[A-Z_]+)'
    r'(?: with (?P<d>\w+) = "(?P<v>[^"]+)")?\s*$')
# "If DwellingCount > LivingUnitExcludingADUCount"
COMPARE = re.compile(r'^If (?P<a>[A-Z]\w+) (?P<op><>|>=|<=|>|<) (?P<b>[A-Z]\w+)\s*$')
# "If ListingStartDate > ListingEndDate in a given instance of LISTING_INFORMATION_DETAIL"
COMPARE_IN = re.compile(r'^If (?P<a>[A-Z]\w+) (?P<op><>|>=|<=|>|<) (?P<b>[A-Z]\w+) in a given instance of [A-Z_]+\s*$')
_DATE = re.compile(r"^\d{4}-\d{2}(-\d{2})?$")
# "If SpecialTaxAssessmentsIndicator = "true", and there is no instance of
# VALUATION_COMMENTARY with ValuationAnalysisCategoryType = "X""
NO_INSTANCE = re.compile(
    r'^If (?P<ante>.+?),? and (?:there (?:is|are) no instances? of (?P<c>[A-Z_]+) with '
    r'(?P<d>\w+) = "(?P<v>[^"]+)"|no instances of (?P<c2>[A-Z_]+) with (?P<d2>\w+) = '
    r'"(?P<v2>[^"]+)" are provided)\s*$')
# "If PostalCode is not in the required format (5 digits, or 5 digits, a
# hyphen, and 4 digits)"
# "If ImprovementComponentType = "Flooring" and (at least one instance of
# FLOOR_COVERING is not provided or FlooringType is not provided in a given
# instance of FLOOR_COVERING)" -- and the same without a condition
CHILD_REQUIRED = re.compile(
    r'^If (?:(?P<ante>.+?),? and )?\(?\s*at least one instance of (?P<c>[A-Z_]+) is not provided '
    r'or (?P<d>\w+) is not provided in a given instance of (?P=c)\s*\)?\s*$')
# "If no instances of SITE_UTILITY_DETAIL with UtilityType = "Water" are provided"
NONE_PROVIDED = re.compile(r'^If no instances of (?P<c>[A-Z_]+) with (?P<d>\w+) = "(?P<v>[^"]+)" are provided\s*$')
# "If IncomeApproachIndicator = "true" and there are no instances of PROPERTY
# with @ValuationUseType = "GrossRentMultiplierComparable""
NO_PROPERTY = re.compile(
    r'^If (?P<ante>.+?),? and there are no instances of PROPERTY with @ValuationUseType = "(?P<use>\w+)"\s*$')
# "If IncomeApproachIndicator is "true" and RentScheduleIndicator is "false""
BOTH_ARE = re.compile(r'^If (?P<a>\w+) is "(?P<x>[^"]+)" and (?P<b>\w+) is "(?P<y>[^"]+)"\s*$')
# "... and there is no instance of RELATIONSHIP with @xlink:arcrole = "...
# DATA_SOURCE_IsDataSourceFor_X" that links DATA_SOURCE to X"
ARCROLE = re.compile(
    r'^If (?:(?P<ante>.+?),? and )?there is no instance of RELATIONSHIP with @xlink:arcrole = '
    r'"(?P<arc>[^"]+)" that links DATA_SOURCE to (?P<each>each )?(?P<t>\w+)')
# "If there is no instance of MARKET_INVENTORY with MarketInventoryType = "ActiveListings""
THERE_IS_NONE = re.compile(r'^If there (?:is|are) no instances? of (?P<c>[A-Z_]+) with (?P<d>\w+) = "(?P<v>[^"]+)"\s*$')
# "If ValuationAnalysisCategoryType = ("HazardZones" or ...) and
# ValuationCommentText length exceeds 140 characters"
TEXT_LENGTH = re.compile(
    r'^If ValuationAnalysisCategoryType = \(?(?P<cats>(?:"\w+"(?:\s+or\s+)?)+)\)? and '
    r'ValuationCommentText length exceeds (?P<n>\d+) characters\s*$', re.I)
# "If neither FullName nor LastName is provided for PartyRoleType = "Borrower""
NEITHER = re.compile(r'^If neither (?P<a>\w+) nor (?P<b>\w+) is provided for PartyRoleType = "(?P<role>\w+)"\s*$')
# "For each IMPROVEMENT, if LivingUnitCount <> the number of instances of PROPERTY_UNIT"
FOR_EACH_COUNT = re.compile(
    r'^For each (?P<o>[A-Z_]+), if (?P<a>\w+) <> the number of instances of (?P<c>[A-Z_]+)\s*$')
# "If ImprovementType = 'Dwelling' and there are no instances of PROPERTY_UNIT"
BLOCK_WITHOUT = re.compile(
    r'^If (?P<a>\w+) = ["\u2018\u2019\']+(?P<v>\w+)["\u2018\u2019\']+ and there are no instances of (?P<c>[A-Z_]+)\s*$')
# a condition and nothing else: "If PropertyValuationMethodType =
# "TraditionalAppraisal" and ValuationReportInspectionCertificationType <> "InteriorAndExterior""
PURE = re.compile(r'^If (?P<ante>(?:\(|\)|\s|AND\b|OR\b|\w+\s*(?:=|<>)\s*"[^"]*"(?:\s+or\s+"[^"]*")*)+)$', re.I)
POSTAL = re.compile(r'^If PostalCode is not in the required format')
STATE = re.compile(r'^If StateCode is not a valid 2-character US State or Territory Code')

# USPS two-letter codes for the states, DC, territories and military "states"
# -- the set H-1's "valid 2-character US State or Territory Code" names.
US_STATES = frozenset("""
AL AK AZ AR CA CO CT DE FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ
NM NY NC ND OH OK OR PA RI SC SD TN TX UT VT VA WA WV WI WY DC AS GU MP PR VI UM FM MH PW
AA AE AP""".split())


def _local(node) -> str:
    return etree.QName(node).localname


def _properties(root, rule) -> list[etree._Element]:
    """The PROPERTY blocks a rule governs, from its Property Affected roles
    (the subject when it names none)."""
    roles = set(getattr(rule, "roles", ()) or ())
    out = []
    for p in root.iter(f"{M}PROPERTY"):
        use = p.get("ValuationUseType") or ""
        if roles:
            if use in roles:
                out.append(p)
        elif use in ("", "SubjectProperty"):
            out.append(p)
    return out


def _number(text: str) -> float | None:
    try:
        return float((text or "").strip())
    except ValueError:
        return None


def _values(scope, name: str) -> list[str]:
    return [(n.text or "").strip() for n in scope.iter(f"{M}{name}") if (n.text or "").strip()]


def _has(block, name: str, value: str) -> bool:
    """Any of the block's own values of ``name`` is ``value`` (a PARTY can
    hold several roles: Lender, then Client)."""
    return any((n.text or "").strip() == value for n in block.iter(f"{M}{name}"))


def _antecedent_holds(text: str, root, scope) -> bool | None:
    """The "if" half, read by the report's own rule reader (``rules.evaluate``),
    which already speaks this grammar (=, <>, OR lists, AND)."""
    from .report import rules as _rules
    d = _rules.evaluate("Display when " + text.strip().rstrip(","), root, scope)
    return d.shown if d.known else None


def decide(root: etree._Element, rule) -> bool | None:
    logic = " ".join((rule.logic or "").split())
    m = POSTAL.match(logic)
    if m:
        values = [v for p in _properties(root, rule) for v in _values(p, "PostalCode")]
        if not values:
            return None
        return any(not re.fullmatch(r"\d{5}(-\d{4})?", v) for v in values)
    m = STATE.match(logic)
    if m:
        values = [v for p in _properties(root, rule) for v in _values(p, "StateCode")]
        if not values:
            return None
        return any(v not in US_STATES for v in values)
    m = COUNT_EQ.match(logic)
    if m:
        decided = False
        for p in _properties(root, rule):
            for node in p.iter(f"{M}{m['a']}"):
                want = _number(node.text)
                if want is None:
                    continue
                blocks = [b for b in p.iter(f"{M}{m['c']}")
                          if not m["d"] or (b.findtext(f"{M}{m['d']}") or "").strip() == m["v"]]
                decided = True
                if int(want) != len(blocks):
                    return True
        return False if decided else None
    m = COMPARE.match(logic) or COMPARE_IN.match(logic)
    if m:
        decided = False
        for p in _properties(root, rule):
            a = _values(p, m["a"]) or _values(root, m["a"])
            b = _values(p, m["b"]) or _values(root, m["b"])
            if not a or not b:
                continue
            x, y = _number(a[0]), _number(b[0])
            if (x is None or y is None) and _DATE.match(a[0]) and _DATE.match(b[0]):
                x, y = a[0], b[0]           # ISO dates compare as text (A-1 format)
            if x is None or y is None:
                continue
            decided = True
            op = m["op"]
            if ((op == ">" and x > y) or (op == "<" and x < y) or (op == ">=" and x >= y)
                    or (op == "<=" and x <= y) or (op == "<>" and x != y)):
                return True
        return False if decided else None
    m = NO_INSTANCE.match(re.sub(r'\s+for @ValuationUseType = "SubjectProperty"', "", logic))
    if m:
        c, d, v = (m["c"], m["d"], m["v"]) if m["c"] else (m["c2"], m["d2"], m["v2"])
        v = re.sub(r"[^\w]", "", v)        # H-1 UAD1079 writes "'ExteriorWallsAndTrim"
        decided = False
        if c == "PARTY":
            # the condition is one party's ("PartyRoleType = Appraiser and
            # AppraiserLicenseType = TraineeAppraiser"): read party by party,
            # not across every party's values at once (D-1 SF1's assistant is
            # the trainee, its appraiser is certified)
            said = [_antecedent_holds(m["ante"], root, b) for b in root.iter(f"{M}PARTY")]
            if any(x is None for x in said) and not any(said):
                return None
            if not any(said):
                return False
            return not any(_has(b, d, v) for b in root.iter(f"{M}{c}"))
        for p in _properties(root, rule):
            holds = _antecedent_holds(m["ante"], root, p)
            if holds is None:
                return None
            decided = True
            if not holds:
                continue
            # the instance may sit in the property, or -- commentary, data
            # sources -- in the valuation the property belongs to
            where = [p] + ([root] if c in ("VALUATION_COMMENTARY", "DATA_SOURCE") else [])
            found = any(_has(b, d, v) for w in where for b in w.iter(f"{M}{c}"))
            if not found:
                return True
        return False if decided else None
    m = NONE_PROVIDED.match(logic)
    if m:
        props = _properties(root, rule)
        if not props:
            return None
        # a block the property cannot hold (PARTY) is looked for in the report
        in_property = "PROPERTIES/PROPERTY" in (getattr(rule, "target_path", "") or "") or \
            (getattr(rule, "target_path", "") or "").startswith("../PROPERTY")
        where = [p if in_property else root for p in props]
        return any(not any(_has(b, m["d"], m["v"]) for b in w.iter(f"{M}{m['c']}")) for w in where)
    m = NO_PROPERTY.match(logic)
    if m:
        holds = _antecedent_holds(m["ante"], root, None)
        if holds is None:
            return None
        if not holds:
            return False
        return not any(p.get("ValuationUseType") == m["use"] for p in root.iter(f"{M}PROPERTY"))
    m = BOTH_ARE.match(logic)
    if m:
        a = _values(root, m["a"])
        b = _values(root, m["b"])
        if not a or not b:
            return None
        return a[0] == m["x"] and b[0] == m["y"]
    m = ARCROLE.match(logic)
    if m:
        decided = False
        linked = {r.get(f"{X}to") for r in root.iter(f"{M}RELATIONSHIP") if r.get(f"{X}arcrole") == m["arc"]}
        for p in _properties(root, rule):
            if m["ante"]:
                holds = _antecedent_holds(m["ante"], root, p)
                if holds is None:
                    return None
                if not holds:
                    decided = True
                    continue
            targets = list(p.iter(f"{M}{m['t']}"))
            if not targets:
                continue
            decided = True
            hits = [t.get(f"{X}label") in linked for t in targets]
            if (not all(hits)) if m["each"] else (not any(hits)):
                return True             # "to each PROPERTY_UNIT_AREA": every one
        return False if decided else None
    m = CHILD_REQUIRED.match(logic)
    if m:
        return _child_required(root, rule, m)
    m = THERE_IS_NONE.match(logic)
    if m:
        props = _properties(root, rule) or [root]
        where = props if "PROPERTIES/PROPERTY" in (getattr(rule, "target_path", "") or "") else [root]
        return any(not any(_has(b, m["d"], m["v"]) for b in w.iter(f"{M}{m['c']}")) for w in where)
    m = TEXT_LENGTH.match(logic)
    if m:
        cats = set(re.findall(r'"(\w+)"', m["cats"]))
        limit = int(m["n"])
        found = [c for c in root.iter(f"{M}VALUATION_COMMENTARY")
                 if (c.findtext(f"{M}ValuationAnalysisCategoryType") or "").strip() in cats]
        if not found:
            return None
        return any(len((c.findtext(f"{M}ValuationCommentText") or "")) > limit for c in found)
    m = NEITHER.match(logic)
    if m:
        parties = [p for p in root.iter(f"{M}PARTY") if _has(p, "PartyRoleType", m["role"])]
        if not parties:
            return None
        return any(not _values(p, m["a"]) and not _values(p, m["b"]) for p in parties)
    m = FOR_EACH_COUNT.match(logic)
    if m:
        decided = False
        for p in _properties(root, rule):
            for o in p.iter(f"{M}{m['o']}"):
                want = _number(o.findtext(f".//{M}{m['a']}") or "")
                if want is None:
                    continue
                decided = True
                if int(want) != len(list(o.iter(f"{M}{m['c']}"))):
                    return True
        return False if decided else None
    m = BLOCK_WITHOUT.match(logic)
    if m:
        decided = False
        for p in _properties(root, rule):
            owner = _owner_of(m["a"], p)
            if not owner:
                continue
            for blk in p.iter(f"{M}{owner}"):
                if not _has_own(blk, m["a"], m["v"]):
                    continue
                decided = True
                if next(blk.iter(f"{M}{m['c']}"), None) is None:
                    return True
        return False if decided else None
    m = PURE.match(logic)
    if m and re.search(r"[=<>]", m["ante"]):
        decided = False
        for p in (_properties(root, rule) or [None]):
            holds = _antecedent_holds(m["ante"], root, p)
            if holds is None:
                return None
            decided = True
            if holds:
                return True
        return False if decided else None
    return None


def _owner_of(name: str, scope) -> str:
    """The repeating block a type value names (ImprovementType -> IMPROVEMENT)."""
    node = next(scope.iter(f"{M}{name}"), None)
    while node is not None and _local(node).endswith("_DETAIL") is False and node.getparent() is not None:
        node = node.getparent()
        if _local(node).endswith("_DETAIL"):
            break
    return _local(node.getparent()) if node is not None and node.getparent() is not None else ""


def _has_own(block, name: str, value: str) -> bool:
    detail = next((c for c in block if _local(c).endswith("_DETAIL")), None)
    return detail is not None and (detail.findtext(f"{M}{name}") or "").strip() == value


def _owner_tag(rule, child: str) -> str:
    """The block that holds the required children: the element above the
    child's plural wrapper in the rule's own xPath
    (.../STRUCTURE_COMPONENT/FOUNDATIONS/FOUNDATION -> STRUCTURE_COMPONENT)."""
    path = [x for x in (getattr(rule, "target_path", "") or getattr(rule, "path", "")).strip("/").split("/") if x]
    if child in path:
        i = path.index(child)
        for back in (2, 1):
            if i - back >= 0 and path[i - back] not in (child + "S", child + "ES"):
                return path[i - back]
    return ""


def _child_required(root, rule, m) -> bool | None:
    child, point = m["c"], m["d"]
    owner = _owner_tag(rule, child)
    decided = False
    for p in _properties(root, rule):
        owners = list(p.iter(f"{M}{owner}")) if owner else [p]
        for o in owners:
            if m["ante"]:
                holds = _antecedent_holds(m["ante"], root, o)
                if holds is None:
                    return None
                if not holds:
                    decided = True
                    continue
            decided = True
            kids = list(o.iter(f"{M}{child}"))
            if not kids or any(not (k.findtext(f".//{M}{point}") or "").strip() for k in kids):
                return True
    return False if decided else None
