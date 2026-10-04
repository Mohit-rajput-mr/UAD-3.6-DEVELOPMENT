import re, pathlib
def patch(path, old, new, count=1):
    p = pathlib.Path(path); s = p.read_text(encoding="utf-8")
    assert s.count(old) >= count, (path, old[:70])
    p.write_text(s.replace(old, new, count), encoding="utf-8")

# ---------------------------------------------------------------- bind.py
bind_new = '''
# ------------------------------------------------------------- commentary
# Every commentary box in the report writes the same data point,
# ValuationCommentText, into the same repeating block, VALUATION_COMMENTARY.
# What tells one box from another is the ValuationAnalysisCategoryType beside
# it, so a read that ignores the category shows the wrong comment and a write
# that ignores it overwrites one.  B-1 names the category for the fields it
# discusses; where it does not, the A-1 enumeration whose name spells the
# field's own label is used ("Site Influence Commentary" -> SiteInfluences).


@lru_cache(maxsize=1)
def commentary_categories() -> dict[str, str]:
    path = SPEC / "commentary_categories.json"
    data = json.loads(path.read_text(encoding="utf-8"))["map"] if path.exists() else {}
    rows = json.loads((SPEC / "enumerations.json").read_text(encoding="utf-8"))
    enums = {r["Supported Enumerations"] for r in rows
             if r.get("MISMO Data Point / Attribute Name") == "ValuationAnalysisCategoryType"}
    key = {_squash(e): e for e in enums}
    key.update({_squash(e).rstrip("s"): e for e in enums})
    for fid, entry in _index().items():
        if fid in data:
            continue
        if not any(is_commentary(dp) for dp in entry.get("data_points", [])):
            continue
        for loc in entry.get("locations") or []:
            label = loc.get("label", "")
            if label in (NO_LABEL, ""):
                label = loc.get("subsection", "")
            stem = _squash(re.sub(r"\b(Commentary|Analysis of|Analysis|Reconciliation of)\b", "", label))
            for cand in (stem, stem.rstrip("s"), "site" + stem, stem.replace("view", "siteview")):
                if cand in key:
                    data[fid] = key[cand]
                    break
            if fid in data:
                break
    return data


def is_commentary(dp: dict) -> bool:
    """Does this data point sit in a categorised VALUATION_COMMENTARY?"""
    return "VALUATION_COMMENTAR" in (dp.get("xpath") or "")


@lru_cache(maxsize=4096)
def commentary_category(field_id: str) -> str:
    known = commentary_categories().get(field_id)
    if known:
        return known
    for dp in (_index().get(field_id) or {}).get("data_points") or []:
        if is_commentary(dp):
            cat = (discriminators().get(dp.get("context", ""), {}) or {}).get(
                "ValuationAnalysisCategoryType")
            if cat:
                return cat
    return ""


def _squash(v: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(v).casefold())


'''
patch("engine/uad/bind.py", "def _walk(root: etree._Element, binding: Binding,",
      bind_new.lstrip("\n") + "def _walk(root: etree._Element, binding: Binding,")

patch("engine/uad/bind.py",
      """        marks = dict(dp.get("requires") or {})
        if not marks and not repeating_container(xpath):
            marks = discriminators().get(dp.get("context", ""), {})""",
      """        marks = dict(dp.get("requires") or {})
        if not marks and not repeating_container(xpath):
            marks = discriminators().get(dp.get("context", ""), {})
        marks.update(commentary_marks(binding.field_id, dp))""")

# the same filter has to reach the two branches that return early
patch("engine/uad/bind.py",
      """        if explicit and container:""",
      """        explicit.update(commentary_marks(binding.field_id, dp))
        if explicit and container:""")
