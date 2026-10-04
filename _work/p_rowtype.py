import pathlib
def rep(path,old,new):
    p=pathlib.Path(path); s=p.read_text(encoding="utf-8"); assert old in s,(path,old[:70])
    p.write_text(s.replace(old,new,1),encoding="utf-8")

rep("engine/uad/bind.py",
"""def _walk(root: etree._Element, binding: Binding,
          scope: etree._Element | None, ordinal: int):""",
"""def _walk(root: etree._Element, binding: Binding,
          scope: etree._Element | None, ordinal: int,
          marks: dict[str, str] | None = None):""")
rep("engine/uad/bind.py",
"""        explicit = {k: v for k, v in (dp.get("requires") or {}).items()
                    if not k.startswith(("@", "__"))}""",
"""        explicit = {k: v for k, v in (dp.get("requires") or {}).items()
                    if not k.startswith(("@", "__"))}
        # the caller may name the instance itself: three grid rows share one
        # field ID and are told apart by the type their label spells
        explicit.update({k: v for k, v in (marks or {}).items()
                         if any(d.get("mismo") == k for d in binding.data_points)
                         or k in _tail(xpath) or True})""")

rep("engine/uad/report/comparables.py",
'''def value_for(root: etree._Element, field_id: str,
              scope: etree._Element | None) -> str:''',
'''# Three rows of the outbuilding block share one Report Field ID and one data
# point (RoomType); which room each means is spelled by its own label, exactly
# as the utilities rows are ("Gas" is a UtilityType).  So the label is matched
# against the data point's own A-1 enumeration and used to pick the instance.
def _row_marks(row: "GridRow | None", binding) -> dict[str, str]:
    if row is None or not row.data_point or not row.data_point.endswith("Type"):
        return {}
    wanted = [w for w in re.split(r"[^A-Za-z]+", row.label.casefold()) if w]
    if not wanted:
        return {}
    for dp in binding.data_points:
        if dp.get("mismo") != row.data_point:
            continue
        for option in dp.get("enumerations") or []:
            value = option.get("value") or ""
            words = [w.casefold() for w in re.findall(r"[A-Z][a-z]*|[a-z]+", value)]
            if len(wanted) != len(words):
                continue
            if all(any(w.startswith(want.rstrip("s")) for w in words) for want in wanted) \
                    and all(any(w.rstrip("s").startswith(x) or x.startswith(w.rstrip("s"))
                                for x in [want.rstrip("s") for want in wanted]) for w in words):
                return {row.data_point: value}
    return {}


def value_for(root: etree._Element, field_id: str,
              scope: etree._Element | None, row: "GridRow | None" = None) -> str:''')
rep("engine/uad/report/comparables.py",
'''    for name, node in bind._walk(root, pf.binding, scope, 1):''',
'''    for name, node in bind._walk(root, pf.binding, scope, 1, _row_marks(row, pf.binding)):''')
print("ok")
