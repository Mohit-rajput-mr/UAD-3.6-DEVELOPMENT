import pathlib

p = pathlib.Path("engine/tests/harness.py")
s = p.read_text(encoding="utf-8")

old = """    spec = comparables.rows("sales")
    known = {r.label for r in spec}
    always = {r.label for r in spec if r.always and not r.heading}
    expected = [r.label for r in spec]"""
new = """    # A row the appraiser adds stands in the place of the supplement's own
    # "[Additional Row]" template and is called whatever they named it, so the
    # check reads the expanded rows: everything else must still be the
    # workbook's, in the workbook's order.
    root = tree.getroot() if hasattr(tree, "getroot") else tree
    spec = comparables.specs(root, "sales")
    known = {r.label for r in spec}
    always = {r.label for r in spec if r.always and not r.heading}
    expected = [r.label for r in spec]"""
assert old in s, "grid spec"
s = s.replace(old, new, 1)

old = """    blocks = [g for g in drawn if g.kind == "sales"]
    rows_drawn = sum(len(g.rows) for g in blocks)
    return Result("grid", PASS,
                  f"{len(blocks)} block(s), {rows_drawn} rows, all from the "
                  f"supplement's {len(spec)} and in its order")"""
new = """    blocks = [g for g in drawn if g.kind == "sales"]
    rows_drawn = sum(len(g.rows) for g in blocks)
    added = sum(1 for r in spec if r.item_name)
    named = f", {added} named by the appraiser" if added else ""
    return Result("grid", PASS,
                  f"{len(blocks)} block(s), {rows_drawn} rows, all from the "
                  f"supplement's {len(spec)}{named} and in its order")"""
assert old in s, "grid pass"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("ok")
