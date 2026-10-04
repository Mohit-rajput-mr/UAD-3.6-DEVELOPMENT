import pathlib
p=pathlib.Path("engine/uad/report/flow.py"); s=p.read_text(encoding="utf-8")

old = """    var more=t.closest('.compadd');
    if(more){
      e.preventDefault();
      more.textContent='Adding\u2026';
      json(api+'/comparables',{method:'POST',headers:{'Content-Type':'application/json'},
                              body:JSON.stringify({kind:'sales'})})
        .then(function(){ tell({uad:'media'}); reloadHere(); })
        .catch(function(err){ alert(err.message); });
      return;
    }"""
new = """    var more=t.closest('.compadd');
    if(more){
      e.preventDefault();
      more.textContent='Adding\u2026';
      json(api+'/comparables',{method:'POST',headers:{'Content-Type':'application/json'},
                              body:JSON.stringify({kind:more.dataset.kind||'sales'})})
        .then(function(){ tell({uad:'media'}); reloadHere(); })
        .catch(function(err){ alert(err.message); });
      return;
    }
    /* Additional Properties Analyzed Not Used: A-1 22.17, a list the
       appraiser lengthens and shortens like any other. */
    var nuadd=t.closest('.nuadd');
    if(nuadd){
      e.preventDefault();
      nuadd.textContent='Adding\u2026';
      json(api+'/comparables',{method:'POST',headers:{'Content-Type':'application/json'},
                              body:JSON.stringify({kind:'not_used'})})
        .then(function(){ reloadHere(); })
        .catch(function(err){ alert(err.message); });
      return;
    }
    var nudrop=t.closest('.nudrop');
    if(nudrop){
      e.preventDefault();
      var n=Number(nudrop.dataset.nu);
      if(!confirm('Remove property #'+n+' from the properties analyzed but not used?')) return;
      json(api+'/comparables/'+n+'?kind=not_used',{method:'DELETE'})
        .then(function(){ reloadHere(); })
        .catch(function(err){ alert(err.message); });
      return;
    }"""
assert old in s; s=s.replace(old,new,1)
s=s.replace("var z=e.target.closest && e.target.closest('.exadd,.compadd');",
            "var z=e.target.closest && e.target.closest('.exadd,.compadd,.nuadd,.nudrop');",1)
p.write_text(s,encoding="utf-8")

# rental and GRM grids get the same "add another" control as the sales grid
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
    report carries gets one -- the rental sheet and the gross rent multiplier
    sheet repeat exactly as the sales sheet does.
    """
    return (f"<div class='exaddrow'><span class='compadd' role='button' tabindex='0'"
            f" data-kind='{esc(kind)}' data-next='{number}'>"
            f"+ Add {esc(what)} #{number}</span></div>")'''
assert old in s; s=s.replace(old,new,1)

old = '''                    if ctx.edit and base == "Sales Comparison Approach":
                        count = sum(len(gr.comparables) for gr in grids)
                        out.append(Block("exhibits", section=printed, visible=True,
                                         html=_add_comparable_html(count + 1)))'''
new = '''                    if ctx.edit:
                        count = sum(len(gr.comparables) for gr in grids)
                        what = {"sales": "Comparable", "rental": "Rental Comparable",
                                "grm": "GRM Comparable"}[GRID_KINDS[base]]
                        out.append(Block("exhibits", section=printed, visible=True,
                                         html=_add_comparable_html(
                                             count + 1, GRID_KINDS[base], what)))'''
assert old in s; s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8"); print("ok")
