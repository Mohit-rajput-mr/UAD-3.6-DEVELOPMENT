import pathlib

p = pathlib.Path("engine/uad/report/comparables.py")
s = p.read_text(encoding="utf-8")

start = s.index('ADDITIONAL_ROW = "[Additional Row]"')
end = s.index('def specs(root: etree._Element, kind: str = "sales", *,')

NEW = '''ADDITIONAL_ROW = "[Additional Row]"
# B-1 writes a row the appraiser names in brackets: "[Additional Row]" is one
# they invent outright, "[Other Exterior Feature]" one the standard list does
# not cover.  Both work the same way -- a name and, beside it, what each
# property has -- and both are expanded here into ordinary named rows.
NAMED_ROWS = ("AdditionalComparisonLineItemIdentifier",
              "ImprovementComponentTypeOtherDescription")

# Where the sales sheet keeps a row it cannot adjust.  A-1 enumerates exactly
# three additional-item types; which one applies follows from the grid.
ADDITIONAL_TYPE = {"sales": "SalesComparableAdditionalNonAdjustableComparisonItem",
                   "grm": "GrossRentMultiplierAdditionalNonAdjustableComparisonItem"}


@dataclass(frozen=True)
class Named:
    """How a row the appraiser names is stored."""
    container: str
    marks: tuple            # (element name, value) pairs that identify it
    name_dp: str            # the data point holding the name
    value_dp: str           # the data point holding what each property has
    value_fid: str


def _next_field_in(container: str, fid: str) -> tuple[str, str]:
    """A-1 numbers a named row's value straight after its name.

    "[Other Exterior Feature]" is 22.08.07, what the property has is 22.08.08;
    "[Additional Row]" is 22.05.18 and its description 22.05.19.  So the value
    is the next Report Field ID in the same container, which is read here
    rather than written out.
    """
    head, _, tail = fid.rpartition(".")
    try:
        nxt = f"{head}.{int(tail) + 1:0{len(tail)}d}"
    except ValueError:
        return "", ""
    binding = binding_of(nxt)
    for dp in (binding.data_points if binding else []):
        if bind.repeating_container(dp.get("xpath", "")) == container and dp.get("mismo"):
            return nxt, dp["mismo"]
    return "", ""


@lru_cache(maxsize=256)
def named_row(kind: str, fid: str, data_point: str, adjust_type: str) -> "Named | None":
    """What a bracketed row of the workbook means, or None if it is not one."""
    if data_point not in NAMED_ROWS:
        return None
    binding = binding_of(fid)
    if binding is None:
        return None
    dp = next((d for d in binding.data_points if d.get("mismo") == data_point), None)
    if dp is None:
        return None
    container = bind.repeating_container(dp.get("xpath", ""))
    if not container:
        return None
    marks = {k: v for k, v in (dp.get("requires") or {}).items()
             if not k.startswith(("@", "__"))}
    if container == "COMPARABLE_ADJUSTMENT":
        marks["ComparableAdjustmentType"] = adjust_type or ADDITIONAL_TYPE.get(kind, "")
    value_fid, value_dp = _next_field_in(container, fid)
    if not value_dp:
        return None
    return Named(container, tuple(sorted(marks.items())), data_point, value_dp, value_fid)


def line_item_place(kind: str, row: "GridRow") -> tuple[str, str]:
    """(the container this grid keeps added rows in, the type that marks one)."""
    named = named_row(kind, row.subject_fid or row.comp_fid, row.data_point,
                      row.adjust_type)
    if named is None:
        return "", ""
    return named.container, dict(named.marks).get("ComparableAdjustmentType", "")


def _is_item(node, named: "Named", name: str = "") -> bool:
    M_ = f"{{{bind.MISMO}}}"
    for key, want in named.marks:
        if node.findtext(f"{M_}{key}", "").strip() != want:
            return False
    got = node.findtext(f"{M_}{named.name_dp}", "").strip()
    return got == name if name else bool(got)


def named_values(root: etree._Element, named: "Named", props: list) -> list[str]:
    """Every name given to this group's rows, in document order."""
    names: list[str] = []
    for prop in props:
        for node in prop.iter(f"{{{bind.MISMO}}}{named.container}"):
            if not _is_item(node, named):
                continue
            name = node.findtext(f"{{{bind.MISMO}}}{named.name_dp}", "").strip()
            if name not in names:
                names.append(name)
    return names


def named_node(prop: etree._Element, named: "Named", name: str, *, create: bool = False):
    """The element this property keeps that named row in."""
    for node in prop.iter(f"{{{bind.MISMO}}}{named.container}"):
        if _is_item(node, named, name):
            return node
    if not create:
        return None
    holder = _container_parent(prop, named)
    if holder is None:
        return None
    node = edit.insert_ordered(holder, named.container)
    for key, want in named.marks:
        edit.insert_ordered(node, key).text = want
    edit.insert_ordered(node, named.name_dp).text = name
    return node


def _container_parent(prop: etree._Element, named: "Named"):
    """The element a named row hangs from, made if the case has none yet."""
    binding = binding_of(named.value_fid)
    for dp in (binding.data_points if binding else []):
        segs = bind._tail(dp.get("xpath", ""))
        if named.container not in segs or "PROPERTY" not in segs:
            continue
        upto = segs[segs.index("PROPERTY") + 1:segs.index(named.container)]
        holder, _ = edit.ensure_path(prop, upto)
        return holder
    return None


def named_value(prop: etree._Element, named: "Named", name: str) -> tuple[str, str]:
    """What this property says on that row, and its adjustment."""
    node = named_node(prop, named, name)
    if node is None:
        return "", ""
    M_ = f"{{{bind.MISMO}}}"
    text = node.findtext(f"{M_}{named.value_dp}", "").strip()
    binding = binding_of(named.value_fid)
    if text and binding is not None:
        text = bind.display_value([[(named.value_dp, text)]], binding) or text
    amount = node.findtext(f"{M_}ComparableAdjustmentAmount", "").strip()
    if amount:
        amount = bind.format_value(amount, "Amount", "+9.0")
    return text, amount


'''

s = s[:start] + NEW + s[end:]
p.write_text(s, encoding="utf-8")
print("helpers ok")
