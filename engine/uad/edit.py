"""Write a value back into the case document, in the schema's own order.

Editing a MISMO document is not the same as setting a key.  The element may not
exist yet, its parent containers may not exist either, and when they are
created they have to be inserted where the XSD's ``xs:sequence`` says -- a
container whose children are in the wrong order fails validation even though
every value in it is correct.

So a write walks the data point's xPath, creating what is missing, and inserts
each new element at the position the schema gives.  The result is a document
that still validates after every keystroke, which is what lets the editor show
a live schema check rather than one at the end.
"""
from __future__ import annotations

import re

from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from lxml import etree

from . import bind, entry, xsd_order

MISMO = bind.MISMO
QN = f"{{{MISMO}}}"


@dataclass
class Written:
    field_id: str
    data_point: str
    path: str
    old: str
    new: str
    created: list[str]

    def to_json(self) -> dict[str, Any]:
        return self.__dict__.copy()


def _order_of(parent_tag: str) -> dict[str, int]:
    """The XSD's declared child order for a container."""
    return xsd_order.load().table.get(parent_tag, {})


def insert_ordered(parent: etree._Element, tag: str) -> etree._Element:
    """Add a child in the position the XSD declares for it, with the
    containers its XSD sequence requires (an APPRAISER gets its
    APPRAISER_DETAIL), so a new block is never invalid for want of one."""
    node = _insert_ordered(parent, tag)
    if tag.isupper():
        for child in xsd_order.required(tag):
            if child.isupper() and node.find(f"{QN}{child}") is None:
                insert_ordered(node, child)
    return node


def _insert_ordered(parent: etree._Element, tag: str) -> etree._Element:
    return place(parent, etree.SubElement(parent, f"{QN}{tag}"))


def place(parent: etree._Element, node: etree._Element) -> etree._Element:
    """Put an element (new, moved or copied) into ``parent`` where the XSD's
    sequence puts it: after its own kind, before what the sequence lists
    later.  ``append`` puts it last -- after an EXTENSION, say, which the
    sequence always puts last -- and the schema refuses the document."""
    if node.getparent() is not None:
        node.getparent().remove(node)
    order = _order_of(etree.QName(parent).localname)
    rank = order.get(etree.QName(node).localname) if order else None
    if rank is not None:
        for i, sibling in enumerate(parent):
            if not isinstance(sibling.tag, str):
                continue
            other = order.get(etree.QName(sibling).localname)
            if other is not None and other > rank:
                parent.insert(i, node)
                return node
    parent.append(node)
    return node


def add_instance(parent: etree._Element, tag: str) -> etree._Element:
    """Another instance of a repeating block, where the XSD puts it.

    A holder made by ``insert_ordered`` comes with the instance its schema
    requires (ROOMS with a ROOM), so appending a second one beside it -- or
    appending at all, after an EXTENSION the sequence puts last -- left an
    empty phantom row next to every first room, flooring or amenity added.
    An empty, unlabelled instance already standing is that instance."""
    fresh = next((x for x in parent.findall(f"{QN}{tag}")
                  if not x.attrib and not "".join(x.itertext()).strip()), None)
    return fresh if fresh is not None else insert_ordered(parent, tag)


def adopt(parent: etree._Element, node: etree._Element) -> etree._Element:
    """Move or copy an existing block into ``parent``, in schema order --
    in place of the empty, unlabelled instance of its kind the holder was
    created with, when there is one (``add_instance``'s rule)."""
    tag = etree.QName(node).localname
    fresh = next((x for x in parent.findall(f"{QN}{tag}")
                  if x is not node and not x.attrib and not "".join(x.itertext()).strip()), None)
    if fresh is None:
        return place(parent, node)
    if node.getparent() is not None:
        node.getparent().remove(node)
    parent.replace(fresh, node)
    return node


class Unremovable(ValueError):
    """A block the schema needs where it is, inside a holder that still holds
    an answer: taking it out would leave the document invalid."""


def remove_block(node: etree._Element) -> list[etree._Element]:
    """Take a block out of the document, with every holder the schema no
    longer lets stand without it.  Returns what was removed, innermost first.

    MISMO nests a repeat inside wrappers that must each hold one of the next
    (GSE subschema): PROPERTY_AMENITY > AMENITY_CATEGORIES > AMENITY_CATEGORY
    > AMENITIES > AMENITY, every one minOccurs 1.  The removers here took the
    block out and its holder with it when the holder was left empty -- so the
    last amenity of a category went with its AMENITIES and left the
    AMENITY_CATEGORY holding only its AMENITY_CATEGORY_DETAIL, which the
    schema refuses ("AMENITY_CATEGORY_DETAIL is not expected. Expected is
    AMENITIES", T-509, owner screenshot 04).

    So the walk goes on up: a holder left empty, or with fewer of a child
    than its XSD sequence requires (``xsd_order.min_occurs``: one, or the
    three MARKET_INVENTORY of a MARKET_INVENTORIES), goes too -- the category
    with its last amenity, the category list with its last category -- until
    one can stand.  A holder
    that still holds an answer (anything but the type values that only say
    which block it is, ``templates.structure_elements``), that a relationship
    points at, or that the document is made of (the property, the service,
    the deal: ``bind.DOCUMENT_SINGLETONS``) is never discarded to make room:
    the removal is refused with ``Unremovable`` and nothing is changed.
    """
    doomed = removal_plan(node)
    top = doomed[-1]
    top.getparent().remove(top)
    return doomed


def removal_plan(node: etree._Element) -> list[etree._Element]:
    """What ``remove_block`` would take out, innermost first, without taking
    anything: the last element is the one actually detached.  Raises
    ``Unremovable`` where the removal would leave the document invalid."""
    parent = node.getparent()
    if parent is None:
        raise Unremovable("that block is the document itself")
    doomed = [node]
    child = node
    while True:
        name, tag = etree.QName(child).localname, etree.QName(parent).localname
        left = [c for c in parent if isinstance(c.tag, str) and c is not child]
        need = xsd_order.min_occurs(tag, name)
        lacks = sum(1 for c in left if etree.QName(c).localname == name) < need
        empty = not left and not (parent.text or "").strip()
        if not (lacks or empty):
            break
        if (parent.getparent() is None or tag in bind.DOCUMENT_SINGLETONS
                or _holds_answer(parent, child) or _linked(parent)):
            if lacks:
                raise Unremovable(
                    f"The {tag.replace('_', ' ').lower()} must keep "
                    f"{'at least one' if need == 1 else need} "
                    f"{name.replace('_', ' ').lower()}, so this one cannot be removed.")
            break
        doomed.append(parent)
        child, parent = parent, parent.getparent()
    return doomed


def empty_block(node: etree._Element) -> etree._Element:
    """Reduce a block the schema will not let go (the only PARTY of a
    SERVICE) to the bare instance its XSD sequence requires -- a PARTY with a
    ROLE that names no one, the shape a blank report starts with."""
    for child in list(node):
        node.remove(child)
    node.text = None
    for child in xsd_order.required(etree.QName(node).localname):
        if child.isupper():
            insert_ordered(node, child)
    return node


def _holds_answer(holder: etree._Element, besides: etree._Element) -> bool:
    """Does anything in ``holder``, outside ``besides``, carry a value other
    than a type that only says which block it is?"""
    from . import templates                       # circular at module level
    keep = templates.structure_elements()
    for child in holder:
        if not isinstance(child.tag, str) or child is besides:
            continue
        if len(child):
            if _holds_answer(child, besides):
                return True
        elif (child.text or "").strip() and etree.QName(child).localname not in keep:
            return True
    return False


def _linked(node: etree._Element) -> bool:
    """Does a relationship point at this element?"""
    label = node.get(f"{XL}label")
    if not label:
        return False
    return any(label in (rel.get(f"{XL}from"), rel.get(f"{XL}to"))
               for rel in node.getroottree().getroot().iter(f"{QN}RELATIONSHIP"))


def _continues_through(node: etree._Element, tag: str, rest: list[str]) -> etree._Element | None:
    """Which of several same-named children this path carries on through.

    A container can appear more than once and mean different things each time.
    Condo1 and Coop1 have two SERVICEs: one is the inspection, the other holds
    the VALUATION and everything the report is made of.  Taking the first --
    which is what ``find`` does -- put the whole valuation inside the
    inspection service, and the document stopped validating on the first field
    written to a condominium that the template had not already created.

    The right one is the one the rest of the path already runs through, so the
    candidates are scored by how much of what follows they can already
    account for.  With nothing to tell them apart the first still wins, which
    is the old behaviour and right for the single-SERVICE case.
    """
    kids = node.findall(f"{QN}{tag}")
    if len(kids) < 2:
        return kids[0] if kids else None

    def depth(kid: etree._Element) -> int:
        here, found = kid, 0
        for step in rest:
            nxt = here.find(f"{QN}{step}")
            if nxt is None:
                break
            here, found = nxt, found + 1
        return found

    best = max(kids, key=depth)
    return best if depth(best) else kids[0]


def ensure_path(root: etree._Element, segments: list[str]) -> tuple[etree._Element, list[str]]:
    """Walk, creating what is missing, and report what had to be created."""
    node = root
    created: list[str] = []
    for n, tag in enumerate(segments):
        found = _continues_through(node, tag, segments[n + 1:])
        if found is None:
            found = insert_ordered(node, tag)
            created.append(tag)
        node = found
    return node, created


def _segments(xpath: str) -> list[str]:
    out = [s for s in xpath.strip("/").split("/") if s]
    if out and out[0] == "MESSAGE":
        out = out[1:]
    return out


def choose_data_point(binding: bind.Binding, data_point: str = "") -> dict:
    """Which of a field's data points a plain value belongs in.

    Most fields have one.  Where a field pairs an indicator with an
    enumeration, an explicit name settles it; otherwise the enumerated one wins,
    because that is what the page prints.
    """
    points = [dp for dp in binding.data_points if dp.get("mismo")]
    if not points:
        raise KeyError(f"{binding.field_id} has no MISMO data point to write to")
    if data_point:
        for dp in points:
            if dp["mismo"] == data_point:
                return dp
        raise KeyError(f"{data_point} is not a data point of {binding.field_id}")
    # An address is not a choice: its one enumerated part is the unit
    # designator, which can only hold "Unit".  A plain value typed into an
    # address is the street line (or, whole, see split_address).
    if is_address(binding):
        return next(dp for dp in points if dp["mismo"] == "AddressLineText")
    for dp in points:
        if (dp.get("format_type") or "").casefold() == "enumerated":
            return dp
    return points[0]


ADDRESS_PARTS = ("AddressLineText", "CityName", "StateCode", "PostalCode")


def is_address(binding: bind.Binding) -> bool:
    """A field that prints a whole postal address from its parts."""
    names = {dp.get("mismo") for dp in binding.data_points}
    return all(n in names for n in ADDRESS_PARTS)


_STATE_ZIP = re.compile(r"[,\s]+([A-Za-z]{2})\.?\s+(\d{5})(?:-?(\d{4}))?\s*$")
_UNIT = re.compile(r"[,\s]+(?:#|unit|apt\.?|apartment|suite|ste\.?|room|rm\.?|no\.)\s*#?\s*"
                   r"([A-Za-z0-9][A-Za-z0-9-]*)\s*$", re.I)


def split_address(text: str, binding: bind.Binding) -> dict[str, str] | None:
    """A whole address typed into one field, as the parts A-1 stores.

    "186 8th St # 2B, Brooklyn, NY 11215" -> street "186 8th St", unit "2B",
    city "Brooklyn", state "NY", ZIP "11215".  The unit's designator is the
    one the specification allows for AddressUnitDesignatorType (A-1 lists
    "Unit" alone), so "#", "Apt" and "Suite" are stored as that and the
    identifier is kept.  None when the text is not a whole address (no city,
    state and ZIP), so the caller treats it as the street line alone.
    """
    t = " ".join((text or "").split()).strip(" ,")
    m = _STATE_ZIP.search(" " + t)
    if not m or "," not in t[:max(0, m.start() - 1)]:
        return None
    state, zip5, plus4 = m.group(1).upper(), m.group(2), m.group(3)
    rest = t[:m.start() - 1].strip(" ,")
    head, _, city = rest.rpartition(",")
    head, city = head.strip(" ,"), city.strip()
    if not head or not city:
        return None
    street, unit = head, ""
    u = _UNIT.search(" " + head.replace(",", " "))
    if u:
        unit = u.group(1)
        street = (" " + head.replace(",", " "))[:u.start()].strip(" ,")
    designator = ""
    if unit:
        point = next((dp for dp in binding.data_points
                      if dp.get("mismo") == "AddressUnitDesignatorType"), {})
        allowed = [o.get("value") for o in point.get("enumerations", []) if o.get("value")]
        designator = "Unit" if "Unit" in allowed or not allowed else allowed[0]
    names = {dp.get("mismo") for dp in binding.data_points}
    out = {"AddressLineText": street, "CityName": city, "StateCode": state,
           "PostalCode": f"{zip5}-{plus4}" if plus4 else zip5}
    if "AddressUnitIdentifier" in names:
        out["AddressUnitIdentifier"] = unit
    if "AddressUnitDesignatorType" in names:
        out["AddressUnitDesignatorType"] = designator
    return out


def _is_it_this(dp: dict, binding: bind.Binding, value: str, current: str) -> str:
    """A Yes or No against a row that names one of the field's own values.

    C-1 asks Condominium, Cooperative and Condop as three Yes/No rows; A-1
    stores the answer once, as ProjectLegalStructureType.  So a tick means a
    value: Yes on the Condominium row is "Condominium", and No clears it only
    if it was Condominium -- No on Condominium says nothing when the project is
    a Cooperative.  Storing the tick itself put "true" into an enumeration, the
    schema refused it, and the question could not be answered at all.
    """
    if (dp.get("format_type") or "").strip().casefold() != "enumerated":
        return value
    answer = (value or "").strip().casefold()
    if answer not in ("true", "false"):
        return value
    label = (binding.label or "").strip().casefold()
    this = next((o["value"] for o in dp.get("enumerations") or []
                 if o.get("value") and label in (o["value"].casefold(),
                                                (o.get("display") or "").strip().casefold())),
                "")
    if not this:
        return value
    if answer == "true":
        return this
    return "" if current == this else current


def _client_second_role(root: etree._Element, *, create: bool = False):
    """The client party's own second role -- Attorney, Lender, whatever it is
    beside "Client" -- distinct from the ROLE that names the party Client at
    all.

    A-1 marks 2.010/2.011 with the Additional Context "Clients", which reads
    as "the field belongs to the Client party" -- correct for finding *which*
    party, and wrong for finding *which of its two roles* to write, because
    the field's own value never equals "Client".  Scoping the write to "the
    ROLE_DETAIL that already says Client" makes the field try to overwrite the
    very anchor it was found by: a value written there is unreadable by the
    same rule that located it, so a re-read never finds what was just saved.
    """
    for party in root.iter(f"{QN}PARTY"):
        details = list(party.iter(f"{QN}ROLE_DETAIL"))
        kinds = [(d, (d.findtext(f"{QN}PartyRoleType") or "").strip()) for d in details]
        if not any(k == "Client" for _d, k in kinds):
            continue
        other = next((d for d, k in kinds if k and k != "Client"), None)
        if other is not None or not create:
            return other
        # lxml's __bool__ is "has children", not "is not None" -- an
        # existing but empty ROLES element would read as falsy here.
        roles = party.find(f"{QN}ROLES")
        if roles is None:
            roles = ensure_path(party, ["ROLES"])[0]
        role = insert_ordered(roles, "ROLE")
        return insert_ordered(role, "ROLE_DETAIL")
    return None


def read_client_role(root: etree._Element) -> str:
    """The client party's own second role, as it reads back after a write.

    ``bind.locate`` cannot answer this: the ordinary read is scoped by "the
    ROLE_DETAIL that says Client", which is the anchor this field is found
    by, not the value it holds -- so a caller checking a write against it
    would see the anchor and conclude the write had failed.
    """
    detail = _client_second_role(root)
    return (detail.findtext(f"{QN}PartyRoleType") or "").strip() if detail is not None else ""


def _write_client_role(tree, field_id: str, value: str, binding: bind.Binding,
                       data_point: str) -> "Written":
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    dp = choose_data_point(binding, data_point)
    leaf_tag = dp["mismo"]
    detail = _client_second_role(root, create=bool(value.strip()))
    if detail is None:
        return Written(field_id, leaf_tag, dp.get("xpath", ""), "", "", [])
    leaf = detail.find(f"{QN}{leaf_tag}")
    old = (leaf.text or "").strip() if leaf is not None else ""
    text, _unit = entry.normalize(dp, value, "")
    if not text:
        if leaf is not None:
            detail.remove(leaf)
        # a role with nothing in it now is not a role
        if not any((c.text or "").strip() for c in detail):
            role = detail.getparent()
            role.getparent().remove(role)
    else:
        if leaf is None:
            leaf = insert_ordered(detail, leaf_tag)
        leaf.text = text
        if leaf_tag == "PartyRoleType" and text != "Other":
            other_desc = detail.find(f"{QN}PartyRoleTypeOtherDescription")
            if other_desc is not None:
                detail.remove(other_desc)
    return Written(field_id=field_id, data_point=leaf_tag, path=dp.get("xpath", ""),
                   old=old, new=text, created=[])


def write(tree, field_id: str, value: str, *, data_point: str = "",
          ordinal: int = 1, binding: bind.Binding | None = None,
          scope: etree._Element | None = None) -> Written:
    """Set one field's value, creating whatever the path needs.

    ``scope`` names the element the value belongs inside -- a comparable's
    PROPERTY, say.  Without it a data point under a PROPERTY is taken to be the
    subject's, which is right for the form and wrong for every cell of the
    comparable grid.
    """
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    if binding is None:
        binding = _binding_for(field_id)
    if field_id in ("2.010", "2.011"):
        return _write_client_role(tree, field_id, value, binding, data_point)
    days = [d for d in binding.data_points if d.get("mismo") and not d.get("attribute")]
    if (not data_point and len(days) > 1
            and all(d["mismo"].endswith("DaysCount") for d in days)
            and any("LowRange" in d["mismo"] for d in days)):
        return _write_days(tree, field_id, value, binding, days, ordinal, scope)
    dp = choose_data_point(binding, data_point)
    if "DATA_SOURCES/DATA_SOURCE" in dp.get("xpath", ""):
        # a source tied by arcrole to what it sources (Area Data Source to the
        # unit's area, 10.009): written with its link (uad/sources.py)
        from .report import form as _form
        target = _form.data_source_target(field_id)
        if target and target != "PROPERTY":
            from . import sources
            old, new = sources.write(root, target, dp["mismo"], value.strip(), scope)
            return Written(field_id=field_id, data_point=dp["mismo"], path=dp.get("xpath", ""),
                           old=old, new=new, created=[])
    if not data_point:
        # One data point, several parties it may belong to (the AMC fee: the
        # client's, or a non-client lender/AMC's): the party the document has.
        for alt in binding.data_points:
            if alt is dp or alt.get("mismo") != dp.get("mismo"):
                continue
            role = bind.party_marks(alt).get("PartyRoleType")
            if role and not bind.party_marks(dp).get("PartyRoleType") == role and any(
                    (r.text or "").strip() == role for r in root.iter(f"{QN}PartyRoleType")):
                if not any((r.text or "").strip() == bind.party_marks(dp).get("PartyRoleType")
                           for r in root.iter(f"{QN}PartyRoleType")):
                    dp = alt
                    break
    xpath = dp.get("xpath", "")
    leaf_tag = dp["mismo"]
    created: list[str] = []

    # First look for the element the page already reads.  Updating that one
    # keeps a write and a read talking about the same node; walking a fresh
    # path instead is how a value lands in a block the page never shows.
    if scope is None and bind.is_inspection_service(dp):
        scope = _inspection_service(root)
    if (scope is not None and "DATA_SOURCES/DATA_SOURCE" in dp.get("xpath", "")
            and etree.QName(scope).localname == "PROPERTY"):
        scope = _data_source_for(root, scope, dp["mismo"], value)
    leaf = bind.locate(root, binding, leaf_tag, scope, ordinal)
    own = {k: v for k, v in (dp.get("requires") or {}).items() if not k.startswith(("@", "__"))}
    marks = _marks(dp, field_id)
    if leaf is not None and not bind.instance_has(leaf, own or marks):
        leaf = None                      # an untyped instance is not this one
    if leaf is None and not str(value).strip():
        # nothing there and nothing typed: a blank never creates a block, nor
        # types one -- the grid's Save sends its empty "Other" descriptions,
        # and each made a CAR_STORAGE of type Other (CarStorageType = "Other")
        return Written(field_id, leaf_tag, xpath, "", "", [])
    if leaf is None and ordinal == 1 and marks:
        # 'IF PartyRoleType = "AppraiserSupervisor"': the value belongs in the
        # instance of a block that carries that type -- found, or created with
        # it -- and 'IF GovernmentAgencyAppraisalIndicator = "true"' is a gate
        # that choosing the value opens.
        scope = instance_for(root, dp, scope, field_id)
        leaf = bind.locate(root, binding, leaf_tag, scope, ordinal)
    old = (leaf.text or "").strip() if leaf is not None else ""
    value = _is_it_this(dp, binding, value, old)
    # "2,352 sf", "$515k", "8/17/19": stored as A-1 defines the data point,
    # with its unit attribute, so the report prints the unit and symbols
    attribute = entry.unit_attribute(dp)
    current_unit = leaf.get(attribute, "") if (leaf is not None and attribute) else ""
    text, unit = entry.normalize(dp, value, current_unit)

    if leaf is None:
        if not text:
            return Written(field_id, leaf_tag, xpath, "", "", [])
        # A-1's xPath column gives the *container*; the data point names the
        # leaf inside it, so the full path is the two joined.
        segments = _segments(xpath) + [leaf_tag]
        where = bind.scope_for(root, xpath, scope, ordinal)
        if where is None:
            where = scope if scope is not None else _make_instance(
                root, xpath, ordinal, segments)
        if where is not root:
            anchor = _common_tail(where, segments)
            segments = segments[anchor:]
        parent, created = ensure_path(where, segments[:-1])
        leaf = parent.find(f"{QN}{leaf_tag}")
        if leaf is None:
            leaf = insert_ordered(parent, leaf_tag)
            created.append(leaf_tag)
        _apply_discriminator(parent, dp)

    if not text:
        parent = leaf.getparent()
        if parent is not None:
            parent.remove(leaf)          # absent, never blank -- MISMO types it
    else:
        leaf.text = text
        if attribute and unit:
            leaf.set(attribute, unit)
    if leaf_tag == "DwellingCount" and text.isdigit():
        _match_dwellings(root, leaf, int(text))
    return Written(field_id=field_id, data_point=leaf_tag,
                   path=xpath, old=old, new=text, created=created)


def _match_dwellings(root: etree._Element, leaf: etree._Element, count: int) -> None:
    """H-1 UAD1016: the dwelling count *is* the number of Dwelling structures.

    A case built from the two-building sample starts with two of them, so a
    converted two-family inherited a dwelling it does not have.  Answering the
    question the report asks is what puts the document right.
    """
    from . import structure                       # circular at module level

    prop = leaf
    while prop is not None and etree.QName(prop).localname != "PROPERTY":
        prop = prop.getparent()
    if prop is not None:
        structure.set_count(prop, count)


_RANGE = re.compile(r"^\s*(\d[\d,]*)\s*(?:-|–|—|to)\s*(\d[\d,]*)")
_SINGLE = re.compile(r"^\s*(\d[\d,]*)")


def _write_days(tree, field_id, value, binding, days, ordinal, scope) -> "Written":
    """B-1 26.010: a time in days is one number ("45 days") or a range
    ("30-60 days").  The typing decides which data points hold it; the other
    form's data points are removed so the document never carries both."""
    single = next(d["mismo"] for d in days if "Range" not in d["mismo"])
    low = next(d["mismo"] for d in days if "LowRange" in d["mismo"])
    high = next(d["mismo"] for d in days if "HighRange" in d["mismo"])
    m = _RANGE.match(value or "")
    if m:
        a, b = sorted((int(m.group(1).replace(",", "")), int(m.group(2).replace(",", ""))))
        plan = {single: "", low: str(a), high: str(b)}
    else:
        m = _SINGLE.match(value or "")
        plan = {single: m.group(1).replace(",", "") if m else "", low: "", high: ""}
    last = None
    for name in (single, low, high):
        if plan[name]:
            continue
        write(tree, field_id, "", data_point=name, ordinal=ordinal, binding=binding, scope=scope)
    for name in (single, low, high):
        if plan[name]:
            last = write(tree, field_id, plan[name], data_point=name, ordinal=ordinal,
                         binding=binding, scope=scope)
    return last or Written(field_id, single, "", "", "", [])


def _common_tail(scope: etree._Element, segments: list[str]) -> int:
    """How much of the path the scope already accounts for."""
    name = etree.QName(scope).localname
    for i in range(len(segments) - 1, -1, -1):
        if segments[i] == name:
            return i + 1
    return 0


def _make_instance(root: etree._Element, xpath: str, ordinal: int,
                   segments: list[str]) -> etree._Element:
    """Create the repeat of a block that does not exist yet."""
    found = bind.scope_for(root, xpath, None, 1)
    base = root if found is None else found
    container = bind.repeating_container(xpath)
    if not container or container not in segments:
        return base
    if etree.QName(base).localname == container and base.getparent() is not None:
        # `base` is already the first repeat of the very container a second
        # one is needed of (a Cost Approach block with Dwelling written but
        # not Outbuilding, say) -- its own parent is where the new sibling
        # belongs.  Walking `upto` from here instead mistook this deep node
        # for the document root and re-created the rest of the document as
        # its child, because the container's own tag -- deliberately not part
        # of "upto", the path *to* it -- never matched `name` to trim away.
        parent = base.getparent()
    else:
        holder = base
        name = etree.QName(base).localname
        upto = segments[:segments.index(container)]
        if name in upto:
            upto = upto[upto.index(name) + 1:]
        parent, _ = ensure_path(holder, upto)
    while len(parent.findall(f"{QN}{container}")) < ordinal:
        insert_ordered(parent, container)
    found = parent.findall(f"{QN}{container}")
    return found[ordinal - 1] if len(found) >= ordinal else base


def _apply_discriminator(parent: etree._Element, dp: dict) -> None:
    """Set the type value that identifies the instance just created.

    A new commentary without its category, or a new party without its role, is
    invisible to the page that asked for it -- the read filters on exactly that
    value.  So the write supplies it.
    """
    marks = dict(dp.get("requires") or {})
    if not marks:
        if bind.repeating_container(dp.get("xpath", "")):
            return                   # the ordinal already picked the instance
        marks = bind.discriminators().get(dp.get("context", ""), {})
    for key, want in marks.items():
        if key.startswith("__"):
            continue
        holder = parent
        while holder is not None and holder.find(f"{QN}{key}") is None:
            nxt = holder.getparent()
            if nxt is None or etree.QName(holder).localname in bind.DOCUMENT_SINGLETONS:
                break
            holder = nxt
        if holder is None:
            continue
        node = holder.find(f"{QN}{key}")
        if node is None:
            # Create it only where the schema actually accepts it: the nearest
            # container, walking up from the field's own, whose XSD content
            # model lists this element.  Dropping it into the innermost
            # container regardless is how PriorSalesOrTransfersIndicator came
            # to sit inside SALES_HISTORY -- which does not accept it -- and
            # one edit in the form left the whole document invalid.
            target = parent
            while target is not None and key not in _order_of(
                    etree.QName(target).localname):
                target = target.getparent()
            if target is None:
                continue
            node = insert_ordered(target, key)
        if not (node.text or "").strip():
            node.text = want


XL = "{http://www.w3.org/1999/xlink}"


def _role_of_type(root: etree._Element, role_type: str) -> etree._Element:
    """The ROLE with this PartyRoleType, labelled for relationships; created
    in a new PARTY of the valuation service when there is none."""
    for role in root.iter(f"{QN}ROLE"):
        if role.findtext(f"{QN}ROLE_DETAIL/{QN}PartyRoleType", "").strip() == role_type:
            break
    else:
        parties = next(root.iter(f"{QN}PARTIES"))
        party = next((x for x in parties.findall(f"{QN}PARTY") if not "".join(x.itertext()).strip()), None)
        if party is None:            # an empty PARTY is falsy in lxml: test identity, not truth
            party = insert_ordered(parties, "PARTY")
        role, _ = ensure_path(party, ["ROLES", "ROLE"])
        detail, _ = ensure_path(role, ["ROLE_DETAIL"])
        insert_ordered(detail, "PartyRoleType").text = role_type
    if not role.get(f"{XL}label"):
        role.set(f"{XL}label", _free_label(root, f"ROLE_{role_type}"))
    return role


def _free_label(root: etree._Element, stem: str) -> str:
    taken = {e.get(f"{XL}label") for e in root.iter() if isinstance(e.tag, str) and e.get(f"{XL}label")}
    label, n = stem, 1
    while label in taken:
        n += 1
        label = f"{stem}_{n}"
    return label


def _related_instance(root: etree._Element, dp: dict, role_type: str,
                      scope: etree._Element | None) -> etree._Element:
    """The block (an INSPECTION) completed by the role of this type, found by
    its INSPECTION_CompletedBy_ROLE relationship or created with one."""
    segs = _segments(dp.get("xpath", ""))
    repeat = max((i for i in range(1, len(segs)) if _plural(segs[i - 1], segs[i])), default=None)
    anchor = scope if scope is not None else (
        bind.subject(root) if bind.PROPERTY_PATH in dp.get("xpath", "") else root)
    if repeat is None or anchor is None:
        return anchor
    container = segs[repeat]
    name = etree.QName(anchor).localname
    rel = segs[segs.index(name) + 1:] if name in segs else segs
    upto = rel[:rel.index(container)] if container in rel else []
    for inst in anchor.findall("/".join(f"{QN}{t}" for t in upto + [container])):
        role = bind.related_role(inst)
        if role is not None and role.findtext(f"{QN}ROLE_DETAIL/{QN}PartyRoleType", "").strip() == role_type:
            return inst
    parent, _ = ensure_path(anchor, upto)
    stem = f"{container}_{role_type}"
    # A block whose role is gone (a blank report drops the sample's parties
    # but keeps SIGNATORY_Appraiser) is this one, not a reason to add another:
    # the subschema allows two SIGNATORYs, and a third made every signature
    # date on a 2-4 unit report invalid (E-081).
    orphans = [x for x in parent.findall(f"{QN}{container}") if bind.related_role(x) is None]
    inst = next((x for x in orphans if (x.get(f"{XL}label") or "") == stem), None)
    full = xsd_order.max_occurs(etree.QName(parent).localname, container)
    if inst is None and orphans and full > 0 and len(parent.findall(f"{QN}{container}")) >= full:
        inst = orphans[0]
    if inst is None:
        inst = insert_ordered(parent, container)
        inst.set(f"{XL}label", _free_label(root, stem))
    elif not inst.get(f"{XL}label"):
        inst.set(f"{XL}label", _free_label(root, stem))
    role = _role_of_type(root, role_type)
    rels = next(root.iter(f"{QN}RELATIONSHIPS"), None)
    if rels is None:
        holder = next(e for e in root.iter() if isinstance(e.tag, str)
                      and "RELATIONSHIPS" in _order_of(etree.QName(e).localname))
        rels = insert_ordered(holder, "RELATIONSHIPS")
    link = next((r for r in rels.findall(f"{QN}RELATIONSHIP")
                 if r.get(f"{XL}from") == inst.get(f"{XL}label")
                 and r.get(f"{XL}arcrole", "").endswith("_ROLE")), None)
    if link is not None:
        link.set(f"{XL}to", role.get(f"{XL}label"))
        return inst
    link = insert_ordered(rels, "RELATIONSHIP")
    # the arcrole is the schema's own for this pair -- a SIGNATORY is
    # IsAssociatedWith its ROLE, an INSPECTION CompletedBy it (E-081)
    link.set(f"{XL}arcrole", xsd_order.arcrole(container, "ROLE")
             or f"urn:fdc:mismo.org:2009:residential/{container}_CompletedBy_ROLE")
    link.set(f"{XL}from", inst.get(f"{XL}label"))
    link.set(f"{XL}to", role.get(f"{XL}label"))
    return inst


def _data_source_for(root: etree._Element, prop: etree._Element, name: str,
                     value: str) -> etree._Element:
    """The DATA_SOURCE a property's data-source value goes in: for a type, the
    linked source of that type (created, with its
    DATA_SOURCE_IsDataSourceFor_PROPERTY relationship, if there is none); for an
    identifier, the linked MLS source, else the last linked one."""
    linked = bind.linked_data_sources(prop)
    if name == "DataSourceType":
        for ds in linked:
            if (ds.findtext(f"{QN}DataSourceType") or "").strip() == value.strip():
                return ds
    else:
        for ds in reversed(linked):
            if (ds.findtext(f"{QN}DataSourceType") or "").strip() == "MLS":
                return ds
        if linked:
            return linked[-1]
    if not prop.get(f"{XL}label"):
        prop.set(f"{XL}label", _free_label(root, f"PROPERTY_{prop.get('ValuationUseType') or 'Property'}"))
    analysis = next(a for a in prop.iterancestors() if etree.QName(a).localname == "VALUATION_ANALYSIS")
    sources, _ = ensure_path(analysis, ["DATA_SOURCES"])
    ds = next((x for x in sources.findall(f"{QN}DATA_SOURCE") if not "".join(x.itertext()).strip()
               and not x.get(f"{XL}label")), None) or insert_ordered(sources, "DATA_SOURCE")
    ds.set(f"{XL}label", _free_label(root, f"DATA_SOURCE_{(value if name == 'DataSourceType' else 'Source')}"
                                            f"_{prop.get(f'{XL}label')}"[:60]))
    rels = next(root.iter(f"{QN}RELATIONSHIPS"), None)
    if rels is None:
        holder = next(e for e in root.iter() if isinstance(e.tag, str)
                      and "RELATIONSHIPS" in _order_of(etree.QName(e).localname))
        rels = insert_ordered(holder, "RELATIONSHIPS")
    link = insert_ordered(rels, "RELATIONSHIP")
    link.set(f"{XL}arcrole", "urn:fdc:mismo.org:2009:residential/DATA_SOURCE_IsDataSourceFor_PROPERTY")
    link.set(f"{XL}from", ds.get(f"{XL}label"))
    link.set(f"{XL}to", prop.get(f"{XL}label"))
    return ds


def _inspection_service(root: etree._Element) -> etree._Element:
    """The Property Data Report's SERVICE, created beside the valuation's."""
    svc = bind.inspection_service(root)
    if svc is not None:
        return svc
    services = next(root.iter(f"{QN}SERVICES"))
    svc = insert_ordered(services, "SERVICE")
    detail, _ = ensure_path(svc, ["SERVICE_DETAIL"])
    insert_ordered(detail, "ServiceType").text = "Inspection"
    return svc


def _marks(dp: dict, field_id: str = "") -> dict[str, str]:
    marks = {k: v for k, v in (dp.get("requires") or {}).items()
             if not k.startswith(("@", "__")) and re.match(r"^[A-Za-z]\w*$", k)}
    # a commentary box is told from every other one by its category, so a write
    # that does not carry the category overwrites whichever comment came first
    marks.update(bind.commentary_marks(field_id, dp))
    if not marks:
        # the same rule the page reads by (bind._walk): a context whose type
        # value identifies the repeating block the data point sits in
        # ("Market Inventory - Total Sales" -> MarketInventoryType TotalSales)
        container = bind.repeating_container(dp.get("xpath", ""))
        ctx = bind.discriminators().get(dp.get("context", ""), {})
        inner = ctx.get("__container__", "")
        segs = bind._tail(dp.get("xpath", ""))
        if container and inner and container in segs and inner in segs[segs.index(container):]:
            marks = {k: v for k, v in ctx.items() if not k.startswith("__") and k.endswith("Type")}
    if "PARTIES/PARTY/" in dp.get("xpath", ""):
        # the same rule the page reads by, plus the party its context names
        for key, want in bind.party_marks(dp).items():
            marks.setdefault(key, want)
    xpath = dp.get("xpath", "")
    if (not marks and not bind.repeating_container(xpath)
            and bind.DISCRIMINATED.intersection(bind._tail(xpath))):
        # Where A-1 gives no explicit condition and the block does not repeat
        # in the ordinary DEFECTS/DEFECT sense (AMENITY_CATEGORY, AMENITY:
        # both held out of repeating_container in bind.DISCRIMINATED because
        # they are picked by a type value, not a position), the Additional
        # Context column is the only place the instance is named.  The read
        # side already falls back to it (bind._walk); missing that fallback
        # here is why a water-feature amenity was written into whichever
        # category the document already had first, and the reader -- which
        # does apply the fallback -- never found it there.
        #
        # A-1's context string is free text and is not unique per field, so
        # this is deliberately restricted to a data point that actually sits
        # inside one of the type-discriminated containers -- applying it to
        # any unmarked field picked up a discriminator meant for a different
        # one and wrote "Unit" into a comparable's address.
        marks = {k: v for k, v in bind.discriminators().get(dp.get("context", ""), {}).items()
                 if not k.startswith("__")}
    return marks


def _plural(parent: str, child: str) -> bool:
    if child in bind.DOCUMENT_SINGLETONS:
        return False                     # one document, deal, service, subject
    if xsd_order.max_occurs(parent, child) == 1:
        # the subschema allows one (SALES_CONTRACTS/SALES_CONTRACT): a
        # condition on it is a gate on that one block, never a reason to add
        # a second, which the schema refuses (E-079)
        return False
    return parent in (f"{child}S", f"{child}ES") or (
        child.endswith("Y") and parent == f"{child[:-1]}IES")


@lru_cache(maxsize=None)
def _paths_of(name: str) -> tuple[tuple[str, ...], ...]:
    """Every container path A-1 gives a data point of this name."""
    import json
    data = json.loads((bind.SPEC / "field_index.json").read_text(encoding="utf-8"))["fields"]
    out = []
    for entry_ in data.values():
        for dp in entry_.get("data_points") or []:
            if dp.get("mismo") == name and dp.get("xpath"):
                path = tuple(_segments(dp["xpath"]))
                if path not in out:
                    out.append(path)
    return tuple(out)


def instance_for(root: etree._Element, dp: dict,
                 scope: etree._Element | None = None,
                 field_id: str = "") -> etree._Element | None:
    """The element a conditioned data point is written inside.

    For each condition A-1 puts on the data point, the type element's own
    A-1 path is compared with the data point's: where the two part company
    below a repeating block (PARTIES/PARTY, ROLES/ROLE), that block is the
    instance the condition picks -- the one whose type has that value, or a
    new one given it, in schema order.  Where they part company with no
    repeat between (SCOPE_OF_WORK_DETAIL), the condition is a gate on a single
    block, and the value implied by choosing this data point is set.
    """
    segs = _segments(dp.get("xpath", ""))
    marks_ = _marks(dp, field_id)
    if marks_.get("PartyRoleType") and "PARTIES/PARTY/" not in dp.get("xpath", ""):
        base = _related_instance(root, dp, marks_["PartyRoleType"], scope)
        marks_ = {k: v for k, v in marks_.items() if k != "PartyRoleType"}
        scope = base
    plan = []
    for key, want in marks_.items():
        paths = _paths_of(key)
        if not paths:
            container = bind.repeating_container(dp.get("xpath", ""))
            if container and key in _order_of(container):
                # The type is not a data point of its own anywhere in A-1 --
                # ValuationAnalysisCategoryType is written only as a condition
                # -- but it sits inside the block this value repeats in, so it
                # names the instance rather than gating a single one.  Treated
                # as a gate it was simply overwritten, and every commentary in
                # the report ended up in the first block, each write erasing
                # the one before it.
                # the path of the block itself: the code appends the key
                paths = (tuple(segs),)
            else:
                # A-1 names the gate only as a condition: it sits in the
                # value's own container or one above it, wherever the XSD
                # accepts it
                plan.append((10_000, key, want, None))   # after the instances
                continue
        def common(path):
            n = 0
            while n < min(len(path), len(segs)) and path[n] == segs[n]:
                n += 1
            return n
        best = max(paths, key=common)
        n = common(best)
        repeat = max((i for i in range(1, n) if _plural(segs[i - 1], segs[i])), default=None)
        plan.append((-1 if repeat is None else repeat, key, want, best))
    plan.sort()
    base = scope
    for repeat, key, want, kpath in plan:
        if repeat == 10_000:
            anchor = base if base is not None else (
                bind.subject(root) if bind.PROPERTY_PATH in dp.get("xpath", "") else root)
            rel = list(segs)
            if anchor is not None and etree.QName(anchor).localname in rel:
                name = etree.QName(anchor).localname
                rel = rel[len(rel) - rel[::-1].index(name):]
            elif anchor is root and rel and rel[0] == etree.QName(root).localname:
                rel = rel[1:]
            holder, _ = ensure_path(anchor, rel)
            found = None
            cur = holder
            while cur is not None and found is None:
                found = cur.find(f"{QN}{key}")
                if found is None:
                    cur = cur.getparent()
            if found is None:
                cur = holder
                while cur is not None and key not in _order_of(etree.QName(cur).localname):
                    cur = cur.getparent()
                if cur is None:
                    continue
                found = insert_ordered(cur, key)
            found.text = want
            continue
        anchor = base
        rel = list(segs)
        if anchor is None:
            if "PROPERTY" in segs and bind.PROPERTY_PATH in dp.get("xpath", ""):
                anchor = bind.subject(root)
                rel = segs[segs.index("PROPERTY") + 1:] if anchor is not None else rel
            if anchor is None:
                anchor = root
                rel = segs[1:] if segs and segs[0] == etree.QName(root).localname else segs
        else:
            name = etree.QName(anchor).localname
            if name in rel:
                rel = rel[len(rel) - rel[::-1].index(name):]
        cut = len(segs) - len(rel)                 # where rel starts within segs
        if repeat < 0:
            # a gate: a single block, reached by the type element's own A-1 path
            upto = list(kpath[1:] if kpath and kpath[0] == etree.QName(root).localname else kpath)
            holder, _ = ensure_path(root, upto) if upto else (root, [])
            node = holder.find(f"{QN}{key}")
            if node is None:
                node = insert_ordered(holder, key)
            node.text = want
            continue
        if repeat < cut:
            continue                               # the scope is already inside that block
        container = segs[repeat]
        to_key = list(kpath[repeat + 1:])
        path = "/".join(f"{QN}{t}" for t in segs[cut:repeat + 1])
        chosen = None
        # any instance of the block, under any instance of the blocks around it
        for inst in (anchor.findall(path) if path else []):
            hit = inst.find("/".join(f"{QN}{t}" for t in to_key + [key]))
            if hit is not None and (hit.text or "").strip() == want:
                chosen = inst
                break
        if chosen is None:
            # none has that type: a new instance of the outermost repeat
            # (a new PARTY, not a second role inside the lender's party)
            outer = min((i for i in range(max(cut, 1), repeat + 1) if _plural(segs[i - 1], segs[i])),
                        default=repeat)
            parent, _ = ensure_path(anchor, segs[cut:outer])
            # creating the plural may itself have made an empty instance the
            # schema requires; that skeleton is the new instance
            fresh = next((x for x in parent.findall(f"{QN}{segs[outer]}")
                          if not "".join(x.itertext()).strip()), None)
            if fresh is None:
                fresh = insert_ordered(parent, segs[outer])
            inner, _ = ensure_path(fresh, segs[outer + 1:repeat + 1])
            holder, _ = ensure_path(inner, to_key)
            insert_ordered(holder, key).text = want
            chosen = inner
        # A ROLE is an APPRAISER or a SERVICE_PROVIDER, not both (an XSD
        # choice): where this instance already holds a rival of the block the
        # value needs, the value goes in a sibling instance (D-1 keeps the
        # appraisal fee in a second ROLE of the appraiser's party).
        nxt = segs[repeat + 1] if repeat + 1 < len(segs) else ""
        if nxt and chosen.find(f"{QN}{nxt}") is None and chosen.getparent() is not None:
            rival = xsd_order.rivals(container, nxt)
            if any(chosen.find(f"{QN}{r}") is not None for r in rival):
                holder = chosen.getparent()
                sibling = next((x for x in holder.findall(f"{QN}{container}")
                                if x is not chosen and x.find(f"{QN}{nxt}") is not None), None)
                if sibling is None:
                    sibling = next((x for x in holder.findall(f"{QN}{container}")
                                    if x is not chosen and not any(x.find(f"{QN}{r}") is not None
                                                                   for r in rival)
                                    and not "".join(x.itertext()).strip()), None)
                chosen = sibling if sibling is not None else insert_ordered(holder, container)
        base = chosen
    return base


def _append_instance(scope: etree._Element, segments: list[str],
                     container: str, ordinal: int) -> etree._Element | None:
    """Create the missing repeat of a block, up to the ordinal asked for."""
    if container not in segments:
        return None
    upto = segments[:segments.index(container)]
    parent, _created = ensure_path(scope, upto)
    while len(parent.findall(f"{QN}{container}")) < ordinal:
        insert_ordered(parent, container)
    found = parent.findall(f"{QN}{container}")
    return found[ordinal - 1] if len(found) >= ordinal else None


def _binding_for(field_id: str) -> bind.Binding:
    """The binding for a Report Field ID.

    The page model covers the fields the older renderer laid out by label.  The
    report is now drawn from C-1, which places fields that model never had a
    row for -- every commentary box, the defect indicators, the instance
    identifiers -- so a field it does not know is bound straight from A-1's own
    index rather than refused.
    """
    for fields in bind.page_model().values():
        for pf in fields:
            if pf.field_id == field_id:
                return pf.binding
    b = bind.binding_for(field_id)
    if b is None:
        raise KeyError(f"no field {field_id} on the page")
    return b


def field(field_id: str):
    """The page field for an identifier, with its position and binding.

    As with ``_binding_for``: a field the older page model never laid out is
    still a field of the report, and refusing it here is what left the editor
    drawing free text where A-1 gives a closed list, and the API answering 404
    for a value the form shows.
    """
    for fields in bind.page_model().values():
        for pf in fields:
            if pf.field_id == field_id:
                return pf
    b = bind.binding_for(field_id)
    if b is None:
        raise KeyError(f"no field {field_id} on the page")
    return bind.PageField(field_id=field_id, label=b.label, section=b.section,
                          subsection=b.subsection, column=0, indent=0, binding=b)
