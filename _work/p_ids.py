import pathlib
p=pathlib.Path("engine/app/autofill.py"); s=p.read_text(encoding="utf-8")
old = '''    comps: dict[int, tuple[str, int]] = {}      # PROPERTY id -> (kind, column)
    steps: list[Step] = []
    for kind, (_sheet, role, _section) in comparables.SHEETS.items():
        if kind == "not_used":
            continue
        for number, prop in enumerate(comparables.properties(source, role), start=1):
            comps[id(prop)] = (kind, number)'''
new = '''    # keyed by address, never by id(): lxml makes a fresh proxy on each access,
    # so an element's id() is not the same twice and neither is "is"
    comps: dict[str, tuple[str, int]] = {}      # PROPERTY -> (kind, column)
    steps: list[Step] = []
    for kind, (_sheet, role, _section) in comparables.SHEETS.items():
        if kind == "not_used":
            continue
        for number, prop in enumerate(comparables.properties(source, role), start=1):
            comps[tree.getelementpath(prop)] = (kind, number)'''
assert old in s; s=s.replace(old,new,1)

old = '''        column, comp_kind = -1, ""
        for ancestor in node.iterancestors():
            if id(ancestor) in comps:
                comp_kind, column = comps[id(ancestor)]
                break
            if ancestor is subject:
                column = 0            # the grid's subject column
                break'''
new = '''        column, comp_kind = -1, ""
        for ancestor in node.iterancestors():
            if etree.QName(ancestor).localname != "PROPERTY":
                continue
            here = tree.getelementpath(ancestor)
            if here in comps:
                comp_kind, column = comps[here]
            elif here == subject_path:
                column = 0            # the grid's subject column
            break'''
assert old in s; s=s.replace(old,new,1)

old = '''    subject = bind.subject(source)
    have = {'''
new = '''    subject = bind.subject(source)
    subject_path = tree.getelementpath(subject) if subject is not None else ""
    have = {'''
assert old in s; s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8"); print("ok")
