import pathlib
p=pathlib.Path("engine/uad/edit.py"); s=p.read_text(encoding="utf-8")
def rep(old,new):
    global s
    assert old in s, old[:60]
    s=s.replace(old,new,1)

rep('''def _marks(dp: dict) -> dict[str, str]:
    marks = {k: v for k, v in (dp.get("requires") or {}).items()
             if not k.startswith(("@", "__")) and re.match(r"^[A-Za-z]\w*$", k)}
    if "PARTIES/PARTY/" in dp.get("xpath", ""):''',
    '''def _marks(dp: dict, field_id: str = "") -> dict[str, str]:
    marks = {k: v for k, v in (dp.get("requires") or {}).items()
             if not k.startswith(("@", "__")) and re.match(r"^[A-Za-z]\w*$", k)}
    # a commentary box is told from every other one by its category, so a write
    # that does not carry the category overwrites whichever comment came first
    marks.update(bind.commentary_marks(field_id, dp))
    if "PARTIES/PARTY/" in dp.get("xpath", ""):''')

rep('    if leaf is not None and not bind.instance_has(leaf, own or _marks(dp)):',
    '    marks = _marks(dp, field_id)\n'
    '    if leaf is not None and not bind.instance_has(leaf, own or marks):')
rep('    if leaf is None and ordinal == 1 and _marks(dp):',
    '    if leaf is None and ordinal == 1 and marks:')
rep('        scope = instance_for(root, dp, scope)',
    '        scope = instance_for(root, dp, scope, field_id)')
rep('''def instance_for(root: etree._Element, dp: dict,
                 scope: etree._Element | None = None) -> etree._Element | None:''',
    '''def instance_for(root: etree._Element, dp: dict,
                 scope: etree._Element | None = None,
                 field_id: str = "") -> etree._Element | None:''')
rep('    marks_ = _marks(dp)', '    marks_ = _marks(dp, field_id)')
p.write_text(s,encoding="utf-8"); print("ok")
