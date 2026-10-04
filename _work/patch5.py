"""Exhibit pagination, template image stripping, and baseline calibration."""
p = r"engine/uad/report/form.py"
s = open(p, encoding='utf-8').read()


def rep(old, new, count=1):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, count)


# ---- exhibits: one block per row of two, so a run of photos breaks across pages
rep('''            if exhibits:
                out.insert(n + 1, Block("exhibits", section=printed, visible=True,
                                        html=_exhibits_html(exhibits)))''',
    '''            if exhibits:
                for offset, pair in enumerate(_pairs(exhibits)):
                    out.insert(n + 1 + offset,
                               Block("exhibits", section=printed, visible=True,
                                     html=_exhibits_html(pair)))''')
rep('''def _exhibits_html(items: list[dict]) -> str:''',
    '''def _pairs(items: list[dict]) -> list[list[dict]]:
    """Exhibits print two to a row (Appendix E, up to 8 per page)."""
    return [items[i:i + 2] for i in range(0, len(items), 2)]


def _exhibits_html(items: list[dict]) -> str:''')

# ---- baselines: every role carries the offset measured against D-1
rep(":root{{--title-top:0.3pt;--add-top:37.5pt;--sum-top:83.0pt;--lead-after:2.2pt;"
    "--row-text:0.2pt;--ck-top:0.9pt}}",
    ":root{{--title-top:6.6pt;--add-top:40.5pt;--sum-top:86.7pt;--lead-after:2.2pt;\n"
    "       --row-text:2.2pt;--value-text:2.0pt;--ck-top:-1.1pt;--yn-top:1.8pt;\n"
    "       --cell-text:2.15pt;--txc-top:2.2pt;--head-text:2.0pt}}")
rep(".r > span.v{{top:calc(var(--row-text) + 0.3pt)}}", ".r > span.v{{top:var(--value-text)}}")
rep(".hd{{min-height:13pt;line-height:13pt;padding-left:4pt;position:relative}}",
    ".hd{{min-height:13pt;line-height:13pt;padding-left:4pt;position:relative;top:var(--head-text)}}")
rep(".yn{{display:flex;justify-content:flex-end;gap:4.8pt;padding-right:3.3pt;",
    ".yn{{position:relative;top:var(--yn-top);display:flex;justify-content:flex-end;gap:4.8pt;padding-right:3.3pt;")
rep(".txcb1{{line-height:11pt;padding:5.5pt 0 1pt 4pt}}",
    ".txcb1{{line-height:11pt;padding:5.5pt 0 1pt 4pt;position:relative;top:var(--txc-top)}}")
rep(".txcb{{line-height:11pt;padding:3.1pt 0 7.4pt 4pt}}",
    ".txcb{{line-height:11pt;padding:3.1pt 0 7.4pt 4pt;position:relative;top:var(--txc-top)}}")
rep(".txc{{line-height:11pt;padding:3pt 0 2pt 4pt}}",
    ".txc{{line-height:11pt;padding:3pt 0 2pt 4pt;position:relative;top:var(--txc-top)}}")
rep(".txci{{line-height:11pt;padding:5.5pt 0 2pt 4pt;font-style:italic}}",
    ".txci{{line-height:11pt;padding:5.5pt 0 2pt 4pt;font-style:italic;position:relative;top:var(--txc-top)}}")
rep(".txci1{{line-height:11pt;padding:5.5pt 0 2pt 4pt;font-style:italic;max-width:264pt}}",
    ".txci1{{line-height:11pt;padding:5.5pt 0 2pt 4pt;font-style:italic;max-width:264pt;"
    "position:relative;top:var(--txc-top)}}")

# table cells: the text moves, the cell keeps its height
rep("table.tbl th{{font-size:9pt;line-height:10pt;font-weight:700;text-align:left;vertical-align:bottom;",
    "table.tbl th > span,table.tbl td > span{{position:relative;top:var(--cell-text);display:inline-block}}\n"
    "table.tbl th{{font-size:9pt;line-height:10pt;font-weight:700;text-align:left;vertical-align:bottom;")
open(p, 'w', encoding='utf-8').write(s)

# cell contents wrapped so they can be shifted
s = open(p, encoding='utf-8').read()
rep('''def _td(t: str) -> str:
    cls = " class='num'" if re.match(r"^-?\\$[\\d,]", t or "") else ""
    return f"<td{cls}>{t}</td>"''', '''def _td(t: str) -> str:
    cls = " class='num'" if re.match(r"^-?\\$[\\d,]", t or "") else ""
    return f"<td{cls}><span>{t}</span></td>"''')
rep('''    head = ("<thead><tr>" + "".join(f"<th>{esc(h)}</th>" for h in heads) + "</tr></thead>"''',
    '''    head = ("<thead><tr>" + "".join(f"<th><span>{esc(h)}</span></th>" for h in heads) + "</tr></thead>"''')
rep('''                body.append("<tr>" + "".join(_td(t) for t in texts) + "</tr>")''',
    '''                body.append("<tr>" + "".join(_td(t) for t in texts) + "</tr>")''')
rep('''                    body.append("<tr class='tot'>" + (f"<td class='blank' colspan='{n - 2}'></td>" if n > 2 else "")
                                + f"<td class='bar lab'>{esc(text)}</td><td class='bar amt'>{esc(total)}</td></tr>")''',
    '''                    body.append("<tr class='tot'>" + (f"<td class='blank' colspan='{n - 2}'></td>" if n > 2 else "")
                                + f"<td class='bar lab'><span>{esc(text)}</span></td>"
                                  f"<td class='bar amt'><span>{esc(total)}</span></td></tr>")''')
rep('''            pending_bar = f"<tr class='sub'><td colspan='{len(cols)}'>{esc(text)}</td></tr>"''',
    '''            pending_bar = (f"<tr class='sub'><td colspan='{len(cols)}'>"
                           f"<span>{esc(text)}</span></td></tr>")''')
open(p, 'w', encoding='utf-8').write(s)

# ---- a blank case starts with no images at all
q = r"engine/uad/templates.py"
t = open(q, encoding='utf-8').read()
old = '''    removed = 0
    for node in list(root.iter()):'''
assert old in t
t = t.replace(old, '''    removed = 0
    # Images belong to the appraiser, not to the template: a new report starts
    # with none, so the GSE sample's photos never appear in someone's report.
    for images in list(root.iter(f"{{{NS['m']}}}IMAGES")):
        parent = images.getparent()
        if parent is not None:
            parent.remove(images)
            removed += 1
    for node in list(root.iter()):''')
open(q, 'w', encoding='utf-8').write(t)
print("ok")
