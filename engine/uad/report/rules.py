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

import json
import re
from dataclasses import dataclass
from functools import lru_cache

from lxml import etree

from .. import bind

M = f"{{{bind.MISMO}}}"

ALWAYS = re.compile(r"^\s*always\s+displays?\b", re.I)
# B-1 writes an aside after the data point -- "(UID: 3700.0002, FID: 5.000)" --
# and phrases a negative as "is a value other than 'None'".
ASIDE = re.compile(r"\((?:UID|FID)[^)]*\)")
OTHER_THAN = re.compile(r"\bis\s+(?:a\s+value\s+)?other\s+than\b", re.I)
CLAUSE = re.compile(
    r"(?P<name>[A-Za-z][\w.]*)\s*(?P<op>>=|<=|=|<>|!=|>|<|\bIs\s+Present\b|\bExists\b|\bIs\s+Not\s+Present\b)"
    # a value list's OR is followed by another quoted value; an OR followed by
    # "(" or a name joins two clauses ('= "Dwelling" or (ImprovementType = ...')
    r"\s*(?P<values>\d+(?:\.\d+)?\b|(?:\"[^\"]*\"(?:\s+OR\s+(?=\"))?)*)", re.I)
UNKNOWN = object()


@lru_cache(maxsize=1)
def vocabulary() -> frozenset[str]:
    """Every MISMO data point name the appendices define (A-1, A-2, A-3)."""
    names: set[str] = set()
    for entry in bind._index().values():
        names.update(dp.get("mismo") or "" for dp in entry.get("data_points") or [])
    folder = bind.SPEC / "report_types"
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        data = json.loads(path.read_text(encoding="utf-8"))
        for f in data.get("fields", {}).values():
            names.update(dp.get("mismo") or "" for dp in f.get("data_points") or [])
    names.discard("")
    return frozenset(names)


_SPLIT = re.compile(r"\b([A-Z][A-Za-z]+) ([a-z][A-Za-z]*)\b")


def rejoin(text: str) -> str:
    """Mend a data point name the PDF's table cell broke in two.

    B-1/B-2/B-3 print rules in narrow columns and the text layer keeps the line
    break as a space -- "ManufacturedHomeHUDDataPlateAtatchedIn dicator",
    "ValuationReportInspectionCertificat ionType" -- so the clause named a
    data point that does not exist and the rule decided on nothing.  Two words
    are joined only when together they are a name the appendices define."""
    names = vocabulary()

    def mend(m: re.Match) -> str:
        joined = m.group(1) + m.group(2)
        return joined if joined in names and m.group(1) not in names else m.group(0)
    text = _NAME.sub(lambda m: spelled(m.group(0)), _SPLIT.sub(mend, text))

    # the same break inside a quoted value: "SignificantRealPropertyApprai
    # salAssistance" is the enumeration SignificantRealPropertyAppraisalAssistance
    def mend_value(m: re.Match) -> str:
        inner = m.group(2)
        joined = inner.replace(" ", "")
        return f"{m.group(1)}{joined}{m.group(3)}" if " " in inner and joined in values() else m.group(0)
    return _QUOTED.sub(mend_value, text)


_QUOTED = re.compile(r"([\"\u201c])([A-Za-z][A-Za-z ]+[A-Za-z])([\"\u201d])")


@lru_cache(maxsize=1)
def values() -> frozenset[str]:
    """Every enumeration value the appendices define (A-1's enumerations
    sheet, which lists those that do not display too, and A-2 / A-3's)."""
    out: set[str] = set()
    sheet = bind.SPEC / "enumerations.json"
    if sheet.is_file():
        for row in json.loads(sheet.read_text(encoding="utf-8")):
            out.add(" ".join(str(row.get("Supported Enumerations") or "").split()))
    for entry in bind._index().values():
        for dp in entry.get("data_points") or []:
            out.update(e.get("value") or "" for e in dp.get("enumerations") or [])
    folder = bind.SPEC / "report_types"
    for path in sorted(folder.glob("*.json")) if folder.is_dir() else []:
        data = json.loads(path.read_text(encoding="utf-8"))
        for f in data.get("fields", {}).values():
            for dp in f.get("data_points") or []:
                out.update(e.get("value") or "" for e in dp.get("enumerations") or [])
    out.discard("")
    return frozenset(out)


_NAME = re.compile(r"\b[A-Z][a-z]+(?:[A-Z][a-z]*){3,}\b")


@lru_cache(maxsize=2048)
def spelled(name: str) -> str:
    """A data point name the guide misspells, as the appendices define it.

    B-3 writes "PersonalInspectoinPerformedIndicator" and
    "PropertyValuationConditoinalConclusionType", B-1
    "ManufacturedHomeHUDDataPlateAtatchedIndicator": a rule naming a data point
    that does not exist decides nothing.  A name is corrected only to the one
    defined name of the same length that differs from it by two swapped
    letters or a single letter -- never by a guess among several."""
    names = vocabulary()
    if name in names or len(name) < 16:
        return name
    near = [n for n in names if abs(len(n) - len(name)) <= 1 and _close(name, n)]
    return near[0] if len(near) == 1 else name


def _close(a: str, b: str) -> bool:
    if len(a) == len(b):
        diff = [i for i, (x, y) in enumerate(zip(a, b)) if x != y]
        if len(diff) == 1:
            return True
        return (len(diff) == 2 and diff[1] == diff[0] + 1
                and a[diff[0]] == b[diff[1]] and a[diff[1]] == b[diff[0]])
    short, long_ = (a, b) if len(a) < len(b) else (b, a)
    return any(long_[:i] + long_[i + 1:] == short for i in range(len(long_)))


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
    if out or scope is None:
        return out
    # Not inside this unit or structure: the name belongs to what holds it
    # (10.026 "Display when LandOwnedInCommonIndicator = true" is the
    # project's, read from inside a unit -- Condo1 prints "Non-Residential
    # Use in Unit  No").  The nearest ancestor that has it answers, never a
    # sibling unit or structure's own copy.
    for anc in scope.iterancestors():
        for node in anc.iter(f"{M}{name}"):
            if any(a.tag == scope.tag and a is not scope for a in node.iterancestors()):
                continue
            text = (node.text or "").strip()
            if text:
                out.append(text)
        if out:
            return out
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
    if op in (">", "<", ">=", "<=") and values:
        # "AccessoryDwellingUnitTotalCount > 0" (B-1 10.011): numbers compared
        try:
            bound = float(values[0])
            nums = [float(v) for v in got]
        except ValueError:
            return False
        test = {">": lambda a: a > bound, "<": lambda a: a < bound,
                ">=": lambda a: a >= bound, "<=": lambda a: a <= bound}[op]
        return any(test(n) for n in nums)
    return False


def evaluate(rule: str, root: etree._Element,
             scope: etree._Element | None = None, *, lenient: bool = False) -> Decision:
    """Run one display rule against a case.

    ``lenient`` decides on the data-point clauses alone when the sentence also
    joins prose to them ('= "FHA" and the original appraisal is for a purchase
    or refinance transaction', B-2 05.009): the AND / OR the prose leaves with
    nothing to join are dropped instead of making the rule undecidable."""
    text = rejoin(" ".join(str(rule or "").split()))
    for quote in ("‘", "’", "“", "”"):
        text = text.replace(quote, '"')
    text = OTHER_THAN.sub("<>", ASIDE.sub(" ", text))
    text = " ".join(text.split())
    if not text:
        return Decision(False, False, text)
    if ALWAYS.match(text):
        return Decision(True, True, text)
    body = re.sub(r"^\s*(display|displays|show)\s+(?:(?:descriptive|this)\s+text\s+)?(when|if)\s+", "", text, flags=re.I)
    # turn each comparison into a token, keeping the AND/OR structure
    tokens: list[str] = []
    last = 0
    for m in CLAUSE.finditer(body):
        between = body[last:m.start()]
        for word in re.findall(r"\bAND\b|\bOR\b|\(|\)", between, re.I):
            tokens.append(word.upper() if word.isalpha() else word)
        raw = m.group("values") or ""
        values = re.findall(r"\"([^\"]*)\"", raw) or ([raw.strip()] if re.match(r"^\d", raw.strip()) else [])
        tokens.append("1" if _clause(root, scope, m.group("name"), m.group("op"), values) else "0")
        last = m.end()
    for word in re.findall(r"\bAND\b|\bOR\b|\(|\)", body[last:], re.I):
        tokens.append(word.upper() if word.isalpha() else word)
    if not any(t in ("0", "1") for t in tokens):
        return Decision(False, False, text)
    if lenient:
        cleaned: list[str] = []
        for t in tokens:
            if t in ("AND", "OR") and (not cleaned or cleaned[-1] in ("AND", "OR", "(")):
                continue
            cleaned.append(t)
        while cleaned and cleaned[-1] in ("AND", "OR"):
            cleaned.pop()
        tokens = cleaned
    expr = " ".join({"AND": "and", "OR": "or"}.get(t, t) for t in tokens)
    expr = re.sub(r"^\s*(and|or)\s+|\s+(and|or)\s*$", "", expr)
    try:
        return Decision(bool(eval(expr, {"__builtins__": {}}, {})), True, text)
    except Exception:
        return Decision(False, False, text)
