import pathlib

p = pathlib.Path("engine/uad/report/comparables.py")
s = p.read_text(encoding="utf-8")

old = """def _is_item(node, named: "Named", name: str = "") -> bool:
    M_ = f"{{{bind.MISMO}}}"
    for key, want in named.marks:
        if node.findtext(f"{M_}{key}", "").strip() != want:
            return False
    got = node.findtext(f"{M_}{named.name_dp}", "").strip()
    return got == name if name else bool(got)"""
new = """def _inside(node, name: str) -> str:
    \"\"\"A value anywhere inside this instance.

    The block that repeats and the block the values sit in are not always the
    same element -- an interior component repeats at INTERIOR_COMPONENT and
    keeps its values in INTERIOR_COMPONENT_DETAIL -- so the search goes down,
    not just one level.
    \"\"\"
    hit = node.find(f"{{{bind.MISMO}}}{name}")
    if hit is None:
        hit = node.find(f".//{{{bind.MISMO}}}{name}")
    return (hit.text or "").strip() if hit is not None else ""


def _is_item(node, named: "Named", name: str = "") -> bool:
    for key, want in named.marks:
        if _inside(node, key) != want:
            return False
    got = _inside(node, named.name_dp)
    return got == name if name else bool(got)"""
assert old in s, "_is_item"
s = s.replace(old, new, 1)

old = """    for name in names:
        pass"""
if old in s:
    s = s.replace(old, "", 1)

old = """            name = node.findtext(f"{{{bind.MISMO}}}{named.name_dp}", "").strip()
            if name not in names:
                names.append(name)"""
new = """            name = _inside(node, named.name_dp)
            if name and name not in names:
                names.append(name)"""
assert old in s, "named_values"
s = s.replace(old, new, 1)

old = """    node = edit.insert_ordered(holder, named.container)
    for key, want in named.marks:
        edit.insert_ordered(node, key).text = want
    edit.insert_ordered(node, named.name_dp).text = name
    return node"""
new = """    node = edit.insert_ordered(holder, named.container)
    inner, _made = edit.ensure_path(node, list(named.inner))
    for key, want in named.marks:
        edit.insert_ordered(inner, key).text = want
    edit.insert_ordered(inner, named.name_dp).text = name
    return node"""
assert old in s, "named_node create"
s = s.replace(old, new, 1)

old = """    node = named_node(prop, named, name)
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
    return text, amount"""
new = """    node = named_node(prop, named, name)
    if node is None:
        return "", ""
    text = _inside(node, named.value_dp)
    binding = binding_of(named.value_fid)
    if text and binding is not None:
        text = bind.display_value([[(named.value_dp, text)]], binding) or text
    amount = _inside(node, "ComparableAdjustmentAmount")
    if amount:
        amount = bind.format_value(amount, "Amount", "+9.0")
    return text, amount"""
assert old in s, "named_value"
s = s.replace(old, new, 1)

# Named carries the path from the repeating block down to the values
old = """@dataclass(frozen=True)
class Named:
    \"\"\"How a row the appraiser names is stored.\"\"\"
    container: str
    marks: tuple            # (element name, value) pairs that identify it
    name_dp: str            # the data point holding the name
    value_dp: str           # the data point holding what each property has
    value_fid: str"""
new = """@dataclass(frozen=True)
class Named:
    \"\"\"How a row the appraiser names is stored.\"\"\"
    container: str
    marks: tuple            # (element name, value) pairs that identify it
    name_dp: str            # the data point holding the name
    value_dp: str           # the data point holding what each property has
    value_fid: str
    inner: tuple = ()       # the path from the repeat down to those values"""
assert old in s, "Named"
s = s.replace(old, new, 1)

old = """    value_fid, value_dp = _next_field_in(container, fid)
    if not value_dp:
        return None
    return Named(container, tuple(sorted(marks.items())), data_point, value_dp, value_fid)"""
new = """    value_fid, value_dp = _next_field_in(container, fid)
    if not value_dp:
        return None
    segs = bind._tail(dp.get("xpath", ""))
    inner = tuple(segs[segs.index(container) + 1:]) if container in segs else ()
    return Named(container, tuple(sorted(marks.items())), data_point, value_dp,
                 value_fid, inner)"""
assert old in s, "named_row return"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("ok")
