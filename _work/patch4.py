p = r"engine/uad/report/form.py"
s = open(p, encoding='utf-8').read()


def rep(old, new):
    global s
    assert old in s, old[:80]
    s = s.replace(old, new)


# B-1 p84-85: CostToRepairType decides the cost column, Total Cost and the summary line
rep('''def _table_html(el: dict, ctx: Ctx) -> tuple[str, bool]:
    cols = el["columns"]
    width = el["x1"] - el["x0"]''', '''def cost_to_repair_type(ctx: Ctx) -> str:
    node = ctx.root.find(f".//{M}CostToRepairType")
    return (node.text or "").strip() if node is not None and node.text else ""


def _drop_cost_column(el: dict) -> dict:
    """The DDD table without Estimated Cost to Repair (Appendix E p34): 8/8/13/8/8 picas."""
    widths = [96.0, 96.0, 156.0, 96.0, 96.0]
    x = el["x0"]
    cols = []
    for c, w in zip(el["columns"][:5], widths):
        cols.append({**c, "x0": x, "x1": x + w})
        x += w
    rows = []
    for r in el["rows"]:
        if r.get("bar") and r.get("align") == "right":
            continue
        cells = []
        x = el["x0"]
        for c, w in zip(r["cells"][:5], widths):
            cells.append({**c, "x0": x, "x1": x + w})
            x += w
        rows.append({**r, "cells": cells})
    return {**el, "columns": cols, "rows": rows}


def _table_html(el: dict, ctx: Ctx) -> tuple[str, bool]:
    if (len(el["columns"]) == 6 and "Estimated Cost" in el["columns"][5].get("head", "")
            and cost_to_repair_type(ctx) != "Itemized"):
        el = _drop_cost_column(el)
    cols = el["columns"]
    width = el["x1"] - el["x0"]''')
rep('''        values = shown(ctx, ids[0]) if len(ids) == 1 else [text_of(ctx, ids)] if text_of(ctx, ids) else []
        return Item("row", style=style, label=label, values=values,''', '''        values = shown(ctx, ids[0]) if len(ids) == 1 else [text_of(ctx, ids)] if text_of(ctx, ids) else []
        if label.startswith("Total Estimated Cost of Items") and cost_to_repair_type(ctx) != "TotalCost":
            values = []
        return Item("row", style=style, label=label, values=values,''')

# bold intro followed by its two-space gap, as the samples set it
rep('''html=f"<div class='txcb'><b>{esc(label)}</b> {esc(value)}</div>"))''',
    '''html=f"<div class='txcb'><b>{esc(label)}&nbsp; </b>{esc(value)}</div>"))''')
rep('''        return (f"<div class='txcb1'><b>{esc(item.label)}</b> "''', '''        return (f"<div class='txcb1'><b>{esc(item.label)}&nbsp; </b>"''')

# footer: labels end 534.4 pt, values from 546 pt; baselines 0.5 pt higher
rep(".ftr .f1{{left:36pt;top:945.1pt;font-weight:700}}", ".ftr .f1{{left:36pt;top:944.6pt;font-weight:700}}")
rep(".ftr .f2{{left:36pt;top:963.1pt;font-weight:700;color:#77787b}}", ".ftr .f2{{left:36pt;top:962.6pt;font-weight:700;color:#77787b}}")
rep(".ftr .f3{{left:36pt;top:972.1pt;font-weight:700;color:#77787b}}", ".ftr .f3{{left:36pt;top:971.6pt;font-weight:700;color:#77787b}}")
rep(".ftr .refl{{right:71pt;", ".ftr .refl{{right:77.8pt;margin-top:-0.5pt;")
rep(".ftr .refv{{left:546pt;", ".ftr .refv{{left:546pt;margin-top:-0.2pt;")

# table cells 3.8 pt in; sub bars 1 pt higher; the total amount right-aligned in its cell
rep("table.tbl td{{font-size:8pt;line-height:9pt;padding:1.9pt 4pt 1.3pt 4pt;",
    "table.tbl td{{font-size:8pt;line-height:9pt;padding:1.9pt 4pt 1.3pt 3.8pt;")
rep("table.tbl tr.sub td{{background:#a7a9ac;color:#fff;font-weight:700;border-right:0}}",
    "table.tbl tr.sub td{{background:#a7a9ac;color:#fff;font-weight:700;border-right:0;padding-top:0.9pt;padding-bottom:2.3pt}}")
open(p, 'w', encoding='utf-8').write(s)
print("ok")
