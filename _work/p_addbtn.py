import pathlib
p=pathlib.Path("engine/uad/report/form.py"); s=p.read_text(encoding="utf-8")
old = '''def _add_comparable_html(number: int) -> str:
    """Under the sales grid, in the editor only: another comparable.

    The new one joins the last block of three, or opens a new block on the
    next page, exactly as the printed report lays it out.
    """
    return (f"<div class='exaddrow'><span class='compadd' role='button' tabindex='0'"
            f" data-next='{number}'>+ Add Comparable #{number}</span></div>")'''
new = '''def _add_comparable_html(number: int, kind: str = "sales",
                         what: str = "Comparable") -> str:
    """Under a comparable grid, in the editor only: another comparable.

    The new one joins the last block of three, or opens a new block on the
    next page, exactly as the printed report lays it out.  Every grid the
    report carries gets one: the rental sheet and the gross rent multiplier
    sheet repeat exactly as the sales sheet does, and an appraiser who needs a
    fourth rental had no way to ask for one.
    """
    return (f"<div class='exaddrow'><span class='compadd' role='button' tabindex='0'"
            f" data-kind='{esc(kind)}' data-next='{number}'>"
            f"+ Add {esc(what)} #{number}</span></div>")'''
assert old in s, "add_comparable_html"
s=s.replace(old,new,1)
old2 = '''                    if ctx.edit and base == "Sales Comparison Approach":
                        count = sum(len(gr.comparables) for gr in grids)
                        out.append(Block("exhibits", section=printed, visible=True,
                                         html=_add_comparable_html(count + 1)))'''
new2 = '''                    if ctx.edit:
                        count = sum(len(gr.comparables) for gr in grids)
                        what = {"sales": "Comparable", "rental": "Rental Comparable",
                                "grm": "GRM Comparable"}[GRID_KINDS[base]]
                        out.append(Block("exhibits", section=printed, visible=True,
                                         html=_add_comparable_html(
                                             count + 1, GRID_KINDS[base], what)))'''
assert old2 in s, "grid add block"
s=s.replace(old2,new2,1)
p.write_text(s,encoding="utf-8"); print("form ok")
