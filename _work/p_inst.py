import pathlib
p=pathlib.Path("engine/uad/edit.py"); s=p.read_text(encoding="utf-8")
old = '''    for key, want in marks_.items():
        paths = _paths_of(key)
        if not paths:
            # A-1 names the gate only as a condition: it sits in the value's
            # own container or one above it, wherever the XSD accepts it
            plan.append((10_000, key, want, None))       # after the instances
            continue'''
new = '''    for key, want in marks_.items():
        paths = _paths_of(key)
        if not paths:
            container = bind.repeating_container(dp.get("xpath", ""))
            if container and key in _order_of(container):
                # The type is not a data point of its own anywhere in A-1 --
                # ValuationAnalysisCategoryType is written only as a condition
                # -- but it sits inside the block this value repeats in, so it
                # names the instance rather than gating a single one.  Treated
                # as a gate it was simply overwritten, and every commentary in
                # the report ended up in the first block, each write erasing
                # the one before it.
                paths = (tuple(segs) + (key,),)
            else:
                # A-1 names the gate only as a condition: it sits in the
                # value's own container or one above it, wherever the XSD
                # accepts it
                plan.append((10_000, key, want, None))   # after the instances
                continue'''
assert old in s; p.write_text(s.replace(old,new,1),encoding="utf-8"); print("ok")
