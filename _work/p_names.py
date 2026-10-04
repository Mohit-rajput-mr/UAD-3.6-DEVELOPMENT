import pathlib
p=pathlib.Path("engine/app/autofill.py"); s=p.read_text(encoding="utf-8")
s=s.replace("from uad import bind, edit  # noqa: E402",
            "from uad import bind, edit, parties  # noqa: E402",1)

s=s.replace('''        writes, display = _read(source, c["fid"], c["data_point"])''',
'''        if parties.name_role(c["fid"]) and not c["data_point"]:
            # a party's name is written as a name -- one party per name, the
            # person or the organisation -- not as a first and a last
            display = _party_name(source, c["fid"])
            if display and display != c["text"]:
                steps.append(Step(
                    n=len(steps) + 1, secn=c["secn"],
                    section=c["section"] or names.get(c["secn"], ""),
                    label=_label(c["fid"]), fid=c["fid"], kind=c["kind"],
                    value=display, display=display, writes=[]))
            continue
        writes, display = _read(source, c["fid"], c["data_point"])''',1)

s=s.replace('''            label=bind.binding_for(c["fid"]).label if bind.binding_for(c["fid"]) else "",''',
            '''            label=_label(c["fid"]),''',1)

s=s.replace('''def plan(target: etree._ElementTree, source: etree._Element,''',
'''def _label(fid: str) -> str:
    b = bind.binding_for(fid)
    return b.label if b else ""


def _party_name(source: etree._Element, fid: str) -> str:
    """Every name this party field shows, as the report prints them."""
    binding = bind.binding_for(fid)
    if binding is None:
        return ""
    return bind.display_value(bind.read_groups(source, binding, ordinal=1), binding)


def plan(target: etree._ElementTree, source: etree._Element,''',1)

s=s.replace('''        try:
            for part in (step.writes or [{"data_point": step.data_point,
                                          "value": step.value}]):''',
'''        try:
            if not step.writes and parties.name_role(step.fid):
                parties.write(tree, step.fid, step.value)
                written += 1
                continue
            for part in (step.writes or [{"data_point": step.data_point,
                                          "value": step.value}]):''',1)
p.write_text(s,encoding="utf-8"); print("ok")
