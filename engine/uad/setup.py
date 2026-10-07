"""Report setup: the property type and the approaches, stated up front.

The report takes its shape from the determining answers (uad/shape.py), but
some of what decides it is never on the report: B-1 shows Rental Information
when RentScheduleIndicator = "true", the Income Approach when
IncomeApproachIndicator = "true" and the Cost Approach when
CostApproachIndicator = "true" -- "FID: Not on report", so the form itself
offers no place to say so.  The setup page is that place, and the place an
appraiser states the kind of property before filling a word of it: single
family, 2- to 4-unit (and how many units), condominium, cooperative or
manufactured home.

The property type is applied the same way an answer in the report is: the
case is rebuilt on the closest official (D-1) structure with every value
carried (shape.reshape), the determining answers are written to match, and
the unit count is made exact by the structure engine.
"""
from __future__ import annotations

from copy import deepcopy

from lxml import etree

from . import bind, edit, shape, templates

M = f"{{{bind.MISMO}}}"

#: the kinds an appraiser chooses between, in the order they are offered
CHOICES = ("single_family", "two_to_four_unit", "condominium", "cooperative", "manufactured")

#: Scope of Work indicators (A-1 SCOPE_OF_WORK_DETAIL, "Not on report") the
#: setup states, by the name the API uses
APPROACHES = {"sales": "SalesComparisonApproachIndicator", "cost": "CostApproachIndicator",
              "income": "IncomeApproachIndicator", "rent": "RentScheduleIndicator"}


def _scope_detail(root: etree._Element, create: bool) -> etree._Element | None:
    found = next(root.iter(f"{M}SCOPE_OF_WORK_DETAIL"), None)
    if found is not None or not create:
        return found
    report = next(root.iter(f"{M}VALUATION_REPORT"), None)
    if report is None:
        return None
    holder, _ = edit.ensure_path(report, ["SCOPE_OF_WORK", "SCOPE_OF_WORK_DETAIL"])
    return holder


def approaches(root: etree._Element) -> dict[str, bool]:
    detail = _scope_detail(root, create=False)
    return {k: (detail is not None and (detail.findtext(f"{M}{name}") or "").strip() == "true")
            for k, name in APPROACHES.items()}


def set_approaches(root: etree._Element, wanted: dict[str, bool]) -> None:
    detail = _scope_detail(root, create=True)
    if detail is None:
        raise ValueError("this report has no scope of work to state the approaches in")
    for key, on in wanted.items():
        name = APPROACHES.get(key)
        if not name:
            continue
        el = detail.find(f"{M}{name}")
        if el is None:
            el = edit.insert_ordered(detail, name)
        el.text = "true" if on else "false"


def keep_approaches(source: etree._Element, target: etree._Element,
                    default: dict[str, bool] | None = None) -> None:
    """After a reshape: an approach the report had, or the new structure
    develops by default (D-1 2-4: rent schedule and income), stays on --
    carrying the old structure's "false" switched the 2-4 rental sections
    off (owner, 2026-10-07)."""
    before = approaches(source)
    default = default if default is not None else approaches(target)   # read before the carry
    set_approaches(target, {k: before[k] or default[k] for k in APPROACHES})


def current(root: etree._Element) -> dict:
    det = shape.determinants(root)
    try:
        units = int(det.get("units_excluding_adus") or 1)
    except ValueError:
        units = 1
    return {"property_type": shape.property_type(root), "units": units,
            "approaches": approaches(root),
            "choices": [{"key": k, "name": templates.PROPERTY_TYPES.get(k, k)} for k in CHOICES]}


def _target(kind: str, units: int) -> tuple[str, dict[str, str]]:
    """The official structure and determining answers for this kind."""
    pool = templates.by_property_type().get(kind) or []
    if not pool:
        raise ValueError(f"no official structure for {kind!r}")
    if kind == "two_to_four_unit":
        base = min(pool, key=lambda t: (abs(int(t.units) - units), t.elements))
    else:
        base = min(pool, key=lambda t: (t.comps, t.elements))
    det = dict(base.determinants)
    det["units_excluding_adus"] = str(units if kind == "two_to_four_unit" else 1)
    return base.key, det


def apply(tree: etree._ElementTree, current_template: str, kind: str, units: int,
          wanted: dict[str, bool]) -> tuple[etree._ElementTree, str | None, list[str], list]:
    """The case's tree with this setup applied: (tree, new template or None,
    notes, values that found no place)."""
    if kind not in CHOICES:
        raise ValueError(f"unknown property type {kind!r}")
    units = max(1, min(4, int(units or 1)))
    if kind == "two_to_four_unit":
        units = max(2, units)
    root = tree.getroot()
    notes: list[str] = []
    failed: list = []
    new_template = None
    det_now = shape.determinants(root)
    template, det = _target(kind, units)
    if shape.property_type(root) != kind or shape.shape_key(det_now) != shape.shape_key(det):
        if template != current_template:
            reshaped = shape.reshape(tree, template)
            keep_approaches(root, reshaped.tree.getroot())
            tree, new_template, failed = reshaped.tree, template, reshaped.failed
            notes.append(f"now a {templates.PROPERTY_TYPES.get(kind, kind)} report; "
                         f"{reshaped.carried} answers carried")
        # the determining answers say what the report is
        tree = deepcopy(tree)
        # (one the new kind leaves unanswered is cleared: a co-op's
        # "Cooperative" carried into a single-family report would make it a
        # co-op again)
        for name, (fid, xp) in templates.determinants().items():
            if name == "adu_count":
                continue
            value = (det.get(name) or "").strip()
            if value:
                try:
                    edit.write(tree, fid, value)
                except (KeyError, ValueError):
                    pass
            else:
                for el in tree.getroot().xpath(f"./{templates._qualify(xp)}", namespaces=templates.NS) or []:
                    if isinstance(el, etree._Element):
                        el.getparent().remove(el)
        if kind not in ("condominium", "cooperative"):
            # a project's answers carried from a condominium or co-op shape
            # (the subject's "in a project", the comparables' legal
            # structure) would keep Project Information on the report
            for name in ("ProjectLegalStructureType", "PropertyInProjectIndicator"):
                for el in list(tree.getroot().iter(f"{M}{name}")):
                    el.getparent().remove(el)
        from . import structure
        notes += structure.set_units(tree.getroot(), units if kind == "two_to_four_unit" else 1, [])
    set_approaches(tree.getroot(), {k: bool(v) for k, v in wanted.items() if k in APPROACHES})
    return tree, new_template, notes, failed
