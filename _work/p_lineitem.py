import pathlib
p=pathlib.Path("engine/uad/report/comparables.py"); s=p.read_text(encoding="utf-8")

# --- BuiltRow gains what an additional line item needs -----------------------
old = '''    adjust_type: str = ""
    adjust_fid: str = ""

    @property
    def empty(self) -> bool:'''
new = '''    adjust_type: str = ""
    adjust_fid: str = ""
    # An additional comparison line item is a row the appraiser names: B-1
    # gives each group one "[Additional Row]" template and A-1 an Identifier
    # (what the row is called) beside a Description (what each property has).
    line_item: str = ""            # the ComparableAdjustmentType it is kept as
    item_name: str = ""            # the identifier, which is the row's label
    new_item: bool = False         # the empty template that starts another

    @property
    def empty(self) -> bool:'''
assert old in s, "BuiltRow"; s=s.replace(old,new,1)

# --- the identifiers a case already holds, in order -------------------------
helper = '''ADDITIONAL_ROW = "[Additional Row]"


def line_item_type(row: "GridRow") -> str:
    """The ComparableAdjustmentType an additional line item is kept as.

    The adjustable rows carry it in the workbook; the two that cannot be
    adjusted (Vehicle Storage, Outbuilding) name it in A-1's own enumeration
    of adjustment types instead, so it is read from there rather than guessed.
    """
    if row.adjust_type:
        return row.adjust_type
    fid = row.subject_fid or row.comp_fid
    for dp in points_for(fid):
        want = (dp.get("requires") or {}).get("ComparableAdjustmentType")
        if want:
            return want
    kind = "Sales" if (fid or "").startswith("22.") else "Rental"
    return f"{kind}ComparableAdditionalNonAdjustableComparisonItem"


def line_items(root: etree._Element, row: "GridRow", props: list) -> list[str]:
    """Every name given to this group's additional rows, in document order."""
    want = line_item_type(row)
    names: list[str] = []
    for prop in props:
        for node in prop.iter(f"{{{bind.MISMO}}}COMPARABLE_ADJUSTMENT"):
            kind = node.findtext(f"{{{bind.MISMO}}}ComparableAdjustmentType", "").strip()
            if kind != want:
                continue
            name = node.findtext(
                f"{{{bind.MISMO}}}AdditionalComparisonLineItemIdentifier", "").strip()
            if name and name not in names:
                names.append(name)
    return names


def line_item_node(prop: etree._Element, adjust_type: str, name: str,
                   *, create: bool = False):
    """The COMPARABLE_ADJUSTMENT this property keeps that line item in."""
    M_ = f"{{{bind.MISMO}}}"
    for node in prop.iter(f"{M_}COMPARABLE_ADJUSTMENT"):
        if node.findtext(f"{M_}ComparableAdjustmentType", "").strip() != adjust_type:
            continue
        if node.findtext(f"{M_}AdditionalComparisonLineItemIdentifier", "").strip() == name:
            return node
    if not create:
        return None
    holder, _ = edit.ensure_path(prop, ["COMPARABLE", "COMPARABLE_ADJUSTMENTS"])
    node = edit.insert_ordered(holder, "COMPARABLE_ADJUSTMENT")
    edit.insert_ordered(node, "ComparableAdjustmentType").text = adjust_type
    edit.insert_ordered(node, "AdditionalComparisonLineItemIdentifier").text = name
    return node


def line_item_value(prop: etree._Element, adjust_type: str, name: str) -> tuple[str, str]:
    """What this property says on that row, and its adjustment."""
    node = line_item_node(prop, adjust_type, name)
    if node is None:
        return "", ""
    M_ = f"{{{bind.MISMO}}}"
    text = node.findtext(f"{M_}AdditionalComparisonLineItemDescription", "").strip()
    amount = node.findtext(f"{M_}ComparableAdjustmentAmount", "").strip()
    if amount:
        amount = bind.format_value(amount, "Amount", "+9.0")
    return text, amount


def build(tree, kind: str = "sales", *, per_block: int = 3, every_row: bool = False) -> list[Grid]:'''
s=s.replace("def build(tree, kind: str = \"sales\", *, per_block: int = 3, every_row: bool = False) -> list[Grid]:",
            helper, 1)

# --- build(): expand an additional-row template into its named rows ---------
old = '''        for row in spec:
            if row.heading:
                grid.rows.append(BuiltRow(row.label, True, "", []))
                continue
            subject_text = (value_for(root, row.subject_fid, subject, row)'''
new = '''        for row in spec:
            if row.heading:
                grid.rows.append(BuiltRow(row.label, True, "", []))
                continue
            if row.label == ADDITIONAL_ROW:
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
                continue
            subject_text = (value_for(root, row.subject_fid, subject, row)'''
assert old in s, "build rows"; s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8"); print("ok")
