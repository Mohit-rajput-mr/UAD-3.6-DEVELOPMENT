"""Section display rules from B-1, and the fixed Certifications / Scope text."""
p = r"engine/uad/report/form.py"
s = open(p, encoding='utf-8').read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


rep("from . import comparables, fonts, page, typography",
    "from . import comparables, fonts, page, rules, typography")

# --- B-1's per-section display rules -------------------------------------
rep('''# ---------------------------------------------------------------------------
# Reading the case
# ---------------------------------------------------------------------------''',
    '''@lru_cache(maxsize=1)
def section_rules() -> dict[str, str]:
    """Each section's display rule, as B-1's section overview states it."""
    path = SPEC / "section_rules.json"
    return json.loads(path.read_text(encoding="utf-8"))["rules"] if path.exists() else {}


def section_shown(ctx: "Ctx", section: str) -> bool | None:
    """True/False from B-1's rule, or None when the rule needs the content.

    Project Information is the one rule B-1 writes in prose rather than in data
    points ("displays when the property is in a project ... or in a PUD"), so
    the three indicators it names are read directly.
    """
    if section == "Project Information":
        for name in ("PropertyInProjectIndicator", "PUDIndicator"):
            if any(v == "true" for v in rules.values_of(ctx.root, name)):
                return True
        legal = rules.values_of(ctx.root, "ProjectLegalStructureType")
        return bool([v for v in legal if v and v != "None"])
    rule = section_rules().get(section)
    if not rule:
        return None
    decided = rules.evaluate(rule, ctx.root)
    return decided.shown if decided.known else None


# ---------------------------------------------------------------------------
# Reading the case
# ---------------------------------------------------------------------------''')

# --- gate each section ----------------------------------------------------
rep('''    blocks: list[Block] = []
    for title, els in sections:
        for sctx, printed in section_instances(ctx, title):
            blocks += _section(title, printed, els, sctx, sample=sample)''',
    '''    blocks: list[Block] = []
    for title, els in sections:
        base = title.split(" - [")[0]
        if section_shown(ctx, base) is False:
            continue
        for sctx, printed in section_instances(ctx, title):
            blocks += _section(title, printed, els, sctx, sample=sample)''')

# --- the fixed text of Certifications and Scope of Work -------------------
rep('''        if kind in ("row", "head", "check", "prose"):
            item = _column_item(el, ctx)
            if column == "full" and kind == "head":
                flush()
                if base == "Certifications and Scope of Work":
                    out.append(Block("static", section=printed, decoration=True,
                                     html=f"<div class='txc'>{esc(el['text'])}</div>"))
                continue''',
    '''        if kind in ("row", "head", "check", "prose"):
            item = _column_item(el, ctx)
            if base == "Certifications and Scope of Work" and kind in ("head", "prose") \\
                    and not el.get("bold", False):
                flush()
                _fixed_text(out, printed, el, ctx)
                continue
            if column == "full" and kind == "head":
                flush()
                continue''')
rep('''        if kind == "slot":''',
    '''        if kind == "slot" and base == "Certifications and Scope of Work":
            # a slot in the margin opens the paragraph that follows it; it
            # carries the rule that decides whether the paragraph prints
            if el.get("x0", 99) < 46:
                ctx.placeholders["rule_fid"] = (el.get("ids") or [""])[0]
                continue
        if kind == "slot":''')

rep('''def _party_item(el: dict, ctx: Ctx) -> Item:''',
    '''NUMBER = re.compile(r"^\\d{1,2}\\.$")


def _fixed_text(out: list[Block], printed: str, el: dict, ctx: Ctx) -> None:
    """One paragraph of the report's own fixed wording.

    The Certifications and Scope of Work pages are wording the GSEs set, not
    data: C-1 marks each paragraph with a slot in the margin whose field
    carries the display rule (``Always displays``, or a condition on the
    assignment), and the paragraph prints only when that rule says so.
    """
    text = " ".join(str(el.get("text", "")).split())
    if not text:
        return
    fid = ctx.placeholders.get("rule_fid", "")
    shown = True
    entry = _fields().get(fid, {})
    for rule in entry.get("display_rules", []):
        decided = rules.evaluate(rule.get("rule", ""), ctx.root)
        if decided.known:
            shown = decided.shown
            break
    numbered = bool(NUMBER.match(text))
    prev = out[-1] if out else None
    if prev is not None and prev.kind == "static" and prev.fids == [fid] and not numbered:
        # a paragraph broken across lines in the layout is one paragraph here
        prev.html = prev.html.replace("</div>", f" {esc(text)}</div>")
        return
    cls = "txc np" if numbered else "txc"
    out.append(Block("static", section=printed, visible=shown, fids=[fid],
                     html=f"<div class='{cls}'>{esc(text)}</div>"))


def _party_item(el: dict, ctx: Ctx) -> Item:''')

# a static block's visibility is its own; do not let the decoration pass reset it
rep('''    # a static paragraph section (Scope of Work, Certifications) always prints
    for blk in blocks:
        if blk.kind == "static":
            blk.visible = True''', '''''')
rep('''    for i, blk in enumerate(blocks):
        if blk.decoration:''', '''    for i, blk in enumerate(blocks):
        if blk.kind == "static":
            continue
        if blk.decoration:''')
rep(""".txc{{line-height:11pt;padding:3pt 0 2pt 4pt;position:relative;top:var(--txc-top)}}""",
    """.txc{{line-height:11pt;padding:3pt 0 2pt 4pt;position:relative;top:var(--txc-top)}}
.txc.np{{padding-left:13pt;text-indent:-9pt}}""")
open(p, 'w', encoding='utf-8').write(s)
print("ok")
