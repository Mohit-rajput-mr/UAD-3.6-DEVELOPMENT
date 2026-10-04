import pathlib
p = pathlib.Path("engine/uad/edit.py"); s = p.read_text(encoding="utf-8")
old = '''def _binding_for(field_id: str) -> bind.Binding:
    for fields in bind.page_model().values():
        for pf in fields:
            if pf.field_id == field_id:
                return pf.binding
    raise KeyError(f"no field {field_id} on the page")'''
new = '''def _binding_for(field_id: str) -> bind.Binding:
    """The binding for a Report Field ID.

    The page model covers the fields the older renderer laid out by label.  The
    report is now drawn from C-1, which places fields that model never had a
    row for -- every commentary box, the defect indicators, the instance
    identifiers -- so a field it does not know is bound straight from A-1's own
    index rather than refused.
    """
    for fields in bind.page_model().values():
        for pf in fields:
            if pf.field_id == field_id:
                return pf.binding
    b = bind.binding_for(field_id)
    if b is None:
        raise KeyError(f"no field {field_id} on the page")
    return b'''
assert old in s
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")

# bind.binding_for: the same binding form.py builds, in one place
p = pathlib.Path("engine/uad/bind.py"); s = p.read_text(encoding="utf-8")
anchor = "def commentary_marks(field_id: str, dp: dict) -> dict[str, str]:"
add = '''@lru_cache(maxsize=4096)
def binding_for(field_id: str) -> "Binding | None":
    """A binding built straight from A-1's index, for any Report Field ID."""
    entry = _index().get(field_id)
    if not entry or not entry.get("data_points"):
        return None
    loc = (entry.get("locations") or [{}])[0]
    return Binding(field_id=field_id, section=loc.get("section", ""),
                   subsection=loc.get("subsection", ""), label=loc.get("label", ""),
                   data_points=entry["data_points"],
                   display_rules=entry.get("display_rules", []))


'''
assert anchor in s
p.write_text(s.replace(anchor, add + anchor, 1), encoding="utf-8")
print("ok")
