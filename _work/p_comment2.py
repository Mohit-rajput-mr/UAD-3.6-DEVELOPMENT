import pathlib
def patch(path, old, new):
    p = pathlib.Path(path); s = p.read_text(encoding="utf-8")
    assert old in s, (path, old[:70]); p.write_text(s.replace(old, new, 1), encoding="utf-8")

patch("engine/uad/bind.py", "def _squash(v: str) -> str:",
      '''def commentary_marks(field_id: str, dp: dict) -> dict[str, str]:
    """The category that picks this field's own commentary, if it is one."""
    if not is_commentary(dp):
        return {}
    cat = commentary_category(field_id)
    return {"ValuationAnalysisCategoryType": cat} if cat else {}


def _squash(v: str) -> str:''')

# form.py: one implementation, in bind
f = pathlib.Path("engine/uad/report/form.py"); s = f.read_text(encoding="utf-8")
start = s.index('@lru_cache(maxsize=1)\ndef commentary_categories() -> dict[str, str]:')
end = s.index('ROLE_USE = {', start)
s = s[:start] + 'commentary_categories = bind.commentary_categories\n\n\n' + s[end:]
start = s.index('@lru_cache(maxsize=4096)\ndef commentary_category(fid: str) -> str:')
end = s.index('def _walk(ctx: Ctx, fid: str):', start)
s = s[:start] + 'commentary_category = bind.commentary_category\n\n\n' + s[end:]
f.write_text(s, encoding="utf-8")
