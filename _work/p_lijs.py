import pathlib

p = pathlib.Path("engine/uad/report/flow.py")
s = p.read_text(encoding="utf-8")

# --- naming a row the appraiser adds ---------------------------------------
old = """  function commit(el){
    // commentary keeps its line breaks; a one-line value does not have any
    var now=(el.classList.contains('multiline')?el.innerText:el.textContent).trim();
    if(now===(el.dataset.was||'').trim()) return;
    el.dataset.was=now;
    send(el,{value:now});
  }"""
new = """  function commit(el){
    // commentary keeps its line breaks; a one-line value does not have any
    var now=(el.classList.contains('multiline')?el.innerText:el.textContent).trim();
    if(now===(el.dataset.was||'').trim()) return;
    if(el.dataset.li!==undefined){ nameRow(el,now); return; }
    el.dataset.was=now;
    send(el,{value:now});
  }
  /* A row the appraiser adds to a grid is named once and the name is kept
     against the subject and every comparable, so the grid reads as one row
     rather than four differently-named ones. */
  function nameRow(el,now){
    var was=el.dataset.liwas||'';
    el.classList.remove('failed'); el.classList.add('saving');
    json(api+'/comparables/lineitems',
         {method:'PUT',headers:{'Content-Type':'application/json'},
          body:JSON.stringify({kind:el.dataset.li,container:el.dataset.lic,
                               adjust_type:el.dataset.lit,was:was,name:now})})
      .then(function(){ el.classList.remove('saving'); el.dataset.liwas=now;
                        el.dataset.was=now; reloadHere(); })
      .catch(function(err){ el.classList.remove('saving'); el.classList.add('failed');
                            el.title=err.message; });
  }"""
assert old in s, "commit"
s = s.replace(old, new, 1)

# --- removing one ----------------------------------------------------------
old = """    var nudrop=t.closest('.nudrop');"""
new = """    var lidrop=t.closest('.lidrop');
    if(lidrop){
      e.preventDefault();
      var cell=lidrop.closest('td').querySelector('.v');
      if(!cell) return;
      if(!confirm('Remove the row \\u201c'+(cell.dataset.liwas||'')+'\\u201d from this grid?')) return;
      json(api+'/comparables/lineitems',
           {method:'PUT',headers:{'Content-Type':'application/json'},
            body:JSON.stringify({kind:cell.dataset.li,container:cell.dataset.lic,
                                 adjust_type:cell.dataset.lit,
                                 was:cell.dataset.liwas,name:''})})
        .then(function(){ reloadHere(); })
        .catch(function(err){ alert(err.message); });
      return;
    }
    var nudrop=t.closest('.nudrop');"""
assert old in s, "lidrop"
s = s.replace(old, new, 1)
s = s.replace(".exadd,.compadd,.nuadd,.nudrop", ".exadd,.compadd,.nuadd,.nudrop,.lidrop", 1)
p.write_text(s, encoding="utf-8")
print("ok")
