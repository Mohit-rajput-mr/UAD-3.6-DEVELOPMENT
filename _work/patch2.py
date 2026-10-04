p = r"engine/uad/report/form.py"
s = open(p, encoding='utf-8').read()


def rep(old, new, count=1):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, count)


# 1. resolve: IDs with no data points fall back to the label too
rep('''    out = []
    for fid in ids:
        if fid in _fields():
            out.append(fid)
            continue''', '''    out = []
    for fid in ids:
        if fid in _fields() and _fields()[fid].get("data_points"):
            out.append(fid)
            continue''')

# 2. generated statements (B-1 p372-373) + owner + roles, inside text_of
rep('''def text_of(ctx: Ctx, ids: Iterable[str], sep: str = " | ") -> str:
    parts: list[str] = []''', '''# B-1 "Reconciliation: Final Value Condition Statement" (pp372-373)
FINAL_VALUE_TEXT = {
    "SubjectToCompletionPerPlans": "subject to completion per plans and specifications on the basis of a "
                                   "hypothetical condition that the improvements have been completed",
    "SubjectToInspection": "subject to the itemized list of required inspections below based on the "
                           "extraordinary assumption that the condition or deficiency does not require "
                           "alteration or repair",
    "SubjectToRepair": "subject to the itemized list of repairs recommended below on the basis of a "
                       "hypothetical condition that the repairs or alterations have been completed in a "
                       "professional manner",
}


def final_value_statement(ctx: Ctx) -> str:
    values = [(n.text or "").strip() for n in ctx.root.iter(f"{M}PropertyValuationConditionalConclusionType")]
    parts = [FINAL_VALUE_TEXT[v] for v in values if v in FINAL_VALUE_TEXT]
    if not parts:
        return ""
    return f"This appraisal is made {', and '.join(parts)}. This might have affected the assignment results."


def text_of(ctx: Ctx, ids: Iterable[str], sep: str = " | ") -> str:
    parts: list[str] = []''')

# owner: read parties that carry the PropertyOwner role directly
rep('''    if owner:
        b = bind.Binding(b.field_id, b.section, b.subsection, b.label,
                         [dp for dp in b.data_points
                          if (dp.get("requires") or {}).get("PartyRoleType") == "PropertyOwner"],
                         b.display_rules)''', '''    if owner:
        names = {dp.get("mismo") for dp in b.data_points
                 if (dp.get("requires") or {}).get("PartyRoleType") == "PropertyOwner"}
        for party in ctx.root.iter(f"{M}PARTY"):
            roles = [(r.text or "").strip() for r in party.iter(f"{M}PartyRoleType")]
            if "PropertyOwner" not in roles:
                continue
            for node in party.iter():
                if isinstance(node.tag, str) and _local(node) in names and (node.text or "").strip():
                    yield _local(node), node
        return
    roles = _fields().get(fid, {}).get("roles") or []
    if ctx.scope is None and roles and "Subject Property" not in roles and any(
            "PROPERTIES/PROPERTY" in dp.get("xpath", "") for dp in b.data_points):
        uses = {ROLE_USE.get(r, "") for r in roles}
        for prop in ctx.root.iter(f"{M}PROPERTY"):
            if prop.get("ValuationUseType") in uses:
                yield from bind._walk(ctx.root, b, prop, 1)
        return''')
rep('''def _walk(ctx: Ctx, fid: str):
    b = binding(fid)''', '''ROLE_USE = {"Sales Comparable": "SalesComparable", "Land Comparable": "LandComparable",
            "Rental Comparable": "RentalComparable",
            "Gross Rent Multiplier Comparable": "GrossRentMultiplierComparable",
            "Property Analyzed Not Used": "PropertyAnalyzedNotUsed",
            "Subject Property": "SubjectProperty"}


def _walk(ctx: Ctx, fid: str):
    b = binding(fid)''')

# prose using the generated statement
rep('''            value = text_of(ctx, resolve(ids, el.get("text", "")), " ")
            out.append(Block("prose"''', '''            value = text_of(ctx, resolve(ids, el.get("text", "")), " ")
            if label == "Final Value Condition Statement":
                value = final_value_statement(ctx)
            out.append(Block("prose"''')

# 3. amounts: whole-dollar figures print without cents (as the samples do)
rep('''def shown(ctx: Ctx, fid: str) -> list[str]:
    """The printed text for a field: one entry per instance it holds."""
    b = binding(fid)
    if b is None:
        return []
    out = []
    for _key, group in instances(ctx, fid):
        text = bind.display_value(group, b)
        if text:
            out.append(text)
    return out''', '''def shown(ctx: Ctx, fid: str) -> list[str]:
    """The printed text for a field: one entry per instance it holds."""
    b = binding(fid)
    if b is None:
        return []
    out = []
    per = "Per " in (b.label or "")
    for _key, group in instances(ctx, fid):
        text = bind.display_value(group, b)
        if text and not per:
            text = re.sub(r"(\\$[\\d,]+)\\.00\\b", r"\\1", text)
        if text:
            out.append(text)
    return out''')

# 4. DDD "None" when the section says it has no defects
rep('''def _td(t: str) -> str:''', '''def _no_defects(ctx: Ctx, el: dict) -> bool:
    """B-1: a section's DDD shows "None" when its DefectsExistIndicator is false."""
    for row in el["rows"]:
        for c in row["cells"]:
            for fid in c["ids"]:
                for dp in _fields().get(fid, {}).get("data_points", []):
                    for k in (dp.get("requires") or {}):
                        if k.endswith("DefectsExistIndicator"):
                            scope = ctx.scope if ctx.scope is not None else subject(ctx)
                            node = scope.find(f".//{M}{k}") if scope is not None else None
                            return node is not None and (node.text or "").strip() == "false"
    return False


def _td(t: str) -> str:''')
rep('''    if not any_data:
        return "", False''', '''    if not any_data:
        if any("Recommended Action" in c.get("head", "") for c in cols) and _no_defects(ctx, el):
            return "<div class='txc none'>None</div>", True
        return "", False''')

# 5. utilities: template row skips instances claimed by fixed rows
rep('''    category = ctx.placeholders.get("section", "")
''', '''    category = ctx.placeholders.get("section", "")
    claimed: set[str] = set()
''')
rep('''                if keys:
                    selector = set(keys)
                    break''', '''                if keys:
                    selector = set(keys)
                    claimed.update(keys)
                    break''')
rep('''        ddd = any("Recommended Action" in c.get("head", "") for c in cols)
        keys = [k for k in _order_keys(keys)''', '''        ddd = any("Recommended Action" in c.get("head", "") for c in cols)
        keys = [k for k in _order_keys(keys) if k not in claimed and not any(
                    k.startswith(c + "/") or c.startswith(k + "/") for c in claimed)]
        keys = [k for k in keys''')

# 6. photo placeholder with camera glyph, offset as C-1 places it
rep('''    what = {"Summary": "Subject Property", "Dwelling Exterior": "Dwelling Front"}.get(section, section)
    return (f"<div class='photo empty' style='height:{h:.1f}pt'>"
            f"<span>This is where the {esc(what)} photo would display.</span></div>")''', '''    what = {"Summary": "Subject Property", "Dwelling Exterior": "Dwelling Front"}.get(section, section)
    return (f"<div class='photo empty' style='height:{h:.1f}pt'>{CAMERA}"
            f"<span>This is where the {esc(what)} photo would display.</span></div>")


CAMERA = ("<svg class='cam' viewBox='0 0 24 20' width='20pt' height='16pt'>"
          "<path d='M8 1h8l2 3h4a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2H2a2 2 0 0 1-2-2V6a2 2 0 0 1 2-2h4z' fill='#939598'/>"
          "<circle cx='12' cy='11.5' r='5.2' fill='#e6e7e8'/><circle cx='12' cy='11.5' r='3.6' fill='#939598'/>"
          "</svg>")''')
rep('''.photo.empty span{{font-style:italic;color:#939598}}''', '''.photo.empty{{flex-direction:column;gap:9pt}}
.photo.empty span{{font-style:italic;color:#939598}}
.col.right .photo{{margin-top:13.6pt}}
.col.right .r + .photo{{margin-top:13.6pt}}''')
rep('''            f"<span>This is where the {esc(it['title'] or 'exhibit')} photo would display.</span></div>")''' if False else '''               f"<div class='ph'>This is where the {esc(it['title'] or 'exhibit')} photo would display.</div>")''',
    '''               f"<div class='ph'>{CAMERA}<span>This is where the {esc(re.sub(r' *[(].*', '', it['title'] or 'exhibit'))} photo would display.</span></div>")''')
rep('''.ex .ph{{flex:1;background:{BAR};display:flex;align-items:center;justify-content:center;''',
    '''.ex .ph{{flex:1;background:{BAR};display:flex;flex-direction:column;gap:9pt;align-items:center;justify-content:center;''')
rep('''              padding:0 4pt 1.3pt 4pt;border-bottom:{rule}}}''', '''              padding:0 0 1.3pt 4pt;border-bottom:{rule}}}''')
open(p, 'w', encoding='utf-8').write(s)
print("patched")
