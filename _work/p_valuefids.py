import pathlib

p = pathlib.Path("engine/uad/report/comparables.py")
s = p.read_text(encoding="utf-8")

old = '''def _next_field_in(container: str, fid: str) -> tuple[str, str]:
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
    return "", ""'''
new = '''def _next_field_in(container: str, fid: str) -> tuple[str, str]:
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


@lru_cache(maxsize=1)
def _roles() -> dict[str, tuple[str, ...]]:
    data = json.loads((SPEC / "field_index.json").read_text(encoding="utf-8"))["fields"]
    return {fid: tuple(entry.get("roles") or []) for fid, entry in data.items()}


def _value_field_for(role: str, value_fid: str, value_dp: str, container: str) -> str:
    """The Report Field ID this role writes the row's value with.

    A-1 gives the subject and each kind of comparable their own identifier for
    the same data point -- the subject's description of an added row is
    22.05.19, a sales comparable's is 22.05.53 -- and a cell that offered the
    subject's identifier to a comparable wrote the value into the subject.
    """
    if role in _roles().get(value_fid, ()):
        return value_fid
    head = value_fid.rsplit(".", 1)[0]
    for fid, roles in _roles().items():
        if role not in roles or not fid.startswith(head + "."):
            continue
        binding = binding_of(fid)
        for dp in (binding.data_points if binding else []):
            if dp.get("mismo") == value_dp and \\
                    bind.repeating_container(dp.get("xpath", "")) == container:
                return fid
    return value_fid'''
assert old in s, "_next_field_in"
s = s.replace(old, new, 1)

# Named gains the two identifiers the grid writes with
old = """    value_fid: str
    inner: tuple = ()       # the path from the repeat down to those values"""
new = """    value_fid: str
    subject_fid: str = ""   # the identifier the subject's cell writes
    comp_fid: str = ""      # the identifier a comparable's cell writes
    inner: tuple = ()       # the path from the repeat down to those values"""
assert old in s, "Named fields"
s = s.replace(old, new, 1)

old = """    segs = bind._tail(dp.get("xpath", ""))
    inner = tuple(segs[segs.index(container) + 1:]) if container in segs else ()
    return Named(container, tuple(sorted(marks.items())), data_point, value_dp,
                 value_fid, inner)"""
new = """    segs = bind._tail(dp.get("xpath", ""))
    inner = tuple(segs[segs.index(container) + 1:]) if container in segs else ()
    comp_role = {"sales": "Sales Comparable", "rental": "Rental Comparable",
                 "grm": "Gross Rent Multiplier Comparable"}.get(kind, "")
    return Named(container, tuple(sorted(marks.items())), data_point, value_dp,
                 value_fid,
                 _value_field_for("Subject Property", value_fid, value_dp, container),
                 _value_field_for(comp_role, value_fid, value_dp, container),
                 inner)"""
assert old in s, "named_row return"
s = s.replace(old, new, 1)

# the expansion gives each named row the identifiers its cells write with
old = """        for name in named_values(root, named, everywhere):
            out.append(replace(row, label=name, item_name=name,
                               container=named.container, container_kind=kind))
        if every_row:
            out.append(replace(row, item_name="", container=named.container,
                               container_kind=kind, new_item=True))"""
new = """        for name in named_values(root, named, everywhere):
            out.append(replace(row, label=name, item_name=name,
                               container=named.container, container_kind=kind,
                               subject_fid=named.subject_fid,
                               comp_fid=named.comp_fid))
        if every_row:
            out.append(replace(row, item_name="", container=named.container,
                               container_kind=kind, new_item=True,
                               subject_fid=named.subject_fid,
                               comp_fid=named.comp_fid))"""
assert old in s, "specs expansion"
s = s.replace(old, new, 1)

# ... and the row now identifies itself by the name it was given
old = """        named = named_row(row.container_kind, row.subject_fid or row.comp_fid,
                          row.data_point, row.adjust_type)
        if named is not None:
            text, _adjust = named_value(scope, named, row.item_name)
            return text
        return \"\""""
new = """        named = row.named
        if named is not None:
            text, _adjust = named_value(scope, named, row.item_name)
            return text
        return \"\""""
assert old in s, "value_for named"
s = s.replace(old, new, 1)

old = """    if row.container:
        named = named_row(row.container_kind, row.subject_fid or row.comp_fid,
                          row.data_point, row.adjust_type)
        if named is None:
            return ""
        _text, amount = named_value(prop, named, row.item_name)
        return amount"""
new = """    if row.container:
        if row.named is None:
            return ""
        _text, amount = named_value(prop, row.named, row.item_name)
        return amount"""
assert old in s, "adjustment_for named"
s = s.replace(old, new, 1)

old = """    item_name: str = ""
    container: str = ""
    container_kind: str = ""       # which grid this row belongs to
    new_item: bool = False"""
new = """    item_name: str = ""
    container: str = ""
    container_kind: str = ""       # which grid this row belongs to
    new_item: bool = False
    named: Any = None              # how the row is stored, when it is a named one"""
assert old in s, "GridRow named"
s = s.replace(old, new, 1)

s = s.replace("""                               subject_fid=named.subject_fid,
                               comp_fid=named.comp_fid))
        if every_row:""",
              """                               subject_fid=named.subject_fid,
                               comp_fid=named.comp_fid, named=named))
        if every_row:""", 1)
s = s.replace("""                               subject_fid=named.subject_fid,
                               comp_fid=named.comp_fid))
    return out""",
              """                               subject_fid=named.subject_fid,
                               comp_fid=named.comp_fid, named=named))
    return out""", 1)
p.write_text(s, encoding="utf-8")
print("ok")
