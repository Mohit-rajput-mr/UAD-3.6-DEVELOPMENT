"""A-1's conditionality, read as a sentence an appraiser can act on.

Appendix A-1 gives each conditionally required data point ("CR") its
condition in a small language of its own::

    IF @ValuationUseType = "SalesComparable" AND ListingStatusType = "Pending" OR "SettledSale"
    IF (ImprovementType = "Dwelling" AND Exists) OR (ImprovementType = "Outbuilding" AND ...)
    IF AddressUnitIdentifier Is Present
    IF LivingUnitExcludingADUCount > 1 OR AccessoryDwellingUnitTotalCount > 0

``OR`` followed by a quoted value continues a value list ("Pending" OR
"SettledSale"); followed by anything else it joins two conditions.

Some clauses only say which block the field sits in: the subject or a
comparable (@ValuationUseType), the borrower or the supervisor
(PartyRoleType), the service (ServiceType).  At the top level those are the
field's *scope* ("required for the Appraiser Supervisor"), not a condition
the appraiser meets.  ``Exists`` means "when there is one": the value is
optional, but required to be well-formed once given.

The field guidance panel (``GET /api/cases/{id}/guide/{fid}``) shows both.
Everything here is read from the specification text; nothing is hand-typed
per field.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field

CONTEXT = ("ValuationUseType", "PartyRoleType", "ServiceType")
_TOKEN = re.compile(r'\s*(?:(\()|(\))|"([^"]*)"|(!=|<>|>=|<=|=|>|<)|([@\w.-]+))')
_SUFFIX = re.compile(r"(Type|Indicator|Identifier|Text|Amount|Count|Date|Measure)$")


def words(name: str) -> str:
    """AddressLineText -> Address Line; ListingStatusType -> Listing Status."""
    name = name.lstrip("@")
    name = _SUFFIX.sub("", name) or name
    return re.sub(r"(?<=[a-z0-9])(?=[A-Z])|(?<=[A-Z])(?=[A-Z][a-z])", " ", name).strip()


def _value(v: str) -> str:
    return {"true": "Yes", "false": "No"}.get(v, words(v) if re.fullmatch(r"[A-Za-z0-9]+", v) else v)


@dataclass
class Node:
    op: str                       # "and", "or", or "atom"
    kids: list["Node"] = field(default_factory=list)
    text: str = ""                # the sentence, for an atom
    context: str = ""             # the block, for a context atom
    bare: str = ""                # a name alone: "A AND B Are Not Present" lists names
    presence: str = ""            # "given" / "not given", for "X Is (Not) Present"


def _tokens(text: str) -> list[tuple[str, str]]:
    out, pos = [], 0
    while pos < len(text):
        m = _TOKEN.match(text, pos)
        if not m or m.end() == pos:
            if text[pos:].strip():
                out.append(("word", text[pos:].strip()))
            break
        pos = m.end()
        lp, rp, q, op, w = m.groups()
        out.append(("(", "") if lp else (")", "") if rp else ("str", q) if q is not None
                   else ("op", op) if op else ("word", w))
    return out


class _Parser:
    def __init__(self, toks):
        self.t, self.i = toks, 0

    def peek(self, k=0):
        j = self.i + k
        return self.t[j] if j < len(self.t) else ("end", "")

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def expr(self) -> Node:
        node = self.term()
        while self.peek() in (("word", "AND"), ("word", "OR")):
            op = self.take()[1].lower()
            right = self.term()
            if node.op == op:
                node.kids.append(right)
            else:
                node = Node(op, [node, right])
        return _lists(node)

    def term(self) -> Node:
        if self.peek()[0] == "(":
            self.take()
            node = self.expr()
            if self.peek()[0] == ")":
                self.take()
            return node
        return self.atom()

    def atom(self) -> Node:
        parts = []
        while self.peek()[0] == "word" and self.peek()[1] not in ("AND", "OR"):
            parts.append(self.take()[1])
        if self.peek()[0] == "op" and parts:
            op = self.take()[1]
            values = []
            while self.peek()[0] in ("str", "word") and self.peek()[1] not in ("AND", "OR"):
                values.append(self.take()[1])
                if self.peek() == ("word", "OR") and self.peek(1)[0] == "str":
                    self.take()
                    continue
                break
            name = parts[-1].lstrip("@")
            shown = " or ".join(_value(v) for v in values)
            if name in CONTEXT and op == "=":
                each = all(v.endswith("Comparable") or v == "PropertyAnalyzedNotUsed" for v in values)
                ctx = ("each " if each else "the ") + shown
                return Node("atom", text="for " + ctx, context=ctx)
            verb = {"=": "is", "!=": "is not", "<>": "is not", ">": "is more than",
                    ">=": "is at least", "<": "is less than", "<=": "is at most"}[op]
            return Node("atom", text=f"{words(name)} {verb} {shown}")
        phrase = " ".join(parts)
        if phrase == "Exists":
            return Node("atom", text="there is one")
        m = re.fullmatch(r"(\S+) (?:Is|Are) (Not )?Present", phrase)
        if m:
            said = ("not " if m.group(2) else "") + "given"
            return Node("atom", text=f"{words(m.group(1))} is {said}", bare=m.group(1), presence=said)
        if re.fullmatch(r"[@\w]+", phrase) and phrase != phrase.lower():
            return Node("atom", text=words(phrase), bare=phrase)
        m = re.fullmatch(r"Included In (.+)", phrase)
        if m:
            return Node("atom", text=f"it is used in the {m.group(1)}")
        return Node("atom", text=phrase)


def _lists(node: Node) -> Node:
    """'A AND B AND C Are Not Present': the names before a presence test
    share it -> 'A, B and C are not given'."""
    if node.op != "and":
        return node
    kids, names = [], []
    for k in node.kids:
        if k.op == "atom" and k.bare and not k.presence:
            names.append(k.bare)
            continue
        if k.op == "atom" and k.presence and names:
            every = [words(n) for n in names + [k.bare]]
            k = Node("atom", text=f"{', '.join(every[:-1])} and {every[-1]} are {k.presence}")
            names = []
        kids += [Node("atom", text=words(n)) for n in names] + [k]
        names = []
    kids += [Node("atom", text=words(n)) for n in names]
    node.kids = kids
    return node if len(kids) > 1 else kids[0]


def parse(text: str) -> Node | None:
    t = re.sub(r"^\s*IF\s+", "", (text or "").strip())
    if not t:
        return None
    return _Parser(_tokens(t)).expr()


def _say(node: Node) -> str:
    if node.op == "atom":
        return node.text
    if node.op == "and":
        ctx = [k.context for k in node.kids if k.op == "atom" and k.context]
        rest = [_say(k) for k in node.kids if not (k.op == "atom" and k.context)]
        said = " and ".join(rest)
        return (f"for {' and '.join(ctx)}: {said}" if ctx and rest
                else f"for {' and '.join(ctx)}" if ctx else said)
    parts = [_say(k) for k in node.kids]
    return ("; or " if any(k.op == "and" for k in node.kids) else " or ").join(parts)


def read(text: str) -> tuple[str, list[str]]:
    """(condition, scope) for one A-1 conditionality text.

    The condition is a sentence to follow "when" ("" when none is left once
    the scope is taken out); the scope lists the blocks the field belongs to.
    """
    node = parse(text)
    if node is None:
        return "", []
    scope: list[str] = []
    kids = node.kids if node.op == "and" else [node]
    rest = []
    for k in kids:
        if k.op == "atom" and k.context:
            scope.append(k.context)
        else:
            rest.append(k)
    if not rest:
        return "", scope
    body = rest[0] if len(rest) == 1 else Node("and", rest)
    return _say(body), scope
