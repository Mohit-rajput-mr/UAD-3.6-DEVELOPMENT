import pathlib
p=pathlib.Path("engine/uad/report/form.py"); s=p.read_text(encoding="utf-8")
old = '''def _instance_ok(dp: dict, instance: "etree._Element | None") -> bool:
    """Does the row's instance meet the condition A-1 puts on this data point
    (``requires``: ImprovementComponentType = WallsAndCeiling ...)?"""
    if instance is None:
        return True
    for key, want in (dp.get("requires") or {}).items():
        if key.startswith("@") or key.startswith("__"):
            continue
        node = instance.find(f".//{M}{key}")
        if node is None:
            holder = instance.getparent()
            while holder is not None and node is None:
                node = holder.find(f"{M}{key}")
                holder = holder.getparent()
        if node is not None and (node.text or "").strip() != want:
            return False
    return True'''
new = '''# 'IF (AmenityType = "IngroundPool" OR "IngroundSpa" OR "Sauna") AND Exists':
# A-1 writes a choice of several values as one condition, which does not
# reduce to the single key/value pair ``requires`` holds, so it is read here.
CONDITION = re.compile(r'(\w+)\s*=\s*"([^"]+)"((?:\s*OR\s*"[^"]+")*)')
OR_VALUE = re.compile(r'"([^"]+)"')


@lru_cache(maxsize=4096)
def _condition_values(details: str) -> tuple[tuple[str, frozenset[str]], ...]:
    out: dict[str, set[str]] = {}
    for key, first, rest in CONDITION.findall(details or ""):
        out.setdefault(key, set()).update([first] + OR_VALUE.findall(rest))
    return tuple((k, frozenset(v)) for k, v in out.items())


def _instance_ok(dp: dict, instance: "etree._Element | None") -> bool:
    """Does the row's instance meet the condition A-1 puts on this data point
    (``requires``: ImprovementComponentType = WallsAndCeiling ...)?"""
    if instance is None:
        return True
    wanted: dict[str, frozenset[str]] = {
        k: frozenset([v]) for k, v in (dp.get("requires") or {}).items()}
    for key, values in _condition_values(dp.get("conditionality_details") or ""):
        wanted.setdefault(key, values)
    for key, values in wanted.items():
        if key.startswith("@") or key.startswith("__"):
            continue
        node = instance.find(f".//{M}{key}")
        if node is None:
            holder = instance.getparent()
            while holder is not None and node is None:
                node = holder.find(f"{M}{key}")
                holder = holder.getparent()
        if node is not None and (node.text or "").strip() not in values:
            return False
    return True'''
assert old in s; p.write_text(s.replace(old,new,1),encoding="utf-8"); print("ok")
