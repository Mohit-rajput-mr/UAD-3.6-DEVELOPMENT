import re
p = r"engine/uad/report/form.py"
s = open(p, encoding='utf-8').read()


def rep(old, new):
    global s
    assert old in s, old[:80]
    s = s.replace(old, new)


# lead: fixed geometry from Appendix E (TITLE / TITLE-ADD / SUM-HD) as D-1 places it
a = s.index(".title{{font-size:32pt")
b = s.index(".tabwrap{{")
s = s[:a] + """.lead{{position:relative;height:104pt;border-bottom:2pt solid {INK};margin-bottom:var(--lead-after)}}
.title{{position:absolute;left:0;top:var(--title-top);font-size:32pt;line-height:32pt;font-weight:400;white-space:nowrap}}
.title-add{{position:absolute;left:0;top:var(--add-top);font-size:12pt;line-height:12pt;font-weight:700;
            letter-spacing:.012em;white-space:nowrap}}
.sum-hd{{position:absolute;left:4pt;top:var(--sum-top);font-size:14pt;line-height:14pt;font-weight:700;
         letter-spacing:.03em}}

""" + s[b:]

# rows on a strict 13 pt pitch with the rule drawn at the foot of each line
rep(""".r{{display:flex;min-height:13pt;line-height:11pt;padding-top:1.9pt;border-bottom:{rule}}}
.r .lb{{width:141pt;flex:none;padding-left:4pt}}""", """.r{{display:flex;min-height:13pt;line-height:13pt;position:relative}}
.r::after{{content:'';position:absolute;left:0;right:0;bottom:0;border-top:{rule}}}
.r > span{{position:relative;top:var(--row-text)}}
.r .lb{{width:145pt;flex:none;padding-left:4pt}}""")
rep(""".hd{{min-height:13pt;line-height:11pt;padding-top:1.9pt;padding-left:4pt}}""",
    """.hd{{min-height:13pt;line-height:13pt;padding-left:4pt;position:relative}}
.hd > *,.hd{{}}
.hd span{{position:relative}}""")
rep(""".hd.ruled{{border-bottom:{rule}}}""", """.hd.ruled::after{{content:'';position:absolute;left:0;right:0;bottom:0;border-top:{rule}}}""")
rep(""".r .v{{width:119pt;flex:none;overflow-wrap:anywhere}}""", """.r .v{{width:119pt;flex:none;overflow-wrap:anywhere}}""")

# css variables, defaults to be calibrated against D-1
rep("""*{{box-sizing:border-box}}""", """:root{{--title-top:0pt;--add-top:37.4pt;--sum-top:82.9pt;--lead-after:2.2pt;--row-text:0pt}}
*{{box-sizing:border-box}}""")
open(p, 'w', encoding='utf-8').write(s)

# footer reference block: labels right-aligned to 541 pt, values from 546 pt
q = r"engine/uad/report/flow.py"
t = open(q, encoding='utf-8').read()
old = """        refs.append(f"<div class='ref' style='top:{y:.1f}pt'><b>{form.esc(label)}</b>"
                    f"<span>{form.esc(value)}</span></div>")"""
assert old in t
t = t.replace(old, """        refs.append(f"<div class='refl' style='top:{y:.1f}pt'>{form.esc(label)}</div>"
                    f"<div class='refv' style='top:{y:.1f}pt'>{form.esc(value)}</div>")""")
open(q, 'w', encoding='utf-8').write(t)
s = open(p, encoding='utf-8').read()
s = s.replace(""".ftr .ref{{right:36pt;text-align:right;white-space:nowrap}}""",
              """.ftr .refl{{right:71pt;text-align:right;white-space:nowrap;font-weight:700}}
.ftr .refv{{left:546pt;white-space:nowrap;font-weight:400}}
.ftr .ref{{right:36pt;text-align:right;white-space:nowrap}}""")
open(p, 'w', encoding='utf-8').write(s)
print("ok")
