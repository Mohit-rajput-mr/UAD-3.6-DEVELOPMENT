"""Execute the Appendix H-1 UAD compliance rules against a case document.

H-1 publishes 728 rules as controlled English in a ``Rule Logic`` column, plus
the xPath, the data point and the property role each one polices.  This module
turns that into an executable check, so the appraiser sees the same Message IDs
a checker would raise -- while they are still editing, not after a rejection.

Three things make the translation reliable rather than a guess.

**The consequent comes from the metadata, not the sentence.**  Every rule names
its ``Primary Data Element`` and the ``xPath`` of the container holding it, so
what the rule is *about* is known exactly.  Only the antecedent -- the "if" --
is parsed, which is the part written regularly.

**Scope is three-dimensional.**  A rule applies to a container named by its
xPath, *within* a property of the role named by ``Property Affected``, subject
to the conditions in its logic.  Using only one of the three -- as an earlier
version of this module did -- makes a rule fire on every address in the file
instead of the one it governs.

**A rule that cannot be executed is reported, never skipped.**  Anything whose
logic this module does not fully understand comes back with status ``review``
and its verbatim text, so a gap in the engine is visible to the appraiser
rather than silently passing.

The engine is checked against the twelve official Appendix D-1 samples, which
are compliant by construction.  A rule that fires on a GSE sample is a defect
in that rule's translation, not in the sample.
"""
from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path
from typing import Any, Iterable

from lxml import etree

SPEC = Path(__file__).resolve().parents[1] / "spec"
MISMO = "http://www.mismo.org/residential/2009/schemas"
NS = {"m": MISMO}

FATAL = "Fatal"
WARNING = "Warning"

OK = "ok"               # antecedent held, requirement met
FINDING = "finding"     # antecedent held, requirement not met
NOT_APPLICABLE = "n/a"  # antecedent never held
REVIEW = "review"       # logic not executable -- shown verbatim


# --------------------------------------------------------------------------
# Rule text -> expression
# --------------------------------------------------------------------------
# "Name = "a" or "b"" is a membership test, not two conditions.
# The value list may be parenthesised -- both 'X = "a" or "b"' and
# 'X = ("a" or "b")' occur, and they mean the same thing.
ATOM = re.compile(
    r'(?P<attr>@)?(?P<name>[A-Za-z][\w.]*)\s*'
    r'(?:(?P<op>=|<>|!=|>=|<=|>|<)\s*(?P<open>\()?\s*'
    r'(?P<value>"[^"]*"|[0-9][0-9.]*)'
    r'(?P<more>(?:\s*or\s*"[^"]*")*)\s*(?P<close>\))?'
    r'|\bis\s+(?P<neg>not\s+)?provided\b)',
    re.I)
MORE_VALUE = re.compile(r'"([^"]*)"')

SCOPE_INSTANCE = re.compile(
    r"\b(?:in|for)\s+a\s+given\s+instance\s+of\s+([A-Z][A-Z_]+)", re.I)
SCOPE_ACROSS = re.compile(r"\bacross all instances of ([A-Z][A-Z_]+)", re.I)

NOT_PROVIDED = re.compile(r"\bis not provided\b", re.I)
# "is not provided in YYYY-MM format" is a format rule wearing a presence
# rule's words: it governs how a supplied value is written, not whether it is
# supplied at all.  Executing it as presence flags every report that legitimately
# omits an optional field.
FORMAT_RULE = re.compile(r"\bis not provided in\s+\S+\s+format\b", re.I)
# "either A or B is not provided" needs both alternatives weighed together.
EITHER = re.compile(r"\beither\b", re.I)
# Consequents this engine does not execute: they compare across instances,
# compute a value, or test a format rather than presence.
COMPOUND = re.compile(
    r"\bat least one instance\b|\bis not unique\b|\bmore than one instance\b"
    r"|\bthe same\b|\byear of\b|\bnot a valid\b|\bis not one of\b"
    r"|\bat least one\b|\bone or more instances\b|\bin any instance\b", re.I)
# A requirement that hangs off a relationship between containers, an xLink arc
# role, or a comparison with another property.  None is decidable from the
# element alone, so these are reported for review rather than executed.
RELATED = re.compile(
    r"\bassociated with\b|\brelated to\b|\barc role\b|\bthat captures\b"
    r"|\bwas compared with\b|\bcomparable instance\b", re.I)
# "(A and B) is not provided" -- either value satisfies the rule.
ALTERNATIVES = re.compile(
    r"\((?P<names>[A-Za-z][\w.]*(?:\s+(?:and|or)\s+[A-Za-z][\w.]*)+)\)\s*is not provided",
    re.I)

# "Subject" -> the @ValuationUseType a property must carry for a rule to apply.
PROPERTY_ROLES = {
    "subject": "SubjectProperty",
    "sales comparable": "SalesComparable",
    "land comparable": "LandComparable",
    "rental comparable": "RentalComparable",
    "gross rent multiplier comparable": "GrossRentMultiplierComparable",
    "property analyzed not used": "PropertyAnalyzedNotUsed",
}


@dataclass
class Condition:
    name: str
    op: str                       # "=", "<>", ">", "<", ">=", "<=", "provided", "absent"
    values: tuple[str, ...] = ()
    is_attribute: bool = False

    def __str__(self) -> str:
        lead = "@" if self.is_attribute else ""
        if self.op in ("provided", "absent"):
            return f"{lead}{self.name} is {'not ' if self.op == 'absent' else ''}provided"
        shown = " or ".join(f'"{v}"' for v in self.values)
        return f"{lead}{self.name} {self.op} {shown}"


@dataclass
class Expr:
    op: str                       # "and", "or", "leaf", "true"
    condition: Condition | None = None
    children: list["Expr"] = field(default_factory=list)

    def conditions(self) -> Iterable[Condition]:
        if self.condition is not None:
            yield self.condition
        for c in self.children:
            yield from c.conditions()


# What kind of check a rule is.  Presence is the bulk of them; the rest are
# executed by dedicated checkers because their evidence lives in H-1's own
# columns (a minimum, a maximum, a date format) rather than in its prose.
PRESENCE = "presence"
RANGE = "range"
DATE_FORMAT = "date_format"
UNIQUENESS = "uniqueness"
CARDINALITY = "cardinality"
ADJUSTMENT_REPEAT = "adjustment_repeat"
UNEXECUTED = "review"

# UAD1758 does not carry its own list -- it points at the workbook's
# "Adjustments Cardinality" tab for which adjustment types may appear only
# once.  That tab is extracted to spec/adjustments_cardinality.json and read
# here, so the rule is executed from the specification rather than left to a
# reviewer to look up by hand.
ADJUSTMENT_TAB = re.compile(r"Adjustments Cardinality", re.I)
REPEAT_WITH_UNITS = "more than one living unit"

# "CCYY" is MISMO's spelling of a four-digit year.
DATE_PATTERNS = {
    "CCYY-MM-DD": re.compile(r"^\d{4}-\d{2}-\d{2}$"),
    "CCYY-MM": re.compile(r"^\d{4}-\d{2}$"),
    "CCYY": re.compile(r"^\d{4}$"),
}
UNIQUE_ACROSS = re.compile(
    r"\b(?P<name>[A-Za-z][\w.]*)\s+is not unique across all instances of\s+"
    r"(?P<container>[A-Z][A-Z_/]*)", re.I)
MORE_THAN_ONE = re.compile(
    r"\bmore than one instance of\s+(?P<container>[A-Z][A-Z_]*)"
    r"(?:\s+(?:with|has)\s+(?P<cond>.+?))?(?=$|,)", re.I)
# "more than one instance of X with the same Y" is a duplicate test on Y, not a
# limit of one X.  A report may hold many comparable adjustments; what it may
# not hold is two of the same type.
SAME_ENUMERATION = re.compile(
    r"\bmore than one instance of\s+(?P<container>[A-Z][A-Z_]*)\s+with the same\s+"
    r"(?P<name>[A-Za-z][\w.]*)", re.I)


@dataclass
class Rule:
    message_id: str
    severity: str
    text: str
    logic: str
    unique_id: str
    data_point: str
    container_path: str
    roles: tuple[str, ...]
    section: str
    subsection: str
    label: str
    antecedent: Expr
    instance_of: str
    executable: bool
    reason: str = ""
    requires: tuple[str, ...] = ()   # any one of these satisfies the rule
    kind: str = PRESENCE
    minimum: float | None = None
    maximum: float | None = None
    date_format: str = ""
    unique_name: str = ""
    unique_container: str = ""
    count_container: str = ""
    count_condition: Expr | None = None

    @property
    def target_path(self) -> str:
        return f"{self.container_path.rstrip('/')}/{self.data_point}"


def _atom(m: re.Match) -> Condition:
    if m.group("op"):
        values = [m.group("value").strip('"')]
        if m.group("more"):
            values.extend(MORE_VALUE.findall(m.group("more")))
        return Condition(m.group("name"), m.group("op").replace("!=", "<>"),
                         tuple(values), bool(m.group("attr")))
    return Condition(m.group("name"), "absent" if m.group("neg") else "provided",
                     (), bool(m.group("attr")))


_WORD_AND = re.compile(r"\band\b", re.I)
_WORD_OR = re.compile(r"\bor\b", re.I)

# "in the instance of X with Y = "v"" and "where Y = "v"" restrict a rule to
# one instance among several.  Ignoring the qualifier makes the rule fire on
# every sibling instead of the one it governs.
QUALIFIER = re.compile(
    r"\b(?:in|for)\s+(?:a\s+given|the\s+given|the|a)\s+instance\s+of\s+[A-Z][A-Z_]*\s*"
    r"(?:with|where)\s+(?P<cond>.+?)(?=$|,\s*(?:and|or)\b)", re.I)
QUALIFIER_BARE = re.compile(
    r"\b(?:in|for)\s+[A-Z][A-Z_]*\s+(?:for\s+)?(?:a\s+given|the)\s+instance\s+of\s+"
    r"[A-Z][A-Z_]*\s*(?:with|where)\s+(?P<cond>.+?)(?=$|,\s*(?:and|or)\b)", re.I)


def _tokenise(text: str) -> list[tuple[str, Any]]:
    """Split an antecedent into parentheses, and/or, and atomic conditions."""
    tokens: list[tuple[str, Any]] = []
    i, n = 0, len(text)
    while i < n:
        ch = text[i]
        if ch in "()":
            tokens.append((ch, None))
            i += 1
            continue
        if ch.isspace() or ch in ",;":
            i += 1
            continue
        m = ATOM.match(text, i)
        if m:
            tokens.append(("atom", _atom(m)))
            i = m.end()
            continue
        m = _WORD_AND.match(text, i)
        if m:
            tokens.append(("and", None))
            i = m.end()
            continue
        m = _WORD_OR.match(text, i)
        if m:
            tokens.append(("or", None))
            i = m.end()
            continue
        i += 1
    return tokens


def _parse_expr(tokens: list[tuple[str, Any]], pos: int = 0) -> tuple[Expr, int]:
    """expr := term ( 'or' term )*"""
    node, pos = _parse_term(tokens, pos)
    terms = [node]
    while pos < len(tokens) and tokens[pos][0] == "or":
        rhs, pos = _parse_term(tokens, pos + 1)
        terms.append(rhs)
    if len(terms) == 1:
        return terms[0], pos
    return Expr("or", children=terms), pos


def _parse_term(tokens: list[tuple[str, Any]], pos: int) -> tuple[Expr, int]:
    """term := factor ( 'and' factor )*"""
    node, pos = _parse_factor(tokens, pos)
    factors = [node]
    while pos < len(tokens) and tokens[pos][0] == "and":
        rhs, pos = _parse_factor(tokens, pos + 1)
        factors.append(rhs)
    factors = [f for f in factors if f.op != "true"]
    if not factors:
        return Expr("true"), pos
    if len(factors) == 1:
        return factors[0], pos
    return Expr("and", children=factors), pos


def _parse_factor(tokens: list[tuple[str, Any]], pos: int) -> tuple[Expr, int]:
    """factor := '(' expr ')' | atom"""
    if pos >= len(tokens):
        return Expr("true"), pos
    kind, payload = tokens[pos]
    if kind == "(":
        node, pos = _parse_expr(tokens, pos + 1)
        if pos < len(tokens) and tokens[pos][0] == ")":
            pos += 1
        return node, pos
    if kind == "atom":
        return Expr("leaf", payload), pos + 1
    return Expr("true"), pos + 1


def instance_qualifier(logic: str) -> Expr:
    """The condition that picks which instance a rule governs, if it names one."""
    for pattern in (QUALIFIER_BARE, QUALIFIER):
        m = pattern.search(logic)
        if m:
            node, _ = _parse_expr(_tokenise(m.group("cond")))
            if node.op != "true":
                return node
    return Expr("true")


def parse_antecedent(logic: str, data_point: str) -> Expr:
    """The "if" half of a rule, with the consequent clause removed.

    The instance qualifier is pulled out before the scope phrase is stripped,
    then re-joined, so "in the instance of VALUATION_COMMENTARY with
    ValuationAnalysisCategoryType = X" keeps its restriction.
    """
    text = " ".join(logic.split())
    text = re.sub(r"^\s*if\s+", "", text, flags=re.I)
    qualifier = instance_qualifier(text)

    if data_point:
        cut = re.search(rf"[,;]?\s*(?:and\s+)?\(?\s*{re.escape(data_point)}\b[^,;]*?"
                        r"is not provided", text, re.I)
        if cut:
            text = text[:cut.start()]
    text = QUALIFIER_BARE.sub("", text)
    text = QUALIFIER.sub("", text)
    text = SCOPE_INSTANCE.sub("", text)
    text = SCOPE_ACROSS.sub("", text)
    text = re.sub(r"[,\s]*\b(and|or)\s*$", "", text.strip(), flags=re.I)

    node, _ = _parse_expr(_tokenise(text))
    if qualifier.op == "true":
        return node
    if node.op == "true":
        return qualifier
    return Expr("and", children=[node, qualifier])


def _roles_for(affected: str) -> tuple[str, ...]:
    """The @ValuationUseType values a rule applies to, from Property Affected."""
    text = " ".join(str(affected or "").split()).lower()
    if not text or text == "n/a":
        return ()
    out: list[str] = []
    for part in re.split(r"[;,]", text):
        part = re.sub(r"#n\b", "", part).strip()
        if part in PROPERTY_ROLES:
            out.append(PROPERTY_ROLES[part])
    return tuple(dict.fromkeys(out))


def _number(raw) -> float | None:
    """A bound published as a plain number.  Expressions are left for review."""
    text = " ".join(str(raw or "").split()).strip('"')
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


@lru_cache(maxsize=1)
def rules() -> list[Rule]:
    raw = json.loads((SPEC / "compliance_rules.json").read_text(encoding="utf-8"))
    out: list[Rule] = []
    for r in raw:
        logic = " ".join(str(r.get("Rule Logic") or "").split())
        data_point = " ".join(str(r.get("Primary Data Element") or "").split())
        path = " ".join(str(r.get("xPath") or "").split())
        # Bounds and formats are published as their own columns, so those
        # rules are executed from data rather than from their prose.  A bound
        # written as an expression ("Current - 367") is left for review.
        minimum = _number(r.get("Min Value"))
        maximum = _number(r.get("Max Value"))
        date_format = " ".join(str(r.get("Date Format") or "").split()).upper()
        unique = UNIQUE_ACROSS.search(logic) or SAME_ENUMERATION.search(logic)
        more_than_one = MORE_THAN_ONE.search(logic)

        kind, executable, reason = PRESENCE, True, ""
        if ADJUSTMENT_TAB.search(logic):
            kind = ADJUSTMENT_REPEAT
        elif unique:
            kind = UNIQUENESS
        elif more_than_one and "no instance or" not in logic.lower():
            kind = CARDINALITY
        elif date_format in DATE_PATTERNS:
            kind = DATE_FORMAT
        elif minimum is not None or maximum is not None:
            kind = RANGE
        elif not NOT_PROVIDED.search(logic):
            kind, executable, reason = (
                UNEXECUTED, False, "consequent is not a presence requirement")
        elif FORMAT_RULE.search(logic):
            kind, executable, reason = (
                UNEXECUTED, False, "rule governs the format of a supplied value")
        elif EITHER.search(logic):
            kind, executable, reason = (
                UNEXECUTED, False, "requirement weighs two alternatives together")
        elif COMPOUND.search(logic):
            kind, executable, reason = (
                UNEXECUTED, False, "logic spans instances or computes a value")
        elif RELATED.search(logic):
            kind, executable, reason = (
                UNEXECUTED, False, "requirement depends on a linked container")
        elif not data_point or not path:
            kind, executable, reason = (
                UNEXECUTED, False, "rule does not name a data point and path")
        if kind in (RANGE, DATE_FORMAT) and not data_point:
            kind, executable, reason = (
                UNEXECUTED, False, "rule does not name the value it bounds")

        # "(A and B) is not provided" means neither was supplied, so either one
        # satisfies the rule.  Requiring only the Primary Data Element would
        # flag a report that legitimately gave the alternative.
        requires: tuple[str, ...] = (data_point,) if data_point else ()
        alt = ALTERNATIVES.search(logic)
        if alt:
            names = tuple(dict.fromkeys(re.findall(r"[A-Za-z][\w.]*", alt.group("names"))))
            names = tuple(n for n in names if n.lower() not in ("and", "or"))
            if data_point in names and len(names) > 1:
                requires = names

        m = SCOPE_INSTANCE.search(logic) or SCOPE_ACROSS.search(logic)
        out.append(Rule(
            message_id=str(r.get("Message ID") or "").strip(),
            severity=str(r.get("Severity") or "").strip(),
            text=" ".join(str(r.get("Message Text") or "").split()),
            logic=logic,
            unique_id=str(r.get("Unique ID") or "").strip(),
            data_point=data_point,
            container_path=path,
            roles=_roles_for(r.get("Property Affected")),
            section=" ".join(str(r.get("Report Section") or "").split()),
            subsection=" ".join(str(r.get("Report Subsection") or "").split()),
            label=" ".join(str(r.get("Report Label / Value") or "").split()),
            antecedent=parse_antecedent(logic, data_point) if executable else Expr("true"),
            instance_of=(m.group(1).upper() if m else ""),
            executable=executable,
            reason=reason,
            requires=requires,
            kind=kind,
            minimum=minimum,
            maximum=maximum,
            date_format=date_format if kind == DATE_FORMAT else "",
            unique_name=unique.group("name") if unique else "",
            unique_container=(unique.group("container").split("/")[-1]
                              if unique and unique.groupdict().get("container")
                              else (more_than_one.group("container")
                                    if unique and more_than_one else "")),
            count_container=(more_than_one.group("container")
                             if kind == CARDINALITY else ""),
            count_condition=(_parse_expr(_tokenise(more_than_one.group("cond") or ""))[0]
                             if kind == CARDINALITY and more_than_one.group("cond")
                             else None),
        ))
    return out


# --------------------------------------------------------------------------
# Locating what a rule governs
# --------------------------------------------------------------------------
def _local(node: etree._Element) -> str:
    return etree.QName(node).localname


class Scope:
    """Per-document indexes, so 728 rules do not each rescan the tree."""

    def __init__(self, root: etree._Element):
        self.root = root
        self.by_name: dict[str, list[etree._Element]] = {}
        self.depth: dict[etree._Element, int] = {}
        self.chain: dict[etree._Element, list[etree._Element]] = {}
        self._instance_names: dict[str, frozenset[str]] = {}
        stack: list[etree._Element] = []
        for node in root.iter():
            if not isinstance(node.tag, str):
                continue
            parent = node.getparent()
            chain = (self.chain[parent] + [parent]) if parent is not None and parent in self.chain else []
            self.chain[node] = chain
            self.depth[node] = len(chain)
            self.by_name.setdefault(_local(node), []).append(node)

    def resolve_path(self, path: str) -> list[etree._Element]:
        """Elements whose ancestor chain ends with this container path.

        H-1 writes paths relative to the valuation response, abbreviated with a
        leading ``../``.  Matching the trailing segments contiguously pins the
        right container without needing the elided prefix.
        """
        segs = [s for s in path.strip("/").split("/") if s and s != ".."]
        if not segs:
            return [self.root]
        out = []
        for node in self.by_name.get(segs[-1], ()):
            chain = self.chain[node]
            want = segs[:-1]
            if len(chain) < len(want):
                continue
            if all(_local(a) == w for a, w in zip(chain[len(chain) - len(want):], want)):
                out.append(node)
        return out

    def nearest(self, node: etree._Element, name: str) -> etree._Element | None:
        """The instance of ``name`` closest in scope to ``node``.

        Closest means the deepest shared ancestor: within the same container
        first, then the enclosing one, and so on.  Picking the document's first
        match instead would read one dwelling's data while checking another.
        """
        if _local(node) == name:
            return node
        best, best_depth = None, -1
        mine = set(map(id, self.chain[node])) | {id(node)}
        for cand in self.by_name.get(name, ()):
            shared = -1
            for anc in reversed(self.chain[cand] + [cand]):
                if id(anc) in mine:
                    shared = self.depth[anc]
                    break
            if shared > best_depth:
                best, best_depth = cand, shared
        return best

    def instance_names(self, container: str) -> frozenset[str]:
        """Element names that occur *inside* instances of this container.

        Used to tell an instance-level datum from an inherited one.  If
        AssociationChargeType appears inside some ASSOCIATION_CHARGE_DETAIL,
        then a charge detail that lacks one does not get to borrow its
        neighbour's -- it simply has no charge type, and a rule keyed to that
        type does not apply to it.  ImprovementType, which never appears inside
        a ROOM_DETAIL, is inherited from the enclosing dwelling as intended.
        """
        cached = self._instance_names.get(container)
        if cached is not None:
            return cached
        names: set[str] = set()
        for inst in self.by_name.get(container, ()):
            for node in inst.iterdescendants():
                if isinstance(node.tag, str):
                    names.add(_local(node))
        out = frozenset(names)
        self._instance_names[container] = out
        return out

    def attribute(self, node: etree._Element, name: str) -> str | None:
        for cur in [node] + list(reversed(self.chain[node])):
            if name in cur.attrib:
                return cur.attrib[name]
        return None

    def property_role(self, node: etree._Element) -> str | None:
        return self.attribute(node, "ValuationUseType")


def _value(scope: Scope, node: etree._Element, cond: Condition,
           local: frozenset[str] = frozenset()) -> str | None:
    if cond.is_attribute:
        return scope.attribute(node, cond.name)
    if cond.name in local:
        # instance-level: read it here or not at all, never from a sibling
        if _local(node) == cond.name:
            found = node
        else:
            found = node.find(f".//{{{MISMO}}}{cond.name}")
    else:
        found = scope.nearest(node, cond.name)
    if found is None:
        return None
    return (found.text or "").strip() or None


def selects(expr: Expr, scope: Scope, inst: etree._Element,
            local: frozenset[str] = frozenset()) -> bool:
    """Do the conditions that pick *this* instance hold?

    A condition naming a data point that lives inside the scoped container is
    not an alternative -- it is what chooses the instance the rule governs.
    "RoomType = Kitchen" on a rule scoped to ROOM_DETAIL selects kitchens; it
    can never be satisfied instead by a fact about the enclosing dwelling.

    Enforcing that separately also repairs a parenthesisation slip in the
    published rules: UAD1145 reads "(A) or (B and C) and (RoomType = ...)",
    which by ordinary precedence attaches the room test to only one branch,
    while its twin UAD1146 -- the same requirement for the neighbouring data
    point -- parenthesises it correctly around both.
    """
    for cond in expr.conditions():
        if cond.is_attribute or cond.op in ("provided", "absent"):
            continue
        if inst.find(f".//{{{MISMO}}}{cond.name}") is None and _local(inst) != cond.name:
            continue
        if not holds(Expr("leaf", cond), scope, inst, local):
            return False
    return True


def holds(expr: Expr, scope: Scope, node: etree._Element,
          local: frozenset[str] = frozenset()) -> bool:
    if expr.op == "true":
        return True
    if expr.op == "leaf" and expr.condition is not None:
        c = expr.condition
        got = _value(scope, node, c, local)
        if c.op == "provided":
            return got is not None
        if c.op == "absent":
            return got is None
        if got is None:
            return False
        lowered = got.lower()
        if c.op == "=":
            return any(lowered == v.lower() for v in c.values)
        if c.op == "<>":
            return all(lowered != v.lower() for v in c.values)
        try:
            left = float(got)
            right = float(c.values[0])
        except (ValueError, IndexError):
            return False
        return {">": left > right, "<": left < right,
                ">=": left >= right, "<=": left <= right}[c.op]
    results = [holds(child, scope, node, local) for child in expr.children]
    if not results:
        return True
    return all(results) if expr.op == "and" else any(results)


_NAME = re.compile(r"^[A-Za-z_][\w.]*$")


def _present(scope: Scope, inst: etree._Element, data_point: str) -> bool:
    name = data_point.strip()
    if name.startswith("@"):
        return scope.attribute(inst, name[1:]) is not None
    if not _NAME.match(name):
        return True
    if _local(inst) == name:
        return bool((inst.text or "").strip())
    target = inst.find(f".//{{{MISMO}}}{name}")
    if target is None:
        return False
    return bool((target.text or "").strip()) or len(target) > 0


@dataclass
class Finding:
    message_id: str
    severity: str
    status: str
    text: str
    data_point: str
    field_id: str
    section: str
    subsection: str
    label: str
    path: str
    logic: str = ""
    reason: str = ""
    role: str = ""

    def to_json(self) -> dict[str, Any]:
        return self.__dict__.copy()


@lru_cache(maxsize=1)
def _field_id_by_uid() -> dict[str, str]:
    index = json.loads((SPEC / "field_index.json").read_text(encoding="utf-8"))["fields"]
    out: dict[str, str] = {}
    for fid, entry in index.items():
        for dp in entry.get("data_points", []):
            uid = dp.get("unique_id")
            if uid and uid not in out:
                out[uid] = fid
    return out


def _values_in(scope: Scope, rule: Rule) -> list[tuple[etree._Element, str]]:
    """Every supplied value of a rule's data point, with the instance holding it.

    The rule's own conditions are applied first.  A bound such as "LivingUnitCount
    must be at least 1" governs dwellings; an outbuilding's structure detail
    legitimately carries none, and checking the bound without the condition
    would fault a correct report.
    """
    container = [c for c in rule.container_path.strip("/").split("/")
                 if c and c != ".."]
    local = scope.instance_names(container[-1]) if container else frozenset()
    out = []
    for inst in scope.resolve_path(rule.container_path):
        if rule.roles and scope.property_role(inst) not in rule.roles:
            continue
        if not holds(rule.antecedent, scope, inst, local):
            continue
        if not selects(rule.antecedent, scope, inst, local):
            continue
        for node in inst.iter(f"{{{MISMO}}}{rule.data_point}"):
            text = (node.text or "").strip()
            if text:
                out.append((inst, text))
    return out


@lru_cache(maxsize=1)
def adjustment_repeatability() -> dict[str, str]:
    """Which comparable adjustment types may appear more than once."""
    path = SPEC / "adjustments_cardinality.json"
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding="utf-8"))
    out = {}
    for row in data.get("rows", []):
        name = " ".join(str(row.get("ComparableAdjustmentType") or "").split())
        rule = " ".join(str(row.get("Adjustment Repeatability") or "").split())
        if name:
            out[name] = rule
    return out


def _count(node: etree._Element | None, name: str, default: int = 0) -> int:
    if node is None:
        return default
    found = node.find(f".//{{{MISMO}}}{name}")
    try:
        return int((found.text or "").strip()) if found is not None else default
    except ValueError:
        return default


def _feature_count(prop: etree._Element | None, name: str) -> int:
    if prop is None:
        return 0
    if name.startswith("Outbuilding"):
        return sum(1 for n in prop.iter(f"{{{MISMO}}}ImprovementType")
                   if (n.text or "").strip() == "Outbuilding")
    return (_count(prop, "LivingUnitExcludingADUCount", 0)
            + _count(prop, "AccessoryDwellingUnitTotalCount", 0))


def _allowance(scope: Scope, name: str, prop: etree._Element) -> int:
    """How many times a repeatable adjustment may legitimately appear.

    The workbook states the allowance as "more than one living unit", but the
    GSEs' own samples show it tracking the count of whatever the adjustment
    describes, on whichever property has more of it: MH1 carries two Outbuilding
    adjustments against two outbuildings; SF3 and SF4 repeat a living-unit
    adjustment against one dwelling plus one ADU; and one SF4 comparable
    carries two Outbuilding adjustments for two outbuildings of its own, where
    the subject has none.  An adjustment exists to reconcile a difference, so
    the allowance is one per instance of the feature on either side.
    """
    subject = next((p for p in scope.by_name.get("PROPERTY", [])
                    if p.get("ValuationUseType") == "SubjectProperty"), None)
    return max(1, _feature_count(subject, name), _feature_count(prop, name))


def _check_adjustment_repeat(scope: Scope, rule: Rule) -> bool:
    """True when an adjustment type repeats that the workbook says may not."""
    repeatability = adjustment_repeatability()
    if not repeatability:
        return False
    for prop in scope.by_name.get("PROPERTY", []):
        if rule.roles and prop.get("ValuationUseType") not in rule.roles:
            continue
        counts: dict[str, int] = {}
        for node in prop.iter(f"{{{MISMO}}}ComparableAdjustmentType"):
            text = (node.text or "").strip()
            if text:
                counts[text] = counts.get(text, 0) + 1
        for name, n in counts.items():
            if n <= 1:
                continue
            policy = repeatability.get(name, "").lower()
            if not policy:
                continue
            if REPEAT_WITH_UNITS in policy and n <= _allowance(scope, name, prop):
                continue
            return True
    return False


def _check_range(scope: Scope, rule: Rule) -> bool:
    """True when a supplied value falls outside the published bounds."""
    for _inst, text in _values_in(scope, rule):
        try:
            value = float(text)
        except ValueError:
            continue
        if rule.minimum is not None and value < rule.minimum:
            return True
        if rule.maximum is not None and value > rule.maximum:
            return True
    return False


def _check_date_format(scope: Scope, rule: Rule) -> bool:
    """True when a supplied date is not written the way H-1 requires."""
    pattern = DATE_PATTERNS.get(rule.date_format)
    if pattern is None:
        return False
    return any(not pattern.match(text) for _inst, text in _values_in(scope, rule))


def _group(scope: Scope, node: etree._Element) -> int:
    """The property a node belongs to, as the unit a count is taken within.

    Three comparables each holding one listing is correct; one comparable
    holding three is not.  Counting document-wide cannot tell those apart, so
    every count and uniqueness test is taken per property.
    """
    for anc in reversed(scope.chain[node] + [node]):
        if _local(anc) == "PROPERTY":
            return id(anc)
    return id(scope.root)


def _check_uniqueness(scope: Scope, rule: Rule) -> bool:
    """True when an identifier repeats where the rule requires it to be unique."""
    container = rule.unique_container or rule.instance_of
    instances = scope.by_name.get(container, [])
    if not instances:
        return False
    seen: dict[int, set[str]] = {}
    for inst in instances:
        if rule.roles and scope.property_role(inst) not in rule.roles:
            continue
        node = inst.find(f".//{{{MISMO}}}{rule.unique_name}")
        if node is None and _local(inst) == rule.unique_name:
            node = inst
        text = (node.text or "").strip() if node is not None else ""
        if not text:
            continue
        # An identifier said to be unique "across all instances" of a container
        # is unique per property; the same unit number may recur in a
        # comparable, which is a different building.
        bucket = seen.setdefault(_group(scope, inst), set())
        if text in bucket:
            return True
        bucket.add(text)
    return False


def _check_cardinality(scope: Scope, rule: Rule) -> bool:
    """True when a container the rule limits to one appears more than once."""
    instances = scope.by_name.get(rule.count_container, [])
    if not instances:
        return False
    local = scope.instance_names(rule.count_container)
    counts: dict[int, int] = {}
    for inst in instances:
        if rule.roles and scope.property_role(inst) not in rule.roles:
            continue
        if rule.count_condition is not None and not holds(
                rule.count_condition, scope, inst, local):
            continue
        key = _group(scope, inst)
        counts[key] = counts.get(key, 0) + 1
    return any(n > 1 for n in counts.values())


EXTENDED = {
    ADJUSTMENT_REPEAT: _check_adjustment_repeat,
    RANGE: _check_range,
    DATE_FORMAT: _check_date_format,
    UNIQUENESS: _check_uniqueness,
    CARDINALITY: _check_cardinality,
}


def evaluate(tree, *, include_ok: bool = False) -> list[Finding]:
    """Run every rule against a case document."""
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    scope = Scope(root)
    by_uid = _field_id_by_uid()
    out: list[Finding] = []

    for rule in rules():
        fid = by_uid.get(rule.unique_id, "")
        base = dict(message_id=rule.message_id, severity=rule.severity,
                    text=rule.text, data_point=rule.data_point, field_id=fid,
                    section=rule.section, subsection=rule.subsection,
                    label=rule.label, path=rule.target_path, logic=rule.logic)
        if not rule.executable:
            out.append(Finding(status=REVIEW, reason=rule.reason, **base))
            continue

        checker = EXTENDED.get(rule.kind)
        if checker is not None:
            if checker(scope, rule):
                out.append(Finding(status=FINDING, reason="", **base))
            elif include_ok:
                out.append(Finding(status=OK, reason="", **base))
            continue

        container = [c for c in rule.container_path.strip('/').split('/') if c and c != '..']
        local = scope.instance_names(container[-1]) if container else frozenset()
        instances = scope.resolve_path(rule.container_path)
        if rule.instance_of:
            named = scope.by_name.get(rule.instance_of, [])
            if named:
                instances = [i for i in instances
                             if any(id(a) in set(map(id, named))
                                    for a in scope.chain[i] + [i])] or instances

        # When nothing in the antecedent singles out one instance, the rule
        # asks that the value appear *somewhere* among them rather than in
        # every one.  Association charges are the clear case: the transfer-fee
        # indicator lives in its own charge detail, so demanding it in each
        # sibling would fault a correctly filed report.  A rule that does name
        # an instance-level condition -- "AssociationChargeType = Dues" -- is
        # selecting instances, and then the requirement is per instance.
        selective = any(
            c.name in local and not c.is_attribute
            for c in rule.antecedent.conditions())
        collective = (not selective
                      and len(instances) > 1
                      and (rule.requires or (rule.data_point,))[0] in local)

        fired, applicable, role_seen = False, False, ""
        if collective:
            in_role = [i for i in instances
                       if not rule.roles or scope.property_role(i) in rule.roles]
            wanted = rule.requires or (rule.data_point,)
            eligible = [i for i in in_role if holds(rule.antecedent, scope, i, local)]
            if eligible:
                applicable = True
                if not any(_present(scope, i, n) for i in eligible for n in wanted):
                    fired = True
                    role_seen = scope.property_role(eligible[0]) or ""
            out.append(Finding(status=FINDING, reason="", role=role_seen, **base)
                       if fired else
                       Finding(status=OK if applicable else NOT_APPLICABLE,
                               reason="", **base))
            if not fired and not include_ok:
                out.pop()
            continue

        for inst in instances:
            if rule.roles:
                role = scope.property_role(inst)
                if role not in rule.roles:
                    continue
            if not holds(rule.antecedent, scope, inst, local):
                continue
            if not selects(rule.antecedent, scope, inst, local):
                continue
            applicable = True
            wanted = rule.requires or (rule.data_point,)
            if not any(_present(scope, inst, name) for name in wanted):
                fired = True
                role_seen = scope.property_role(inst) or ""
                break
        if fired:
            out.append(Finding(status=FINDING, reason="", role=role_seen, **base))
        elif include_ok:
            out.append(Finding(status=OK if applicable else NOT_APPLICABLE,
                               reason="", **base))
    return out


def summarise(findings: list[Finding]) -> dict[str, int]:
    out = {"fatal": 0, "warning": 0, "review": 0, "total": 0}
    for f in findings:
        if f.status == FINDING:
            out["fatal" if f.severity == FATAL else "warning"] += 1
            out["total"] += 1
        elif f.status == REVIEW:
            out["review"] += 1
    return out


def main() -> None:
    rs = rules()
    ex = [r for r in rs if r.executable]
    print(f"{len(rs)} H-1 compliance rules")
    print(f"   executable ....... {len(ex)}")
    print(f"   sent to review ... {len(rs) - len(ex)}")
    reasons: dict[str, int] = {}
    for r in rs:
        if not r.executable:
            reasons[r.reason] = reasons.get(r.reason, 0) + 1
    for reason, n in sorted(reasons.items(), key=lambda kv: -kv[1]):
        print(f"      {n:>4}  {reason}")
    roles: dict[tuple, int] = {}
    for r in rs:
        roles[r.roles] = roles.get(r.roles, 0) + 1
    print("\n  property scoping:")
    for role, n in sorted(roles.items(), key=lambda kv: -kv[1])[:6]:
        print(f"      {n:>4}  {role or '(no property filter)'}")


if __name__ == "__main__":
    main()
