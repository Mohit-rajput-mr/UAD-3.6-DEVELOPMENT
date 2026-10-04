import pathlib

# ---------------------------------------------------------------- the route
p = pathlib.Path("engine/app/api.py")
s = p.read_text(encoding="utf-8")

anchor = '@router.post("/cases/{case_id}/comparables")'
route = '''@router.put("/cases/{case_id}/comparables/lineitems")
def name_line_item(case_id: str, request: Request, body: dict = Body(...)) -> dict:
    """Name, rename or remove a row the appraiser adds to a grid.

    B-1 gives each grid group an "[Additional Row]" the appraiser names --
    "Below Grade Exterior Access" -- and A-1 keeps that name against every
    property the grid shows, so naming it here writes it to the subject and to
    every comparable at once.  Renaming follows the same rule, and an empty
    name removes the row from all of them.
    """
    _case_or_404(case_id)
    st = store()
    tree = st.tree(case_id)
    root = tree.getroot()
    kind = str(body.get("kind") or "sales")
    if kind not in comparables.SHEETS:
        raise HTTPException(400, f"kind must be one of {list(comparables.SHEETS)}")
    container = str(body.get("container") or "")
    adjust_type = str(body.get("adjust_type") or "")
    was = str(body.get("was") or "").strip()
    name = str(body.get("name") or "").strip()
    if not container:
        raise HTTPException(422, "the row does not say where it is kept")
    if not name and not was:
        raise HTTPException(422, "give the row a name")
    _sheet, role, _title = comparables.SHEETS[kind]
    props = comparables.properties(root, role)
    subject = bind.subject(root)
    everywhere = ([subject] if subject is not None else []) + props
    if name and any(name == other for other in
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
                                              create=True)
        if not name:
            node.getparent().remove(node)
            continue
        label = node.find(f"{{{bind.MISMO}}}AdditionalComparisonLineItemIdentifier")
        if label is None:
            label = edit.insert_ordered(node, "AdditionalComparisonLineItemIdentifier")
        label.text = name
    st.save_tree(case_id, tree)
    st.invalidate(case_id, _actor(request), "grid row named")
    st.log(case_id, _actor(request), "edited",
           f"added row {was!r} -> {name!r}" if was else f"added row {name!r}")
    return {"name": name, "removed": not name, "state": st.get(case_id).state}


def _line_row(kind: str, container: str):
    """The workbook's own template for the group kept in this container."""
    for row in comparables.rows(kind):
        if row.label == comparables.ADDITIONAL_ROW and \\
                comparables.line_item_place(kind, row)[0] == container:
            return row
    raise HTTPException(422, f"no added-row template for {container}")


'''
assert anchor in s
s = s.replace(anchor, route + anchor, 1)
p.write_text(s, encoding="utf-8")
print("api ok")
