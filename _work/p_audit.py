import pathlib
p=pathlib.Path("engine/uad/coverage.py"); s=p.read_text(encoding="utf-8")

old = '''        if el.get("data-tf"):
            found[el.get("data-tf")].add("table")
            if el.get("data-tf") and fid is None:
                pass'''
new = '''        if el.get("data-tf"):
            found[el.get("data-tf")].add("table")
        # A fixed row whose instance does not exist yet names the field that
        # identifies it: typing into the row creates the instance with that
        # value, so that field is edited there as surely as the cell is.
        if el.get("data-tsel"):
            found[el.get("data-tsel")].add("table")'''
assert old in s; s=s.replace(old,new,1)

old = '''    if f.expected and f.control in ("text", "pick", "check") and f.control not in f.expected.split("|"):
        f.status, f.reason = INCORRECT, f"A-1 format {f.format} calls for {f.expected}, editor draws {f.control}"
        return'''
new = '''    if (f.expected == "pick" and f.control == "check" and f.boxes > 1):
        # An enumerated value with a box per value is how the URAR asks it --
        # "Condominium / Cooperative / Condop" is a run of tick boxes on the
        # form itself, not a list -- and one box per A-1 value is the same
        # question asked the way C-1 draws it.
        f.status, f.reason = IMPLEMENTED, f"a tick box per A-1 value ({f.boxes})"
        return
    if f.expected and f.control in ("text", "pick", "check") and f.control not in f.expected.split("|"):
        f.status, f.reason = INCORRECT, f"A-1 format {f.format} calls for {f.expected}, editor draws {f.control}"
        return'''
assert old in s; s=s.replace(old,new,1)

s=s.replace('''    rules: int = 0''','''    rules: int = 0
    boxes: int = 0                 # tick boxes drawn for this field''',1)

old = '''        if fid:
            if "pick" in cls.split():
                found[fid].add("pick")
            elif "bx" in cls.split():
                found[fid].add("check")'''
new = '''        if fid:
            if "pick" in cls.split():
                found[fid].add("pick")
            elif "bx" in cls.split():
                found[fid].add("check")
                if el.get("data-pick"):
                    found[fid].add("box:" + el.get("data-pick"))'''
assert old in s; s=s.replace(old,new,1)

old = '''        kinds = controls.get(fid, set())'''
new = '''        kinds = controls.get(fid, set())
        f.boxes = len({k for k in kinds if k.startswith("box:")})'''
assert old in s; s=s.replace(old,new,1)

old = '''        elif kinds - {"source-of-summary"}:
            f.control = sorted(kinds - {"source-of-summary"})[0]'''
new = '''        elif kinds - {"source-of-summary"}:
            plain = {k for k in kinds if not k.startswith(("box:", "source-of"))}
            if plain:
                f.control = sorted(plain)[0]'''
assert old in s; s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8"); print("ok")
