"""Decide whether a conditional element prints, from its own display rule.

Appendix B-1 states each conditional element's rule as a sentence over MISMO
data points -- ``Display when GovernmentAgencyAppraisalType = "FHA" AND
ValuationAssignmentType = "Purchase" OR "Refinance"`` -- and ``engine/spec/
display_rules.json`` carries them field by field.  The fixed text of the
Certifications and Scope of Work pages is chosen entirely by these rules, so
they are read and executed rather than guessed at.

Only the forms B-1 actually uses are executed:

* ``Always displays``
* ``Display when <data point> = "A" [OR "B" ...]``
* ``... <> "A"``,  ``... Is Present`` / ``Exists``
* clauses joined by AND / OR, with AND binding tighter, and parentheses.

Anything else is reported as undecidable, and the caller decides what to do
with it rather than being told the element displays.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

from .. import bind

M = f"{{{bind.MISMO}}}"

ALWAYS = re.compile(r"^\s*always\s+displays?\b", re.I)
# B-1 writes an aside after the data point -- "(UID: 3700.0002, FID: 5.000)" --
# and phrases a negative as "is a value other than 'None'".
ASIDE = re.compile(r"\((?:UID|FID)[^)]*\)")
OTHER_THAN = re.compile(r"\bis\s+(?:a\s+value\s+)?other\s+than\b", re.I)
CLAUSE = re.compile(
    r"(?P<name>[A-Za-z][\w.]*)\s*(?P<op>=|<>|!=|\bIs\s+Present\b|\bExists\b|\bIs\s+Not\s+Present\b)"
    r"\s*(?P<values>(?:\"[^\"]*\"(?:\s+OR\s+)?)*)", re.I)
UNKNOWN = object()


@dataclass
class Decision:
    shown: bool
    known: bool
    rule: str = ""

    def __bool__(self) -> bool:
        return self.shown


def values_of(root: etree._Element, name: str,
              scope: etree._Element | None = None) -> list[str]:
    base = scope if scope is not None else root
    out = []
    for node in base.iter(f"{M}{name}"):
        text = (node.text or "").strip()
        if text:
            out.append(text)
    return out


def _clause(root, scope, name: str, op: str, values: list[str]) -> bool:
    got = values_of(root, name, scope)
    op = " ".join(op.split()).casefold()
    if op in ("is present", "exists"):
        return bool(got)
    if op == "is not present":
        return not got
    if op == "=":
        return any(v in values for v in got)
    if op in ("<>", "!="):
        return bool(got) and all(v not in values for v in got)
    return False


def evaluate(rule: str, root: etree._Element,
             scope: etree._Element | None = None) -> Decision:
    """Run one display rule against a case."""
    text = " ".join(str(rule or "").split())
    for quote in ("‘", "’", "“", "”"):
        text = text.replace(quote, '"')
    text = OTHER_THAN.sub("<>", ASIDE.sub(" ", text))
    text = " ".join(text.split())
    if not text:
        return Decision(False, False, text)
    if ALWAYS.match(text):
        return Decision(True, True, text)
    body = re.sub(r"^\s*(display|displays|show)\s+(when|if)\s+", "", text, flags=re.I)
    # turn each comparison into a token, keeping the AND/OR structure
    tokens: list[str] = []
    last = 0
    for m in CLAUSE.finditer(body):
        between = body[last:m.start()]
        for word in re.findall(r"\bAND\b|\bOR\b|\(|\)", between, re.I):
            tokens.append(word.upper() if word.isalpha() else word)
        values = re.findall(r"\"([^\"]*)\"", m.group("values") or "")
        tokens.append("1" if _clause(root, scope, m.group("name"), m.group("op"), values) else "0")
        last = m.end()
    for word in re.findall(r"\bAND\b|\bOR\b|\(|\)", body[last:], re.I):
        tokens.append(word.upper() if word.isalpha() else word)
    if not any(t in ("0", "1") for t in tokens):
        return Decision(False, False, text)
    expr = " ".join({"AND": "and", "OR": "or"}.get(t, t) for t in tokens)
    expr = re.sub(r"^\s*(and|or)\s+|\s+(and|or)\s*$", "", expr)
    try:
        return Decision(bool(eval(expr, {"__builtins__": {}}, {})), True, text)
    except Exception:
        return Decision(False, False, text)
