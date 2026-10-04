import pathlib

p = pathlib.Path("engine/uad/report/comparables.py")
s = p.read_text(encoding="utf-8")

old = """        address = row.label.strip() == "Property Address"
        cells = [f"<td class='lbl'><span>{_esc(row.label)}</span></td>"]"""
new = """        address = row.label.strip() == "Property Address"
        if edit and row.line_item:
            # a row the appraiser adds and names: the name is the row's label,
            # and naming the empty one at the foot of the group creates it
            attrs = (f" data-li='{_esc(kind_of(grid))}'"
                     f" data-lic='{_esc(row.line_item)}'"
                     f" data-lit='{_esc(row.adjust_type)}'"
                     f" data-liwas='{_esc(row.item_name)}'")
            name = "" if row.new_item else row.item_name
            drop = ("" if row.new_item else
                    f"<span class='lidrop' role='button' tabindex='0'"
                    f" title='Remove this row'>&#215;</span>")
            cells = [f"<td class='lbl liname'><span class='v'{attrs}"
                     f" contenteditable='true' spellcheck='false'"
                     f" data-ph='Name this row'>{_esc(name)}</span>{drop}</td>"]
        else:
            cells = [f"<td class='lbl'><span>{_esc(row.label)}</span></td>"]"""
assert old in s, "label cell"
s = s.replace(old, new, 1)

# the grid knows which sheet it is
old = """def _photo_cell(src: str | None, text: str, number: int = 0, edit: bool = False) -> str:"""
new = """def kind_of(grid: "Grid") -> str:
    return grid.kind


def _photo_cell(src: str | None, text: str, number: int = 0, edit: bool = False) -> str:"""
assert old in s, "kind_of"
s = s.replace(old, new, 1)

# an added row that has no name yet keeps its cells writable but not its values
old = """        skip = {"Comparable #"} if edit else {
        "Comparable #", "[Additional Row]",
        "[Other Exterior Feature]", "[Other Interior Feature]"}"""
if old in s:
    s = s.replace(old, old, 1)
p.write_text(s, encoding="utf-8")

# ----------------------------------------------------------------- the CSS
p = pathlib.Path("engine/uad/report/form.py")
s = p.read_text(encoding="utf-8")
old = """.nudrop{display:inline-block;cursor:pointer;color:#6a6a66;font-size:9pt;line-height:1;
  padding:0 2pt}
.nudrop:hover,.nudrop:focus{color:#231f20;outline:none}"""
new = """.nudrop,.lidrop{display:inline-block;cursor:pointer;color:#6a6a66;font-size:9pt;
  line-height:1;padding:0 2pt}
.nudrop:hover,.nudrop:focus,.lidrop:hover,.lidrop:focus{color:#231f20;outline:none}
/* a grid row the appraiser adds and names */
td.lbl.liname{position:relative}
td.lbl.liname .v{outline:none;display:inline-block;min-width:40pt}
td.lbl.liname .v:empty:before{content:attr(data-ph);color:#939598;font-style:italic}
td.lbl.liname .lidrop{position:absolute;right:1pt;top:0}"""
assert old in s, "css"
s = s.replace(old, new, 1)
p.write_text(s, encoding="utf-8")
print("ok")
