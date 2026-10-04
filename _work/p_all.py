import pathlib
def rep(path, old, new):
    p=pathlib.Path(path); s=p.read_text(encoding="utf-8")
    assert old in s, (path, old[:70]); p.write_text(s.replace(old,new,1),encoding="utf-8")

rep("engine/uad/bind.py",
    '''    A data point under a PROPERTY belongs to the subject unless told otherwise,
    and a data point inside a repeating block belongs to the ordinal-th
    instance of it.  Returns None when that instance does not exist.
    """''',
    '''    A data point under a PROPERTY belongs to the subject unless told otherwise,
    and a data point inside a repeating block belongs to the ordinal-th
    instance of it.  Returns None when that instance does not exist.

    Ordinal 0 means *every* instance: a grid row that A-1 gives one field ID
    covers all of them, and the samples print them joined -- a comparable's
    outbuilding utilities read "Electricity | Sanitary Sewer | Water", not the
    first one alone.
    """''')
rep("engine/uad/bind.py",
    '''    container = repeating_container(xpath)
    picked = nth_instance(root, container, ordinal, base) if container else None''',
    '''    if ordinal <= 0:
        return base
    container = repeating_container(xpath)
    picked = nth_instance(root, container, ordinal, base) if container else None''')
rep("engine/uad/bind.py",
    '''    if 1 <= ordinal <= len(instances):
        for node in hits[instances[ordinal - 1]]:
            yield name, node''',
    '''    chosen = instances if ordinal <= 0 else (
        [instances[ordinal - 1]] if 1 <= ordinal <= len(instances) else [])
    for key in chosen:
        for node in hits[key]:
            yield name, node''')
rep("engine/uad/report/comparables.py",
    '''    pf = _by_field_id().get(field_id)
    if pf is None:
        return ""
    groups = []
    for name, node in bind._walk(root, pf.binding, scope, 1):''',
    '''    pf = _by_field_id().get(field_id)
    if pf is None:
        return ""
    groups = []
    # ordinal 0: one row of the grid covers every instance of its block, and
    # the samples print them joined with a pipe
    for name, node in bind._walk(root, pf.binding, scope, 0):''')
print("ok")
