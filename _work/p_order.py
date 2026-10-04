import pathlib
p=pathlib.Path("engine/app/autofill.py"); s=p.read_text(encoding="utf-8")

old = '''        control = drawn.get(fid, {})
        if control.get("secn"):
            secn, section = control["secn"], control["section"]
        elif fid:
            b = bind.binding_for(fid)
            number = form.SECTION_NUMBER.get(b.section if b else "", 0)
            if number:
                secn, section = number, (b.section if b else "")'''
new = '''        control = drawn.get(fid, {})
        # Which section the value is entered in: the section the editor draws
        # its control in, else the section A-1 locates the field in.  A value
        # A-1 does not locate (an image's MIME type) belongs with the value
        # before it, which is the block it sits in.
        if control.get("secn"):
            secn, section = control["secn"], control["section"]
        elif fid:
            b = bind.binding_for(fid)
            number = form.SECTION_NUMBER.get(b.section if b else "", 0)
            if number:
                secn, section = number, (b.section if b else "")'''
assert old in s; s=s.replace(old,new,1)

old = '''    steps += _photo_steps(media, len(steps))
    for n, step in enumerate(steps, start=1):
        step.n = n
    return steps'''
new = '''    steps += _photo_steps(media, len(steps))
    # In report order, because that is the order an appraiser fills it in.
    # Inside a section the document's own order is kept, except that a
    # comparable is created before anything is written into its column.
    order = {step: n for n, step in enumerate(steps)}
    steps.sort(key=lambda x: (x.secn or 99, 0 if x.kind == COMP else 1, order[x]))
    for n, step in enumerate(steps, start=1):
        step.n = n
    return steps'''
assert old in s; s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8"); print("ok")
