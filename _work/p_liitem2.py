import pathlib

p = pathlib.Path("engine/uad/report/comparables.py")
s = p.read_text(encoding="utf-8")

start = s.index('ADDITIONAL_ROW = "[Additional Row]"')
end = s.index('def build(tree, kind: str = "sales"')

NEW = '''ADDITIONAL_ROW = "[Additional Row]"

# Where a grid keeps the rows an appraiser adds.  The sales sheet keeps them
# among the comparable's adjustments, told apart by a ComparableAdjustmentType
# A-1 enumerates; the rental sheet has a container of its own and no
# adjustment at all.  Which it is, is read from the field's own A-1 xPath.
ADDITIONAL_TYPE = {"sales": "SalesComparableAdditionalNonAdjustableComparisonItem",
                   "grm": "GrossRentMultiplierAdditionalNonAdjustableComparisonItem"}


def line_item_place(kind: str, row: "GridRow") -> tuple[str, str]:
    """(the container this grid keeps added rows in, the type that marks one)."""
    fid = row.subject_fid or row.comp_fid
    container = ""
    for dp in points_for(fid):
        if dp.get("mismo") == "AdditionalComparisonLineItemIdentifier":
            container = bind.repeating_container(dp.get("xpath", ""))
            break
    if container != "COMPARABLE_ADJUSTMENT":
        return container, ""
    return container, (row.adjust_type or ADDITIONAL_TYPE.get(kind, ""))


def _is_item(node, adjust_type: str, name: str = "") -> bool:
    M_ = f"{{{bind.MISMO}}}"
    if adjust_type and node.findtext(f"{M_}ComparableAdjustmentType", "").strip() != adjust_type:
        return False
    got = node.findtext(f"{M_}AdditionalComparisonLineItemIdentifier", "").strip()
    return got == name if name else bool(got)


def line_items(root: etree._Element, kind: str, row: "GridRow", props: list) -> list[str]:
    """Every name given to this grid's added rows, in document order."""
    container, adjust_type = line_item_place(kind, row)
    if not container:
        return []
    names: list[str] = []
    for prop in props:
        for node in prop.iter(f"{{{bind.MISMO}}}{container}"):
            if not _is_item(node, adjust_type):
                continue
            name = node.findtext(
                f"{{{bind.MISMO}}}AdditionalComparisonLineItemIdentifier", "").strip()
            if name not in names:
                names.append(name)
    return names


def line_item_node(prop: etree._Element, container: str, adjust_type: str,
                   name: str, *, create: bool = False):
    """The element this property keeps that added row in."""
    for node in prop.iter(f"{{{bind.MISMO}}}{container}"):
        if _is_item(node, adjust_type, name):
            return node
    if not create:
        return None
    holder = _container_parent(prop, container)
    if holder is None:
        return None
    node = edit.insert_ordered(holder, container)
    if adjust_type:
        edit.insert_ordered(node, "ComparableAdjustmentType").text = adjust_type
    edit.insert_ordered(node, "AdditionalComparisonLineItemIdentifier").text = name
    return node


def _container_parent(prop: etree._Element, container: str):
    """The element an added row hangs from, made if the case has none yet."""
    for fid in ("22.05.18", "23.03.19"):
        for dp in points_for(fid):
            if dp.get("mismo") != "AdditionalComparisonLineItemIdentifier":
                continue
            segs = bind._tail(dp.get("xpath", ""))
            if container not in segs or "PROPERTY" not in segs:
                continue
            upto = segs[segs.index("PROPERTY") + 1:segs.index(container)]
            holder, _ = edit.ensure_path(prop, upto)
            return holder
    return None


def line_item_value(prop: etree._Element, container: str, adjust_type: str,
                    name: str) -> tuple[str, str]:
    """What this property says on that row, and its adjustment."""
    node = line_item_node(prop, container, adjust_type, name)
    if node is None:
        return "", ""
    M_ = f"{{{bind.MISMO}}}"
    text = node.findtext(f"{M_}AdditionalComparisonLineItemDescription", "").strip()
    amount = node.findtext(f"{M_}ComparableAdjustmentAmount", "").strip()
    if amount:
        amount = bind.format_value(amount, "Amount", "+9.0")
    return text, amount


'''

s = s[:start] + NEW + s[end:]

old = """    last_additional: dict[str, int] = {}
    for r in spec:
        if r.label == ADDITIONAL_ROW:
            last_additional[line_item_type(r)] = r.order"""
new = """    last_additional: dict[tuple[str, str], int] = {}
    for r in spec:
        if r.label == ADDITIONAL_ROW:
            last_additional[line_item_place(kind, r)] = r.order"""
assert old in s, "last_additional"
s = s.replace(old, new, 1)

old = """                if row.order != last_additional.get(line_item_type(row)):
                    continue
                # one row per line item the appraiser has named, and -- in the
                # editor -- an empty one to name another
                want = line_item_type(row)
                for name in line_items(root, row, ([subject] if subject is not None else []) + comps):
                    sub_text, _sub_adj = (line_item_value(subject, want, name)
                                          if subject is not None else ("", ""))
                    cells = []
                    for prop in block:
                        text, adj = line_item_value(prop, want, name)
                        cells.append(Cell(text=text, adjustment=adj))
                    grid.rows.append(BuiltRow(
                        name, False, sub_text, cells, bool(row.adjustable),
                        row.subject_fid, row.comp_fid, row.adjust_type, row.adjust_fid,
                        line_item=want, item_name=name))
                if every_row:
                    grid.rows.append(BuiltRow(
                        ADDITIONAL_ROW, False, "", [Cell() for _ in block],
                        bool(row.adjustable), row.subject_fid, row.comp_fid,
                        row.adjust_type, row.adjust_fid, line_item=want, new_item=True))
                continue"""
new = """                where = line_item_place(kind, row)
                if row.order != last_additional.get(where):
                    continue
                container, want = where
                everywhere = ([subject] if subject is not None else []) + comps
                for name in line_items(root, kind, row, everywhere):
                    sub_text, _sub_adj = (line_item_value(subject, container, want, name)
                                          if subject is not None else ("", ""))
                    cells = []
                    for prop in block:
                        text, adj = line_item_value(prop, container, want, name)
                        cells.append(Cell(text=text, adjustment=adj))
                    grid.rows.append(BuiltRow(
                        name, False, sub_text, cells, bool(row.adjustable),
                        row.subject_fid, row.comp_fid, row.adjust_type, row.adjust_fid,
                        line_item=container, item_name=name))
                if every_row:
                    grid.rows.append(BuiltRow(
                        ADDITIONAL_ROW, False, "", [Cell() for _ in block],
                        bool(row.adjustable), row.subject_fid, row.comp_fid,
                        row.adjust_type, row.adjust_fid, line_item=container,
                        new_item=True))
                continue"""
assert old in s, "additional rows"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("ok")
