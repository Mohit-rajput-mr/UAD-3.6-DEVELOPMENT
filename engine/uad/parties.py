"""Names of the parties to the assignment, written the way A-1 and B-1 define.

A party's name is either an individual's (INDIVIDUAL/NAME: FirstName,
MiddleName, LastName, SuffixName) or a legal entity's
(LEGAL_ENTITY/LEGAL_ENTITY_DETAIL/FullName) -- an XSD choice inside PARTY, so
one excludes the other.  Which party a name belongs to is its PartyRoleType
(A-1 "IF PartyRoleType = ..."), and a report may have several (two borrowers).

Current Owner of Public Record (B-1 p90-91):

* Case A -- the owner is the borrower: the borrower's PARTY gets a second ROLE
  with PartyRoleType "PropertyOwner" (no repeated party);
* Case B -- the owner is the seller: the same, on the seller's PARTY;
* Case C -- anyone else: a PARTY of its own with that role.

The editor sends one line of text per field ("Betty Borrower | Bob Borrower").
It is split here; nothing is invented.  Whether a name is a person's or a
company's is the appraiser's call (``kind``); without it, a name that reads as
an organisation ("... LLC", "... Trust") is taken as one.
"""
from __future__ import annotations

import re
from functools import lru_cache

from lxml import etree

from . import bind, edit

M = f"{{{bind.MISMO}}}"
SUFFIXES = {"jr", "jr.", "sr", "sr.", "ii", "iii", "iv", "v"}
ENTITY_WORDS = re.compile(
    r"\b(llc|l\.l\.c\.|inc\.?|corp\.?|corporation|company|co\.|trust|trustee|estate|bank|"
    r"lp|llp|ltd\.?|partnership|association|assn\.?|holdings|group|properties|fund|"
    r"church|ministries|foundation|builders|homes|realty|investments?|capital|"
    r"federal|national|credit union|mortgage|services|management|authority|"
    r"county|city of|state of|university|hud|fannie mae|freddie mac)\b", re.I)


@lru_cache(maxsize=None)
def name_role(field_id: str) -> str:
    """The PartyRoleType whose name this field shows, or '' when the field is
    not a party-name field (INDIVIDUAL/NAME under PARTIES/PARTY)."""
    try:
        binding = edit._binding_for(field_id)
    except KeyError:
        return ""
    points = [dp for dp in binding.data_points if dp.get("mismo")]
    names = [dp for dp in points if dp["mismo"] in ("FirstName", "LastName", "FullName")
             and "PARTIES/PARTY/" in dp.get("xpath", "")
             and ("PARTY/INDIVIDUAL/NAME" in dp["xpath"] or "PARTY/LEGAL_ENTITY/LEGAL_ENTITY_DETAIL" in dp["xpath"]
                  or "LEGAL_ENTITY/CONTACTS/CONTACT/NAME" in dp["xpath"])]
    if not names or len(names) != len([dp for dp in points if not dp.get("attribute")]) - \
            len([dp for dp in points if dp["mismo"] in ("MiddleName", "SuffixName")]):
        return ""
    roles = [(dp.get("requires") or {}).get("PartyRoleType") or bind.party_marks(dp).get("PartyRoleType")
             for dp in names]
    roles = [r for r in roles if r]
    if not roles:
        return ""
    if "PropertyOwner" in roles:
        return "PropertyOwner"          # 2.003 also lists the Case A / B redisplays
    return max(set(roles), key=roles.count)


@lru_cache(maxsize=None)
def is_contact(field_id: str) -> bool:
    """A contact person inside an organisation (the data collector's name)."""
    binding = edit._binding_for(field_id)
    return any("CONTACTS/CONTACT/NAME" in dp.get("xpath", "") for dp in binding.data_points)


def allows_person(field_id: str) -> bool:
    binding = edit._binding_for(field_id)
    return any(dp.get("mismo") in ("FirstName", "LastName") for dp in binding.data_points)


def allows_entity(field_id: str) -> bool:
    binding = edit._binding_for(field_id)
    return any(dp.get("mismo") == "FullName" for dp in binding.data_points)


def _roles(party: etree._Element) -> list[str]:
    return [(r.text or "").strip() for r in party.iter(f"{M}PartyRoleType")]


def parties_with(root: etree._Element, role: str) -> list[etree._Element]:
    return [p for p in root.iter(f"{M}PARTY") if role in _roles(p)]


def read_name(party: etree._Element, contact: bool = False) -> tuple[str, str]:
    """(kind, printed name) of one party."""
    if contact:
        name = party.find(f"{M}LEGAL_ENTITY/{M}CONTACTS/{M}CONTACT/{M}NAME")
        parts = [] if name is None else [(name.findtext(f"{M}{t}") or "").strip()
                                         for t in ("FirstName", "MiddleName", "LastName", "SuffixName")]
        return "person", " ".join(p for p in parts if p)
    full = party.findtext(f"{M}LEGAL_ENTITY/{M}LEGAL_ENTITY_DETAIL/{M}FullName")
    if full and full.strip():
        return "entity", full.strip()
    name = party.find(f"{M}INDIVIDUAL/{M}NAME")
    if name is None:
        return "person", ""
    parts = [(name.findtext(f"{M}{t}") or "").strip() for t in ("FirstName", "MiddleName", "LastName", "SuffixName")]
    return "person", " ".join(p for p in parts if p)


def read(root: etree._Element, field_id: str) -> tuple[str, str]:
    """(kind of the first, the names as the report prints them)."""
    role = name_role(field_id)
    found = [read_name(p, is_contact(field_id)) for p in parties_with(root, role)]
    found = [f for f in found if f[1]]
    return (found[0][0] if found else "person", " | ".join(n for _k, n in found))


def split_person(text: str) -> dict[str, str]:
    """"Betty J. Borrower Jr." -> First, Middle, Last, Suffix (A-1 lengths)."""
    tokens = text.split()
    suffix = ""
    if len(tokens) > 2 and tokens[-1].lower().rstrip(",") in SUFFIXES:
        suffix = tokens.pop().rstrip(",")
    if len(tokens) == 1:
        return {"FirstName": "", "MiddleName": "", "LastName": tokens[0][:100], "SuffixName": suffix[:4]}
    first, last = tokens[0], tokens[-1]
    middle = " ".join(tokens[1:-1])
    return {"FirstName": first[:100], "MiddleName": middle[:30], "LastName": last[:100], "SuffixName": suffix[:4]}


def guess_kind(text: str) -> str:
    return "entity" if ENTITY_WORDS.search(text or "") else "person"


def _set_name(party: etree._Element, text: str, kind: str, contact: bool = False) -> None:
    if contact:
        name, _ = edit.ensure_path(party, ["LEGAL_ENTITY", "CONTACTS", "CONTACT", "NAME"])
        _fill_person(name, text)
        return
    for rival in ("INDIVIDUAL", "LEGAL_ENTITY"):
        node = party.find(f"{M}{rival}")
        if node is not None and ((rival == "INDIVIDUAL") == (kind == "entity")):
            # an XSD choice: a party is a person or an organisation
            if rival == "LEGAL_ENTITY" and node.find(f"{M}CONTACTS") is not None:
                detail = node.find(f"{M}LEGAL_ENTITY_DETAIL")
                if detail is not None:
                    node.remove(detail)
                continue
            party.remove(node)
    if kind == "entity":
        detail, _ = edit.ensure_path(party, ["LEGAL_ENTITY", "LEGAL_ENTITY_DETAIL"])
        node = detail.find(f"{M}FullName")
        if node is None:
            node = edit.insert_ordered(detail, "FullName")
        node.text = text[:100]
        return
    name, _ = edit.ensure_path(party, ["INDIVIDUAL", "NAME"])
    _fill_person(name, text)


def _fill_person(name: etree._Element, text: str) -> None:
    for tag, value in split_person(text).items():
        node = name.find(f"{M}{tag}")
        if value:
            if node is None:
                node = edit.insert_ordered(name, tag)
            node.text = value
        elif node is not None:
            name.remove(node)


def _new_party(root: etree._Element, role: str) -> etree._Element:
    if role == "PropertyDataCollector":
        # the Property Data Report's party lives in its own SERVICE (D-1 condo 1)
        parties, _ = edit.ensure_path(edit._inspection_service(root), ["PARTIES"])
    else:
        # A report that has nobody in it yet has no PARTIES either -- blanking
        # takes the list out rather than leaving an empty one, which the schema
        # forbids.  So the list is made when the first party needs it, in the
        # SERVICE that holds the valuation.
        parties = next(root.iter(f"{M}PARTIES"), None)
        if parties is None:
            service = next((s for s in root.iter(f"{M}SERVICE")
                            if s.find(f"{M}VALUATION") is not None), None)
            if service is None:
                service = next(root.iter(f"{M}SERVICE"), None)
            if service is None:
                raise KeyError("the document has no SERVICE to put a party in")
            parties = edit.insert_ordered(service, "PARTIES")
    party = next((p for p in parties.findall(f"{M}PARTY") if not "".join(p.itertext()).strip()), None)
    if party is None:
        party = edit.insert_ordered(parties, "PARTY")
    _add_role(party, role)
    return party


def _add_role(party: etree._Element, role: str) -> None:
    if role in _roles(party):
        return
    roles, _ = edit.ensure_path(party, ["ROLES"])
    node = next((r for r in roles.findall(f"{M}ROLE") if not "".join(r.itertext()).strip()), None)
    if node is None:
        node = edit.insert_ordered(roles, "ROLE")
    detail, _ = edit.ensure_path(node, ["ROLE_DETAIL"])
    edit.insert_ordered(detail, "PartyRoleType").text = role


def _drop_role(party: etree._Element, role: str) -> None:
    """Take a role away; a party left with no role at all goes too."""
    for kind in list(party.iter(f"{M}PartyRoleType")):
        if (kind.text or "").strip() == role:
            node = kind
            while node is not None and etree.QName(node).localname != "ROLE":
                node = node.getparent()
            if node is not None:
                node.getparent().remove(node)
    if not _roles(party) and party.getparent() is not None:
        try:
            edit.remove_block(party)
        except edit.Unremovable:
            # the service's only party: the schema keeps one (SERVICE >
            # PARTIES > PARTY), so it stays as the bare instance, naming no
            # one -- the one _new_party fills next
            edit.empty_block(party)


def write(tree, field_id: str, value: str, kind: str = "") -> dict:
    """Write the names typed into a party-name field.  Returns what prints."""
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    role = name_role(field_id)
    if not role:
        raise KeyError(f"{field_id} is not a party name field")
    names = [n.strip() for n in re.split(r"\s*\|\s*|\n", value or "") if n.strip()]
    if kind not in ("person", "entity"):
        kind = ""
    if not allows_entity(field_id) or is_contact(field_id):
        kind = "person"
    elif not allows_person(field_id):
        kind = "entity"                  # "Company Name": FullName is all A-1 gives it

    if role == "PropertyOwner":
        # Case A / B: the owner is the borrower or the seller already on file
        for other in ("Borrower", "PropertySeller"):
            others = parties_with(root, other)
            shown = [read_name(p)[1] for p in others]
            if names and shown and [n.casefold() for n in names] == [s.casefold() for s in shown]:
                for party in parties_with(root, role):
                    if party not in others:
                        _drop_role(party, role)
                for party in others:
                    _add_role(party, role)
                return {"kind": read_name(others[0])[0], "value": " | ".join(shown),
                        "case": "A" if other == "Borrower" else "B"}
        # Case C: parties of their own -- never rename the borrower or seller
        existing = [p for p in parties_with(root, role)
                    if not ({"Borrower", "PropertySeller"} & set(_roles(p)))]
        for party in parties_with(root, role):
            if party not in existing:
                _drop_role(party, role)
    else:
        existing = parties_with(root, role)

    for i, text in enumerate(names):
        party = existing[i] if i < len(existing) else _new_party(root, role)
        _set_name(party, text, kind or guess_kind(text), is_contact(field_id))
    for party in existing[len(names):]:
        _drop_role(party, role)
    kind_now, shown = read(root, field_id)
    return {"kind": kind_now, "value": shown, "case": "C" if role == "PropertyOwner" else ""}
