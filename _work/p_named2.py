import pathlib

# ------------------------------------------------------------ comparables.py
p = pathlib.Path("engine/uad/report/comparables.py")
s = p.read_text(encoding="utf-8")

old = """    if row is not None and row.container and scope is not None:
        # an added row keeps its value beside its name, not where the field's
        # own path would otherwise look
        text, _adjust = line_item_value(scope, row.container, row.adjust_type,
                                        row.item_name)
        return text"""
new = """    if row is not None and row.container and scope is not None:
        # a row the appraiser named keeps its value beside that name, not
        # where the field's own path would otherwise look
        named = named_row(row.container_kind, row.subject_fid or row.comp_fid,
                          row.data_point, row.adjust_type)
        if named is not None:
            text, _adjust = named_value(scope, named, row.item_name)
            return text
        return \"\""""
assert old in s, "value_for"
s = s.replace(old, new, 1)

old = """    if row.container:
        _text, amount = line_item_value(prop, row.container, row.adjust_type,
                                        row.item_name)
        return amount"""
new = """    if row.container:
        named = named_row(row.container_kind, row.subject_fid or row.comp_fid,
                          row.data_point, row.adjust_type)
        if named is None:
            return ""
        _text, amount = named_value(prop, named, row.item_name)
        return amount"""
assert old in s, "adjustment_for"
s = s.replace(old, new, 1)

old = """    item_name: str = ""
    container: str = ""
    new_item: bool = False"""
new = """    item_name: str = ""
    container: str = ""
    container_kind: str = ""       # which grid this row belongs to
    new_item: bool = False"""
assert old in s, "GridRow fields"
s = s.replace(old, new, 1)

old = """    out: list[GridRow] = []
    for row in spec:
        if row.label != ADDITIONAL_ROW:
            out.append(row)
            continue
        where = line_item_place(kind, row)
        if row.order != last.get(where):
            continue
        container, adjust_type = where
        for name in line_items(root, kind, row, everywhere):
            out.append(replace(row, label=name, item_name=name,
                               container=container, adjust_type=adjust_type))
        if every_row:
            out.append(replace(row, item_name="", container=container,
                               adjust_type=adjust_type, new_item=True))
    return out"""
new = """    out: list[GridRow] = []
    for row in spec:
        named = named_row(kind, row.subject_fid or row.comp_fid, row.data_point,
                          row.adjust_type)
        if named is None:
            out.append(row)
            continue
        if row.label == ADDITIONAL_ROW and row.order != last.get(
                (named.container, dict(named.marks).get("ComparableAdjustmentType", ""))):
            # every additional row of a grid is kept under one type, so the
            # workbook's several templates for it expand in one place
            continue
        for name in named_values(root, named, everywhere):
            out.append(replace(row, label=name, item_name=name,
                               container=named.container, container_kind=kind))
        if every_row:
            out.append(replace(row, item_name="", container=named.container,
                               container_kind=kind, new_item=True))
    return out"""
assert old in s, "specs body"
s = s.replace(old, new, 1)

old = """    last: dict[tuple[str, str], int] = {}
    for row in spec:
        if row.label == ADDITIONAL_ROW:
            last[line_item_place(kind, row)] = row.order"""
new = """    last: dict[tuple[str, str], int] = {}
    for row in spec:
        if row.label == ADDITIONAL_ROW:
            last[line_item_place(kind, row)] = row.order
    everywhere = ([subject] if subject is not None else []) + props"""
assert old in s, "specs head"
s = s.replace(old, new, 1)
s = s.replace("""    everywhere = ([subject] if subject is not None else []) + props
    spec = rows(kind)""", "    spec = rows(kind)", 1)
p.write_text(s, encoding="utf-8")

# ------------------------------------------------------------------- api.py
p = pathlib.Path("engine/app/api.py")
s = p.read_text(encoding="utf-8")
old = """    if name and any(name == other for other in
                    comparables.line_items(root, kind, _line_row(kind, container), everywhere)
                    if other != was):
        raise HTTPException(422, f"this grid already has a row called {name!r}")
    for prop in everywhere:
        node = comparables.line_item_node(prop, container, adjust_type, was or name,
                                          create=bool(name and not was))
        if node is None:
            if not name:
                continue
            node = comparables.line_item_node(prop, container, adjust_type, name,
                                              create=True)"""
new = """    named = comparables.named_row(kind, *_line_row(kind, container))
    if named is None:
        raise HTTPException(422, f"no added-row template for {container}")
    if name and any(name == other
                    for other in comparables.named_values(root, named, everywhere)
                    if other != was):
        raise HTTPException(422, f"this grid already has a row called {name!r}")
    for prop in everywhere:
        node = comparables.named_node(prop, named, was or name,
                                      create=bool(name and not was))
        if node is None:
            if not name:
                continue
            node = comparables.named_node(prop, named, name, create=True)"""
assert old in s, "route body"
s = s.replace(old, new, 1)

old = """        label = node.find(f"{{{bind.MISMO}}}AdditionalComparisonLineItemIdentifier")
        if label is None:
            label = edit.insert_ordered(node, "AdditionalComparisonLineItemIdentifier")
        label.text = name"""
new = """        label = node.find(f"{{{bind.MISMO}}}{named.name_dp}")
        if label is None:
            label = edit.insert_ordered(node, named.name_dp)
        label.text = name"""
assert old in s, "route label"
s = s.replace(old, new, 1)

old = """def _line_row(kind: str, container: str):
    \"\"\"The workbook's own template for the group kept in this container.\"\"\"
    for row in comparables.rows(kind):
        if row.label == comparables.ADDITIONAL_ROW and \\
                comparables.line_item_place(kind, row)[0] == container:
            return row
    raise HTTPException(422, f"no added-row template for {container}")"""
new = """def _line_row(kind: str, container: str) -> tuple[str, str, str]:
    \"\"\"The workbook's own template for the rows kept in this container.\"\"\"
    for row in comparables.rows(kind):
        fid = row.subject_fid or row.comp_fid
        named = comparables.named_row(kind, fid, row.data_point, row.adjust_type)
        if named is not None and named.container == container:
            return fid, row.data_point, row.adjust_type
    raise HTTPException(422, f"no added-row template for {container}")"""
assert old in s, "_line_row"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("ok")
