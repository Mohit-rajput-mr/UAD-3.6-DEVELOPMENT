"""When a comparable-grid cell with nothing in it prints an em-dash.

Appendix B-1's supplement gives every grid row two sentences, "Display Em-Dash
for Subject when ..." and "... for Comp when ..." (``supplements.json``,
``b1_em_dashes``).  A cell with nothing in it is blank unless its sentence
holds -- most rows say "Never display dash".  Printing a dash in every empty
cell, as the grid did, printed two to six times the dashes the D-1 samples do.

The sentences are executed, not guessed at.  The forms B-1 actually uses:

* ``Never display dash`` (or nothing): blank.
* ``<data point> = "A" [OR "B"]``, ``<>``, ``> n``, ``= n`` -- read in the
  property the cell belongs to (the subject, or that comparable).
* ``an instance of <data point> = "A" is not provided``.
* ``<A> = "x" for all instances of <B> = "y"``.
* ``Subject does not have <X> on the row and one or more Comps does`` and
  ``Comp does not have <X> on the row and Subject or another Comp does`` --
  about the row's other cells, not the data.
* those joined by AND / OR, with parentheses.

A sentence not of those forms ("Display em-dash for ... when ...") decides
nothing, and the cell stays blank.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

from lxml import etree

from .. import bind

M = f"{{{bind.MISMO}}}"

ASIDE = re.compile(r"\((?:UID|FID)[^)]*\)")
NEVER = re.compile(r"^\s*never\s+display\s+dash", re.I)

TOKEN = re.compile(r"""
    (?P<prose>(?:Subject|Comp)\s+does\s+not\s+have\s+[\w\s]+?\s+on\s+(?:the\s+)?row,?\s+and\s+
        (?:one\s+or\s+more\s+Comps|Subject\s+or\s+another\s+Comp)\s+does\.?)
  | (?P<forall>(?P<fa>\w+)\s*=\s*"(?P<fav>[^"]*)"\s+for\s+all\s+instances\s+of\s+
        (?P<fn>\w+)\s*=\s*"(?P<fv>[^"]*)")
  | (?P<absent>an\s+instance\s+of\s+(?P<an>\w+)\s*=\s*"(?P<av>[^"]*)"\s+is\s+not\s+provided)
  | (?P<num>(?P<nn>[A-Za-z]\w*)\s*(?P<nop>>=|<=|>|<|=)\s*(?P<nv>\d+(?:\.\d+)?)(?![\d"]))
  | (?P<cmp>(?P<cn>[A-Za-z]\w*)\s*(?P<cop><>|!=|=)\s*(?P<cv>"[^"]*"(?:\s*(?:,\s*)?(?:or\s+)?"[^"]*")*))
  | (?P<word>\bAND\b|\bOR\b|[()])
""", re.I | re.X)


@dataclass
class Cell:
    """What a decision needs to know about the cell and its row."""
    root: etree._Element
    scope: etree._Element | None
    is_subject: bool
    empty_cells: list[bool]          # row-wide: [subject, comp 1, comp 2, ...]
    index: int                       # this cell's place in empty_cells


def _norm(value: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(value).casefold())


def _values(cell: Cell, name: str) -> list[str]:
    base = cell.scope if cell.scope is not None else cell.root
    return [(n.text or "").strip() for n in base.iter(f"{M}{name}") if (n.text or "").strip()]


def _compare(got: list[str], op: str, wanted: list[str]) -> bool:
    keys = {_norm(w) for w in wanted}
    if op == "=":
        return any(_norm(g) in keys for g in got)
    # <> : a data point that is not there is not that value either -- a pending
    # listing has no OwnershipTransferTransactionType, and "<> Sale" is why
    # D-1 prints a dash in its Sale Price
    return all(_norm(g) not in keys for g in got)


def _number(got: list[str], op: str, limit: float) -> bool:
    for text in got:
        try:
            value = float(text)
        except ValueError:
            continue
        if {"=": value == limit, ">": value > limit, "<": value < limit,
            ">=": value >= limit, "<=": value <= limit}[op]:
            return True
    return False


def _row_clause(cell: Cell, text: str) -> bool:
    """"Subject does not have X on the row and one or more Comps does." """
    mine_empty = cell.empty_cells[cell.index]
    others = [e for i, e in enumerate(cell.empty_cells) if i != cell.index]
    if text.casefold().startswith("subject"):
        return mine_empty and any(not e for e in others)
    return mine_empty and any(not e for e in others)       # a comp: subject or another comp has it


def _instances(cell: Cell, name: str, value: str) -> list[etree._Element]:
    base = cell.scope if cell.scope is not None else cell.root
    return [n for n in base.iter(f"{M}{name}") if _norm(n.text or "") == _norm(value)]


def _for_all(cell: Cell, m: re.Match) -> bool:
    """"PrivateAccessIndicator = "false" for all instances of
    SiteInfluenceType = "BodyOfWater"" -- true when there is such an instance
    and every one of them has that value."""
    hits = _instances(cell, m["fn"], m["fv"])
    if not hits:
        return False
    for node in hits:
        block = node.getparent()
        got = block.findtext(f"{M}{m['fa']}") if block is not None else None
        if got is None or _norm(got) != _norm(m["fav"]):
            return False
    return True


def decide(rule: str, cell: Cell) -> bool:
    """Does this row's sentence call for a dash in this (empty) cell?"""
    text = " ".join(ASIDE.sub(" ", str(rule or "")).split())
    for quote in ("‘", "’", "“", "”"):
        text = text.replace(quote, '"')
    text = text.lstrip('"')
    if not text or NEVER.match(text):
        return False
    tokens: list[str] = []
    for m in TOKEN.finditer(text):
        kind = m.lastgroup
        if m["prose"]:
            tokens.append("1" if _row_clause(cell, m["prose"]) else "0")
        elif m["forall"]:
            tokens.append("1" if _for_all(cell, m) else "0")
        elif m["absent"]:
            tokens.append("0" if _instances(cell, m["an"], m["av"]) else "1")
        elif m["num"]:
            tokens.append("1" if _number(_values(cell, m["nn"]), m["nop"], float(m["nv"])) else "0")
        elif m["cmp"]:
            wanted = re.findall(r'"([^"]*)"', m["cv"])
            tokens.append("1" if _compare(_values(cell, m["cn"]), m["cop"].replace("!=", "<>"), wanted) else "0")
        elif m["word"]:
            tokens.append(m["word"].lower() if m["word"].isalpha() else m["word"])
    if not any(t in ("0", "1") for t in tokens):
        return False
    expr = " ".join(tokens)
    expr = re.sub(r"^\s*(and|or)\s+|\s+(and|or)\s*$", "", expr)
    try:
        return bool(eval(expr, {"__builtins__": {}}, {}))
    except Exception:
        return False
