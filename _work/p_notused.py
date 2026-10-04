import pathlib
p=pathlib.Path("engine/uad/report/form.py"); s=p.read_text(encoding="utf-8")

NEW = '''
# ---------------------------------------------------------------------------
# Additional Properties Analyzed Not Used
# ---------------------------------------------------------------------------
# A-1 gives this list its own six field IDs (22.17.01-06) and the D-1 samples
# print it under the sales grid, but the C-1 layout has no element for it, so
# it is laid out from the samples' own measurements: the rules on SF1 p17 fall
# at 54, 144, 198, 288 and 378 pt, which is what these widths are.
NOT_USED_COLS = ((18.0, "#", "22.17.01"), (90.0, "Property Address", "22.17.02"),
                 (54.0, "Sale Date", "22.17.03"), (90.0, "Status", "22.17.04"),
                 (90.0, "Reason Not Used", "22.17.05"),
                 (198.0, "Comment", "22.17.06"))


def _not_used_html(ctx: "Ctx") -> tuple[str, bool]:
    """The rejected comparables: one line each, edited where they print."""
    props = comparables.properties(ctx.root, "PropertyAnalyzedNotUsed")
    if not props and not ctx.edit:
        return "", False
    tree = ctx.root.getroottree()
    body = []
    for number, prop in enumerate(props, start=1):
        inside = ctx.inside(prop)
        key = tree.getpath(prop)
        cells = []
        for _width, _head, fid in NOT_USED_COLS:
            if fid == "22.17.05":
                cells.append(_reason_cell(inside, prop, key))
                continue
            text = comparables.value_for(ctx.root, fid, prop) or (
                str(number) if fid == "22.17.01" else "")
            cells.append(_cell(esc(text), fid, inside, key=key) if ctx.edit
                         else _td(esc(text)))
        row = "".join(cells)
        if ctx.edit:
            row += (f"<td class='nuside'><span class='nudrop' role='button' tabindex='0'"
                    f" data-nu='{number}' title='Remove this property'>&#215;</span></td>")
        body.append(f"<tr>{row}</tr>")
    if not body and not ctx.edit:
        return "", False
    widths = "".join(f"<col style='width:{w:.2f}pt'>" for w, _h, _f in NOT_USED_COLS)
    if ctx.edit:
        widths += "<col style='width:14pt'>"
    head = "".join(f"<th><span>{esc(h)}</span></th>" for _w, h, _f in NOT_USED_COLS)
    if ctx.edit:
        head += "<th></th>"
    table = (f"<table class='tbl nutbl' style='width:{540.0 + (14 if ctx.edit else 0):.2f}pt'>"
             f"<colgroup>{widths}</colgroup><thead><tr>{head}</tr></thead>"
             f"<tbody>{''.join(body)}</tbody></table>")
    if ctx.edit:
        table += ("<div class='exaddrow'><span class='nuadd' role='button' tabindex='0'>"
                  "+ Add a property analyzed but not used</span></div>")
    return table, True


def _reason_cell(ctx: "Ctx", prop: etree._Element, prop_key: str) -> str:
    """Why a property was not used: A-1 allows several reasons, so the cell
    holds a line per reason and, in the editor, an empty line for one more."""
    tree = ctx.root.getroottree()
    lines = []
    for node in prop.iter(f"{M}PROPERTY_NOT_USED_REASON"):
        text = bind.display_value(
            [[(_local(v), (v.text or "").strip()) for v in node.iter()
              if isinstance(v.tag, str) and (v.text or "").strip()]],
            binding("22.17.05"))
        if not text and not ctx.edit:
            continue
        if ctx.edit:
            lines.append(_cell(esc(text), "22.17.05", ctx, key=tree.getpath(node)))
        else:
            lines.append(f"<span>{esc(text)}</span>")
    if ctx.edit:
        lines.append(_cell("", "22.17.05", ctx, key="", new=True))
    inner = "".join(l.replace("<td", "<span class='nureason'", 1).replace("</td>", "</span>")
                    if l.startswith("<td") else l for l in lines)
    return f"<td class='nureasons'>{inner}</td>"


'''
anchor = "def _add_comparable_html(number: int) -> str:"
assert anchor in s
s = s.replace(anchor, NEW.lstrip("\n") + anchor, 1)

# draw it under the sales grid
old = """                    if ctx.edit and base == "Sales Comparison Approach":
                        count = sum(len(gr.comparables) for gr in grids)
                        out.append(Block("exhibits", section=printed, visible=True,
                                         html=_add_comparable_html(count + 1)))"""
new = """                    if ctx.edit and base == "Sales Comparison Approach":
                        count = sum(len(gr.comparables) for gr in grids)
                        out.append(Block("exhibits", section=printed, visible=True,
                                         html=_add_comparable_html(count + 1)))
                    if base == "Sales Comparison Approach":
                        # A-1 22.17: the properties analyzed and not used, which
                        # the samples print under the grid and C-1 never placed
                        nu, shown_ = _not_used_html(ctx)
                        if shown_:
                            out.append(Block("h2", section=printed, group=1,
                                             title="Additional Properties Analyzed Not Used",
                                             html=_h2_html("Additional Properties Analyzed Not Used", 540),
                                             visible=True))
                            out.append(Block("table", section=printed, html=nu, visible=True))"""
assert old in s
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("ok")
