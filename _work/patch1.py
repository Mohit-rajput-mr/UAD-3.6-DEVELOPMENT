p = r"engine/uad/report/form.py"
s = open(p, encoding='utf-8').read()


def rep(old, new, count=1):
    global s
    assert old in s, old[:80]
    s = s.replace(old, new, count)


# ---- fixed rows rewrite
a = s.index("        fixed = any(s.strip() for s in static[:1])")
b = s.index("        # a template row: one line per instance in the case")
new = '''        fixed = any(s.strip() for s in static[:1])
        if fixed:
            label = static[0].strip()
            first_ids = list(cells[0]["ids"])
            selector: set[str] | None = None
            for fid in first_ids:
                b_ = binding(fid)
                keys = [k for k, g in instances(ctx, fid)
                        if any(_norm(v) == _norm(label) for _n, v in g)
                        or (b_ is not None and _norm(bind.display_value(g, b_)) == _norm(label))]
                if keys:
                    selector = set(keys)
                    break
            ids_by_cell = [list(c["ids"]) for c in cells]
            if selector is None and first_ids:
                # the IDs printed over a fixed label belong to the next open cell
                ids_by_cell[0] = []
                target = next((i for i in range(1, len(cells)) if not cells[i]["ids"]), None)
                if target is not None:
                    ids_by_cell[target] = first_ids
            elif selector is not None:
                ids_by_cell[0] = []
            texts, has = [], False
            for n, c in enumerate(cells):
                ids = ids_by_cell[n]
                if n == 0:
                    texts.append(esc(label))
                    continue
                if not ids:
                    texts.append(esc(c.get("text", "")))
                    continue
                head = next((col.get("head", "") for col in cols
                             if abs(col["x0"] - c["x0"]) < 1), "")
                if head in ("Public", "Private"):
                    raws = [v for fid in ids for k, g in instances(ctx, fid)
                            if selector is None or k in selector for _n, v in g]
                    want = "Public" if head == "Public" else "NonPublic"
                    tick = any(r == want for r in raws)
                    has = has or bool(raws)
                    texts.append("<span class='tick'>&#10003;</span>" if tick else "")
                    continue
                vals = []
                for fid in ids:
                    b_ = binding(fid)
                    for k, g in instances(ctx, fid):
                        if selector is not None and k not in selector:
                            continue
                        t = bind.display_value(g, b_) if b_ else ""
                        if t and t not in vals:
                            vals.append(t)
                v = " | ".join(vals)
                has = has or bool(v)
                texts.append(esc(v))
            if has:
                any_data = True
                if pending_bar:
                    body.append(pending_bar)
                    pending_bar = None
                body.append("<tr>" + "".join(_td(t) for t in texts) + "</tr>")
            continue
'''
s = s[:a] + new + s[b:]

rep('''        keys = [k for k in _order_keys(keys)
                if _defect_ok(ctx, k, category, ctx.placeholders.get("base", ""))]''', '''        ddd = any("Recommended Action" in c.get("head", "") for c in cols)
        keys = [k for k in _order_keys(keys)
                if _defect_ok(ctx, k, category, ctx.placeholders.get("base", ""), ddd)]
        counts = [len(g) for g in per_col if g]
        if not ddd and counts and len(set(counts)) == 1 and len(keys) > counts[0]:
            # the columns sit in different containers: pair them by position
            rows_html = []
            for idx in range(counts[0]):
                line = []
                for c, groups in zip(cells, per_col):
                    b_ = binding(c["ids"][0]) if c["ids"] else None
                    line.append(esc(bind.display_value(groups[idx][1], b_)) if groups and b_ else "")
                rows_html.append("<tr>" + "".join(_td(t) for t in line) + "</tr>")
            if rows_html:
                any_data = True
                if pending_bar:
                    body.append(pending_bar)
                    pending_bar = None
                body += rows_html
            continue''')
rep('''                rows_html.append("<tr>" + "".join(f"<td>{t}</td>" for t in line) + "</tr>")''',
    '''                rows_html.append("<tr>" + "".join(_td(t) for t in line) + "</tr>")''')
rep('''def _defect_ok(ctx: Ctx, key: str, category: str, section: str) -> bool:
    try:
        node = ctx.root.getroottree().xpath(key)
    except etree.XPathError:
        return True
    if not node or _local(node[0]) != "DEFECT":
        return True''', '''def _td(t: str) -> str:
    cls = " class='num'" if re.match(r"^-?\\$[\\d,]", t or "") else ""
    return f"<td{cls}>{t}</td>"


def _norm(v: str) -> str:
    return re.sub(r"[^a-z0-9]", "", str(v).casefold())


def _defect_ok(ctx: Ctx, key: str, category: str, section: str, ddd: bool = False) -> bool:
    try:
        node = ctx.root.getroottree().xpath(key)
    except etree.XPathError:
        return not ddd
    if not node or _local(node[0]) != "DEFECT":
        return not ddd''')

a = s.index('            if row.get("align") == "right" and row.get("ids"):')
b = s.index("                continue", a) + len("                continue")
s = s[:a] + '''            if row.get("align") == "right" and row.get("ids"):
                total = text_of(ctx, row["ids"])
                if total and any_data:
                    n = len(cols)
                    body.append("<tr class='tot'>" + (f"<td class='blank' colspan='{n - 2}'></td>" if n > 2 else "")
                                + f"<td class='bar lab'>{esc(text)}</td><td class='bar amt'>{esc(total)}</td></tr>")
                continue''' + s[b:]

rep('''def _walk(ctx: Ctx, fid: str):
    b = binding(fid)
    if b is None:
        return
    yield from bind._walk(ctx.root, b, ctx.scope, 1)''', '''@lru_cache(maxsize=1)
def commentary_categories() -> dict[str, str]:
    """Commentary field -> ValuationAnalysisCategoryType, as B-1 states it.

    Where B-1 does not name the category for a commentary field, the A-1
    enumeration whose name spells the field's label is used (``Site Influence
    Commentary`` -> ``SiteInfluences``).
    """
    path = SPEC / "commentary_categories.json"
    data = json.loads(path.read_text(encoding="utf-8"))["map"] if path.exists() else {}
    rows = json.loads((SPEC / "enumerations.json").read_text(encoding="utf-8"))
    enums = {r["Supported Enumerations"] for r in rows
             if r.get("MISMO Data Point / Attribute Name") == "ValuationAnalysisCategoryType"}
    key = {_norm(e): e for e in enums}
    key.update({_norm(e).rstrip("s"): e for e in enums})
    for fid, entry in _fields().items():
        if fid in data:
            continue
        dps = entry.get("data_points", [])
        if not any(dp.get("mismo") == "ValuationCommentText" and "VALUATION_COMMENTAR" in dp.get("xpath", "")
                   for dp in dps):
            continue
        for loc in entry.get("locations") or []:
            label = loc.get("label", "")
            if label in ("{No Label}", ""):
                label = loc.get("subsection", "")
            stem = _norm(re.sub(r"\\b(Commentary|Analysis of|Analysis|Reconciliation of)\\b", "", label))
            for cand in (stem, stem.rstrip("s"), "site" + stem, stem.replace("view", "siteview")):
                if cand in key:
                    data[fid] = key[cand]
                    break
            if fid in data:
                break
    return data


def _walk(ctx: Ctx, fid: str):
    b = binding(fid)
    if b is None:
        return
    category = commentary_categories().get(fid)
    comment = any(dp.get("mismo") == "ValuationCommentText" and "VALUATION_COMMENTAR" in dp.get("xpath", "")
                  for dp in b.data_points)
    owner = "Owner" in b.label and any((dp.get("requires") or {}).get("PartyRoleType") == "PropertyOwner"
                                       for dp in b.data_points)
    if owner:
        b = bind.Binding(b.field_id, b.section, b.subsection, b.label,
                         [dp for dp in b.data_points
                          if (dp.get("requires") or {}).get("PartyRoleType") == "PropertyOwner"],
                         b.display_rules)
    for name, node in bind._walk(ctx.root, b, ctx.scope, 1):
        if comment and name == "ValuationCommentText":
            if not category:
                continue
            got = node.getparent().findtext(f"{M}ValuationAnalysisCategoryType", "").strip()
            if got != category:
                continue
        yield name, node''')
rep('''        if (name, text) not in groups[key]:
            groups[key].append((name, text))
    return [(k, groups[k]) for k in order]''', '''        unit = node.get("AreaUnitOfMeasureType")
        if unit:
            text = _area(text, unit)
        if (name, text) not in groups[key]:
            groups[key].append((name, text))
    return [(k, groups[k]) for k in order]


AREA_UNITS = {"SquareFeet": "Sq. Ft.", "Acres": "Acres", "SquareMeters": "Sq. M.",
              "Hectares": "Hectares"}


def _area(text: str, unit: str) -> str:
    """An area as the samples print it: '14,950 Sq. Ft.', '10.5 Acres'."""
    try:
        number = float(text)
    except ValueError:
        return f"{text} {AREA_UNITS.get(unit, unit)}"
    shown = f"{number:,.3f}".rstrip("0").rstrip(".")
    return f"{shown} {AREA_UNITS.get(unit, bind._humanise(unit))}"''')

rep('''item = Item("photo", html=_photo_html(src, base, el), visible=bool(src) or sample)''',
    '''item = Item("photo", html=_photo_html(src, base, el), visible=True)''')
rep('''            blk.visible = bool(nxt and nxt.visible) if blk.kind == "italic" else True''', '''            if blk.kind == "italic" and "There are no apparent" in blk.html:
                prv = next((b for b in reversed(blocks[:i]) if b.kind == "table"), None)
                blk.visible = bool(prv is not None and not prv.visible)
            else:
                blk.visible = bool(nxt and nxt.visible) if blk.kind == "italic" else True''')
rep(""".tab{{display:inline-block;background:{INK};color:#fff;height:14.8pt;line-height:14.8pt;
      min-width:144pt;padding:0 16pt 0 6pt;font-weight:700;font-size:9pt;
      border-radius:0 7.5pt 0 0;white-space:nowrap}}""", """.tab{{display:inline-block;background:{INK};color:#fff;height:14.83pt;line-height:14.83pt;
      min-width:144pt;padding:0 14pt 0 6pt;font-weight:700;font-size:9pt;
      border-radius:7.42pt 7.42pt 0 0;white-space:nowrap;vertical-align:bottom}}""")
rep("""table.tbl tr.tot td.bar{{background:#a7a9ac;color:#fff;font-weight:700;text-align:right;border-right:0}}""",
    """table.tbl td.num{{text-align:right}}
table.tbl .tick{{font-size:11pt;line-height:9pt}}
table.tbl tr.tot td.bar{{background:#a7a9ac;color:#fff;font-weight:700;text-align:right;border:0}}""")
open(p, 'w', encoding='utf-8').write(s)
print("patched")
