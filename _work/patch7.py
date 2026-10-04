p = r"engine/uad/report/form.py"
s = open(p, encoding='utf-8').read()


def rep(old, new):
    global s
    assert old in s, old[:80]
    s = s.replace(old, new, 1)


rep('NEW_PAGE_SECTIONS = {"Assignment Information", "Sales Comparison Approach",\n'
    '                     "Certifications and Scope of Work"}',
    'NEW_PAGE_SECTIONS = {"Assignment Information", "Sales Comparison Approach",\n'
    '                     "Certifications and Scope of Work"}\n'
    "# Sections whose body is the report's own fixed wording rather than case data.\n"
    'FIXED_TEXT = {"Certifications and Scope of Work", "Certifications"}')
rep('            if base == "Certifications and Scope of Work" and kind in ("head", "prose") \\',
    '            if base in FIXED_TEXT and kind in ("head", "prose") \\')
rep('        if kind == "slot" and base == "Certifications and Scope of Work":',
    '        if kind == "slot" and base in FIXED_TEXT:')
rep('            if base == "Certifications and Scope of Work":\n                continue',
    '            if base in FIXED_TEXT:\n                continue')
rep('''    if prev is not None and prev.kind == "static" and prev.fids == [fid] and not numbered:
        # a paragraph broken across lines in the layout is one paragraph here
        prev.html = prev.html.replace("</div>", f" {esc(text)}</div>")
        return''', '')
rep('''    base = title.split(" - [")[0]
    ctx = ctx.inside(ctx.scope, section=base, base=base)''',
    '''    base = title.split(" - [")[0]
    ctx = ctx.inside(ctx.scope, section=base, base=base, rule_fid="")''')
open(p, 'w', encoding='utf-8').write(s)
print("ok")
