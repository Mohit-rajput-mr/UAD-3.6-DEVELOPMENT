"""Heal a saved document that an older remover left invalid (T-1201).

Before T-509 (E-180) every remover took a block out and then its holder once
that was empty, so the last amenity of a category went with its AMENITIES and
left the AMENITY_CATEGORY holding only its AMENITY_CATEGORY_DETAIL.  The
removers are fixed, but a case saved before then still carries the result,
and the Review Master shows it as an XSD fatal with no field to go to:

    Element 'AMENITY_CATEGORY_DETAIL': This element is not expected.
    Expected is ( AMENITIES ).

Each such fault names the holder (the parent of the element "not expected")
and the child the schema wanted before it.  Two repairs are tried on a copy,
in this order:

* **Take the holder out** when it says nothing but which block it is (its
  type, the values a blank report keeps: ``templates.structure_elements``)
  and nothing links to it -- the category of an amenity that is gone.
  ``edit.remove_block`` walks up through every holder the schema no longer
  lets stand.
* **Put the wanted container back** (``templates._restore_required_containers``)
  when an empty one is itself valid -- a PARTIES wrapper blanking emptied.

A repair is kept only when it lowers the schema error count and every answer
the document held is still in it.  Nothing is invented; what cannot be
repaired this way stays an XSD finding.
"""
from __future__ import annotations

import collections
from copy import deepcopy
from dataclasses import dataclass, field

from lxml import etree

from . import bind, edit, schema, templates

M = f"{{{bind.MISMO}}}"
XL = "{http://www.w3.org/1999/xlink}"


@dataclass
class Healed:
    tree: etree._ElementTree
    before: int = 0                       # schema errors before
    after: int = 0                        # and after
    removed: list[str] = field(default_factory=list)
    restored: int = 0

    @property
    def changed(self) -> bool:
        return self.after < self.before


def _answers(root: etree._Element) -> collections.Counter:
    """Every value the document states beyond what says which block is which."""
    kept = templates.structure_elements()
    return collections.Counter(
        (etree.QName(n).localname, (n.text or "").strip()) for n in root.iter()
        if isinstance(n.tag, str) and not len(n) and (n.text or "").strip()
        and etree.QName(n).localname not in kept)


def _linked(root: etree._Element, node: etree._Element) -> bool:
    ends = {r.get(f"{XL}{e}") for r in root.iter(f"{M}RELATIONSHIP") for e in ("from", "to")}
    return any(x.get(f"{XL}label") in ends for x in node.iter() if isinstance(x.tag, str))


def _bare(node: etree._Element) -> bool:
    return not _answers(node)


def heal(tree) -> Healed:
    """A repaired copy of ``tree`` and what was done; ``tree`` is untouched."""
    work = deepcopy(tree.getroottree() if hasattr(tree, "getroottree") else tree)
    root = work.getroot()
    answers = _answers(root)
    errors = schema.validate(work)
    out = Healed(tree=work, before=len(errors), after=len(errors))
    for _round in range(16):
        progress = False
        for err in schema.validate(work):
            m = templates._EXPECTED.search(getattr(err, "message", "") or "")
            path = getattr(err, "path", "") or ""
            if not m or not path:
                continue
            found = work.xpath(path)
            holder = found[0].getparent() if found else None
            if holder is None or holder is root or not _bare(holder) or _linked(root, holder):
                continue
            trial = deepcopy(work)
            node = trial.xpath(work.getpath(holder))[0]
            name = etree.QName(node).localname
            try:
                edit.remove_block(node)
            except edit.Unremovable:
                continue
            if len(schema.validate(trial)) < len(schema.validate(work)) \
                    and not (answers - _answers(trial.getroot())):
                work = trial
                root = work.getroot()
                out.removed.append(name)
                progress = True
                break
        if not progress:
            break
    trial = deepcopy(work)
    restored = templates._restore_required_containers(trial.getroot())
    if restored and len(schema.validate(trial)) < len(schema.validate(work)) \
            and not (answers - _answers(trial.getroot())):
        work, out.restored = trial, restored
    out.tree = work
    out.after = len(schema.validate(work))
    return out
