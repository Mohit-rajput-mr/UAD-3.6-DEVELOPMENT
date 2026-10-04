import pathlib

p = pathlib.Path("engine/uad/report/comparables.py")
s = p.read_text(encoding="utf-8")

# --- one way to reach a field's binding, wherever it is defined --------------
old = '''@lru_cache(maxsize=1)
def _by_field_id() -> dict[str, Any]:'''
new = '''def binding_of(field_id: str):
    """The binding for a grid field.

    The page model only knows the fields the older label-driven renderer laid
    out; the grids ask for plenty it never had a row for (an additional line
    item, a not-used property), and a cell whose binding came back empty read
    and wrote nothing at all -- silently.  A-1's own index answers for those.
    """
    pf = _by_field_id().get(field_id)
    if pf is not None:
        return pf.binding
    return bind.binding_for(field_id)


@lru_cache(maxsize=1)
def _by_field_id() -> dict[str, Any]:'''
assert old in s, "by_field_id"
s = s.replace(old, new, 1)

# --- every reader goes through it ------------------------------------------
old = '''    pf = _by_field_id().get(field_id)
    if pf is None:
        return ""
    groups = []
    marks = _row_marks(row, pf.binding)
    for name, node in bind._walk(root, pf.binding, scope, 1, marks):'''
new = '''    binding = binding_of(field_id)
    if binding is None:
        return ""
    groups = []
    marks = _row_marks(row, binding)
    for name, node in bind._walk(root, binding, scope, 1, marks):'''
assert old in s, "value_for"
s = s.replace(old, new, 1)
s = s.replace('''    shown = bind.display_value([g for _k, g in groups], pf.binding)
    return bind.trim_cents(shown, pf.label)''',
              '''    shown = bind.display_value([g for _k, g in groups], binding)
    return bind.trim_cents(shown, binding.label)''', 1)

old = '''    pf = _by_field_id().get(field_id)
    if pf is None:
        return []
    return [(node.text or "").strip()
            for _name, node in bind._walk(root, pf.binding, scope, 1)
            if (node.text or "").strip()]'''
new = '''    binding = binding_of(field_id)
    if binding is None:
        return []
    return [(node.text or "").strip()
            for _name, node in bind._walk(root, binding, scope, 1)
            if (node.text or "").strip()]'''
assert old in s, "raw_for"
s = s.replace(old, new, 1)

old = '''    pf = _by_field_id().get(field_id)
    if pf is None:
        return []
    unique = {d["mismo"]: d for d in pf.binding.data_points'''
new = '''    binding = binding_of(field_id)
    if binding is None:
        return []
    unique = {d["mismo"]: d for d in binding.data_points'''
assert old in s, "points_for"
s = s.replace(old, new, 1)

old = '''    pf = _by_field_id().get(field_id)
    if pf is None or scope is None:
        return {}
    out: dict[str, str] = {}
    for name, node in bind._walk(root, pf.binding, scope, 1):'''
new = '''    binding = binding_of(field_id)
    if binding is None or scope is None:
        return {}
    out: dict[str, str] = {}
    for name, node in bind._walk(root, binding, scope, 1):'''
assert old in s, "parts_for"
s = s.replace(old, new, 1)

# the adjustment reader too
old = '''        pf = _by_field_id().get(row.adjust_fid)
        if pf is None:
            return (amount.text or "").strip()
        return bind.display_value(
            [[("ComparableAdjustmentAmount", (amount.text or "").strip())]],
            pf.binding)'''
new = '''        binding = binding_of(row.adjust_fid)
        if binding is None:
            return (amount.text or "").strip()
        return bind.display_value(
            [[("ComparableAdjustmentAmount", (amount.text or "").strip())]],
            binding)'''
assert old in s, "adjustment_for"
s = s.replace(old, new, 1)

# --- the line item helpers read A-1 directly --------------------------------
old = '''    fid = row.subject_fid or row.comp_fid
    container = ""
    for dp in points_for(fid):
        if dp.get("mismo") == "AdditionalComparisonLineItemIdentifier":
            container = bind.repeating_container(dp.get("xpath", ""))
            break'''
new = '''    fid = row.subject_fid or row.comp_fid
    binding = binding_of(fid)
    container = ""
    for dp in (binding.data_points if binding else []):
        if dp.get("mismo") == "AdditionalComparisonLineItemIdentifier":
            container = bind.repeating_container(dp.get("xpath", ""))
            break'''
assert old in s, "line_item_place"
s = s.replace(old, new, 1)

old = '''    for fid in ("22.05.18", "23.03.19"):
        for dp in points_for(fid):
            if dp.get("mismo") != "AdditionalComparisonLineItemIdentifier":
                continue'''
new = '''    for fid in ("22.05.18", "23.03.19"):
        binding = binding_of(fid)
        for dp in (binding.data_points if binding else []):
            if dp.get("mismo") != "AdditionalComparisonLineItemIdentifier":
                continue'''
assert old in s, "_container_parent"
s = s.replace(old, new, 1)

p.write_text(s, encoding="utf-8")
print("ok")
