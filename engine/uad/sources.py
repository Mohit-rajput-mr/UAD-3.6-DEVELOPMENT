"""Data sources tied to what they are the source for.

A-1 keeps every data source once, in VALUATION_ANALYSIS/DATA_SOURCES, and ties
each to what it sources with a relationship whose arcrole names the target:
DATA_SOURCE_IsDataSourceFor_PROPERTY_UNIT_AREA for a unit's area (10.009),
..._MARKET_TREND for the price trend (17.018), ..._AccessoryDwellingUnit
LegallyRentableIndicator for that one answer (10.013).  B-1 states the target
in the field's display rule ("An arcrole is required for each data source from
DATA SOURCE n to PROPERTY UNIT AREA n"), read by ``form.data_source_target``.

So writing such a field is adding (or removing) a DATA_SOURCE and its link,
inside the unit or section the value is entered for -- a source written
without its link reads back as nothing, which is how a typed Area Data Source
used to vanish on any report the template had not pre-linked.
"""
from __future__ import annotations

from lxml import etree

from . import bind, edit, xsd_order

M = f"{{{bind.MISMO}}}"
X = "{http://www.w3.org/1999/xlink}"
ARC = "urn:fdc:mismo.org:2009:residential/DATA_SOURCE_IsDataSourceFor_{}"


def _is_source(scope: etree._Element | None) -> bool:
    return scope is not None and etree.QName(scope).localname == "DATA_SOURCE"


def target_of(root: etree._Element, source: etree._Element, target: str) -> etree._Element | None:
    """What this DATA_SOURCE is the source for, of the target's kind: a row
    of the list the editor draws for a field of several sources is keyed by
    the DATA_SOURCE (form.repeats_as_list), not by what it is tied to.  One
    source may be tied to several (D-1 SF5: DATA_SOURCE_MLS sources the
    subject's listing and its prior sales); the subject's comes first."""
    label = source.get(f"{X}label")
    tos = {r.get(f"{X}to") for r in root.iter(f"{M}RELATIONSHIP")
           if label and r.get(f"{X}from") == label
           and r.get(f"{X}arcrole", "").endswith(f"IsDataSourceFor_{target}")}
    tied = [e for e in root.iter(f"{M}{target}") if e.get(f"{X}label") in tos]
    subj = bind.subject(root)
    mine = [e for e in tied if subj is not None and any(a is subj for a in e.iterancestors())]
    return (mine or tied or [None])[0]


def _untie(root: etree._Element, source: etree._Element, target_el: etree._Element) -> None:
    """Take one source off one target; a source then tied to nothing goes."""
    for rel in list(root.iter(f"{M}RELATIONSHIP")):
        if rel.get(f"{X}from") == source.get(f"{X}label") and rel.get(f"{X}to") == target_el.get(f"{X}label"):
            edit.remove_block(rel)   # MISMO: RELATIONSHIPS holds at least one
    if not any(r.get(f"{X}from") == source.get(f"{X}label") for r in root.iter(f"{M}RELATIONSHIP")):
        edit.remove_block(source)    # and DATA_SOURCES at least one DATA_SOURCE


def _target_element(root: etree._Element, scope: etree._Element | None, target: str,
                    *, create: bool) -> etree._Element | None:
    if _is_source(scope):
        return target_of(root, scope, target)
    base = scope if scope is not None else bind.subject(root)
    if base is None:
        return None
    found = next(base.iter(f"{M}{target}"), None)
    if found is None and scope is None:
        # a target no property holds is the report's own, as the report reads
        # it (form._linked_sources): COST_APPROACH sits in the valuation, not
        # the subject (25.052 Cost Data Source, D-1 MH1)
        found = next((e for e in root.iter(f"{M}{target}")
                      if next(e.iterancestors(f"{M}PROPERTY"), None) is None), None)
    if found is None and create:
        # the target is a container on the unit or property's own path
        # (PROPERTY_UNIT_AREA under PROPERTY_UNIT): made in the schema's order
        if target in edit._order_of(etree.QName(base).localname):
            found = edit.insert_ordered(base, target)
    return found


def _first_answer(target: str) -> str:
    """Where the target is an answer, not a block (A-1 ties the "no prior
    sales" source to PriorSalesOrTransfersIndicator itself, D-1 SF1; the
    legally-rentable source to AccessoryDwellingUnitLegallyRentableIndicator,
    D-1 SF3): what the appraiser must answer before it can have a source --
    "Legally Rentable (10.012)".  Empty for a block."""
    from . import uadmap
    if target.isupper() or not uadmap.known(target):
        return ""
    where = (uadmap.point(target).get("locations") or [""])[0].split("\n")[0]
    fid, _, place = where.partition(": ")
    return f"{place.rsplit(' - ', 1)[-1].strip()} ({fid.strip()})" if place else target


def read(root: etree._Element, target: str, data_point: str,
         scope: etree._Element | None = None) -> list[str]:
    """The ``data_point`` of every source tied to the target in this scope,
    in document order -- what ``write`` stored, read back the way the report
    reads it (form._linked_sources), never the first DATA_SOURCE in the list."""
    target_el = _target_element(root, scope, target, create=False)
    if target_el is None:
        return []
    return [text for ds in linked(root, target_el, target)
            if (text := (ds.findtext(f"{M}{data_point}") or "").strip())]


def groups(root: etree._Element, target: str, names: list[str],
           scope: etree._Element | None = None) -> list[list[tuple[str, str]]]:
    """(data point, value) per tied source, as ``bind.read_groups`` gives
    them for a field read where it sits."""
    target_el = _target_element(root, scope, target, create=False)
    out = []
    for ds in (linked(root, target_el, target) if target_el is not None else []):
        group = [(n, (ds.findtext(f"{M}{n}") or "").strip()) for n in names]
        group = [p for p in group if p[1]]
        if group:
            out.append(group)
    return out


def linked(root: etree._Element, target_el: etree._Element, target: str) -> list[etree._Element]:
    label = target_el.get(f"{X}label")
    if not label:
        return []
    wanted = [r.get(f"{X}from") for r in root.iter(f"{M}RELATIONSHIP")
              if r.get(f"{X}to") == label and r.get(f"{X}arcrole", "").endswith(f"IsDataSourceFor_{target}")]
    by = {ds.get(f"{X}label"): ds for ds in root.iter(f"{M}DATA_SOURCE")}
    return [by[w] for w in dict.fromkeys(wanted) if w in by]


def _relationships(root: etree._Element) -> etree._Element:
    rels = next(root.iter(f"{M}RELATIONSHIPS"), None)
    if rels is None:
        holder = next(e for e in root.iter() if isinstance(e.tag, str)
                      and "RELATIONSHIPS" in edit._order_of(etree.QName(e).localname))
        rels = edit.insert_ordered(holder, "RELATIONSHIPS")
    return rels


def _sources_holder(root: etree._Element) -> etree._Element:
    va = next(root.iter(f"{M}VALUATION_ANALYSIS"))
    holder = va.find(f"{M}DATA_SOURCES")
    if holder is None:
        holder = edit.insert_ordered(va, "DATA_SOURCES")
    return holder


def write(root: etree._Element, target: str, data_point: str, value: str,
          scope: etree._Element | None = None) -> tuple[str, str]:
    """Add the source ``value`` (a DataSourceType, or another data point of
    the source such as its description) for the target in this scope; an
    empty value removes every source linked there.  Returns (old, new).

    Where the scope is one of those sources -- a row of the list the editor
    draws for them, keyed by its DATA_SOURCE -- the value is that row's: a
    new type replaces it for this target alone (a source tied to more than
    this keeps its other ties), a description is its own, and an empty value
    takes it off.  Written as an ordinary scope, the row looked for the
    target inside the DATA_SOURCE and every change after the first pick was
    refused (T-1072)."""
    row = scope if _is_source(scope) else None
    target_el = _target_element(root, scope, target, create=bool(value) and row is None)
    if target_el is None:
        if not value:
            return "", ""
        answer = _first_answer(target)
        if answer:
            raise ValueError(f"Answer {answer} first: this is the data source of that answer.")
        raise ValueError(f"there is no {target.replace('_', ' ').lower()} here to give a source")
    have = linked(root, target_el, target)
    old = " | ".join((ds.findtext(f"{M}{data_point}") or "").strip() for ds in have
                     if (ds.findtext(f"{M}{data_point}") or "").strip())
    if row is not None:
        old = (row.findtext(f"{M}{data_point}") or "").strip()
        if value and (data_point != "DataSourceType" or old == value):
            node = row.find(f"{M}{data_point}")
            if node is None:
                node = edit.insert_ordered(row, data_point)
            node.text = value
            return old, value
        _untie(root, row, target_el)
        have = [ds for ds in have if ds is not row]
        if not value:
            return old, ""
    elif not value:
        for ds in have:
            _untie(root, ds, target_el)
        return old, ""
    if data_point != "DataSourceType" and have:
        # a description, name or identifier belongs to the source already there
        ds = have[-1]
        node = ds.find(f"{M}{data_point}")
        if node is None:
            node = edit.insert_ordered(ds, data_point)
        node.text = value
        return old, value
    if any((ds.findtext(f"{M}{data_point}") or "").strip() == value for ds in have):
        return old, value                                    # already a source here
    if not target_el.get(f"{X}label"):
        target_el.set(f"{X}label", edit._free_label(root, target))
    ds = edit.insert_ordered(_sources_holder(root), "DATA_SOURCE")
    ds.set(f"{X}label", edit._free_label(root, f"DATA_SOURCE_{target}"))
    edit.insert_ordered(ds, data_point).text = value
    link = edit.insert_ordered(_relationships(root), "RELATIONSHIP")
    link.set(f"{X}arcrole", xsd_order.arcrole("DATA_SOURCE", target) or ARC.format(target))
    link.set(f"{X}from", ds.get(f"{X}label"))
    link.set(f"{X}to", target_el.get(f"{X}label"))
    return old, value
