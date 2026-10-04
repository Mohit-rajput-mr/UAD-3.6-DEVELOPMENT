import pathlib

p = pathlib.Path("engine/uad/report/comparables.py")
s = p.read_text(encoding="utf-8")

# BuiltRow keeps what the editor needs to name the row it came from
old = """            built = BuiltRow(row.label, False, subject_text, cells, bool(row.adjustable),
                             row.subject_fid, row.comp_fid, row.adjust_type, row.adjust_fid)"""
new = """            built = BuiltRow(row.label, False, subject_text, cells, bool(row.adjustable),
                             row.subject_fid, row.comp_fid, row.adjust_type, row.adjust_fid,
                             line_item=row.container, item_name=row.item_name,
                             new_item=row.new_item)"""
assert old in s, "BuiltRow build"
s = s.replace(old, new, 1)

# an added row is shown whenever it is named, and the empty template always in
# the editor: its own rule, because the workbook's "if relevant" cannot know
old = """            if not every_row and not (row.always or adjusted or any(map(_told, comp_raw))
                                      or (row.if_applicable and any(map(_told, subject_raw)))):
                continue"""
new = """            if row.container:
                grid.rows.append(built)
                continue
            if not every_row and not (row.always or adjusted or any(map(_told, comp_raw))
                                      or (row.if_applicable and any(map(_told, subject_raw)))):
                continue"""
assert old in s, "visibility"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")

# ---------------------------------------------------------------- the route
p = pathlib.Path("engine/app/api.py")
s = p.read_text(encoding="utf-8")
old = """    rows = []
    for spec in comparables.rows(kind):"""
new = """    rows = []
    for spec in comparables.specs(root, kind, every_row=True):"""
assert old in s, "route rows"
s = s.replace(old, new, 1)
old = """            "adjust_type": spec.adjust_type,"""
new = """            "adjust_type": spec.adjust_type,
            "item_name": spec.item_name,
            "container": spec.container,
            "new_item": spec.new_item,"""
assert old in s, "route fields"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("ok")
