import pathlib
p=pathlib.Path("engine/app/autofill.py"); s=p.read_text(encoding="utf-8")

s=s.replace('''    cat: str = ""
    new: bool = False''','''    cat: str = ""
    new: bool = False
    # A field can be made of several data points -- a name is a first and a
    # last, an address is six -- and the page shows them as one value.  The
    # step stays one step so the filling reads as one action, and carries
    # every write it is made of.
    writes: list[dict] = _field(default_factory=list)''',1)

s=s.replace('''def _raw(root: etree._Element, fid: str, data_point: str = "") -> tuple[str, str]:
    """The value a source document holds for a field: raw, and as it prints."""
    binding = bind.binding_for(fid)
    if binding is None:
        return "", ""
    groups = bind.read_groups(root, binding, ordinal=1)
    parts = [p for g in groups for p in g]
    if data_point:
        parts = [p for p in parts if p[0] == data_point]
        if not parts:
            return "", ""
        return parts[0][1], bind.display_value([parts], binding)
    if not parts:
        return "", ""
    return parts[0][1], bind.display_value(groups, binding)''',
'''def _read(root: etree._Element, fid: str, data_point: str = ""
          ) -> tuple[list[dict], str]:
    """What a source document holds for a field: the writes, and what prints."""
    binding = bind.binding_for(fid)
    if binding is None:
        return [], ""
    groups = bind.read_groups(root, binding, ordinal=1)
    parts = [p for g in groups[:1] for p in g]        # the first instance
    if data_point:
        parts = [p for p in parts if p[0] == data_point]
    if not parts:
        return [], ""
    writes = [{"data_point": name, "value": value} for name, value in parts]
    return writes, bind.display_value([parts], binding)''',1)

s=s.replace('''        value, display = _raw(source, c["fid"], c["data_point"])
        if not value or value == c["text"] or display == c["text"]:
            continue
        if c["kind"] == "check":
            # one box of the run carries the value; the others stay clear
            if c["pick"] != value:
                continue
            display = ""''',
'''        writes, display = _read(source, c["fid"], c["data_point"])
        value = writes[0]["value"] if writes else ""
        if not value or value == c["text"] or display == c["text"]:
            continue
        if c["kind"] == "check":
            # one box of the run carries the value; the others stay clear
            if c["pick"] != value:
                continue
            display = ""
            writes = [{"data_point": writes[0]["data_point"], "value": c["pick"]}]''',1)

s=s.replace('''            value=c["pick"] if c["kind"] == "check" else value,
            display=display, data_point=c["data_point"], key=c["key"],
            sel=c["sel"], row_label=c["row_label"], cat=c["cat"], new=c["new"]))''',
'''            value=c["pick"] if c["kind"] == "check" else value,
            display=display, data_point=c["data_point"], key=c["key"],
            sel=c["sel"], row_label=c["row_label"], cat=c["cat"], new=c["new"],
            writes=writes))''',1)

s=s.replace('''    written, failed = 0, []
    for step in steps:
        try:
            edit.write(tree, step.fid, step.value, data_point=step.data_point)
            written += 1
        except Exception as exc:                       # noqa: BLE001
            failed.append({"n": step.n, "fid": step.fid,
                           "reason": f"{type(exc).__name__}: {exc}"[:160]})
    return {"written": written, "failed": failed}''',
'''    written, failed = 0, []
    for step in steps:
        try:
            for part in (step.writes or [{"data_point": step.data_point,
                                          "value": step.value}]):
                edit.write(tree, step.fid, part["value"],
                           data_point=part.get("data_point", ""))
            written += 1
        except Exception as exc:                       # noqa: BLE001
            failed.append({"n": step.n, "fid": step.fid,
                           "reason": f"{type(exc).__name__}: {exc}"[:160]})
    return {"written": written, "failed": failed}''',1)
p.write_text(s,encoding="utf-8"); print("ok")
