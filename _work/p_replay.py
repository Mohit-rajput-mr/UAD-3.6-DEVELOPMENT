import pathlib
p = pathlib.Path("engine/uad/report/flow.py"); s = p.read_text(encoding="utf-8")

old = """  function control(s){
    if(s.kind==='check')
      return document.querySelector('.bx[data-fid="'+s.fid+'"][data-pick="'+s.value+'"]');
    return document.querySelector('[data-fid="'+s.fid+'"]');
  }"""
new = r"""  function words(t){ return (t||'').replace(/\s+/g,' ').trim().toLowerCase(); }
  /* A table cell is found by the field it writes and, where a table repeats a
     row per instance, by the row it prints on. */
  function cellFor(s){
    var all=[].slice.call(document.querySelectorAll('[data-tf="'+s.fid+'"]'));
    if(!all.length) return null;
    if(s.row_label){
      var named=all.filter(function(el){
        var tr=el.closest('tr'), first=tr&&tr.querySelector('td');
        return first&&words(first.textContent)===words(s.row_label);
      });
      if(named.length) all=named;
    }
    var free=all.filter(function(el){ return !words(el.textContent); });
    return (free.length?free:all)[0];
  }
  /* A grid cell is the row whose label matches, in the column of that
     comparable (0 is the subject). */
  function gridCell(s){
    var tables=document.querySelectorAll('table.grid');
    for(var t=0;t<tables.length;t++){
      var rows=tables[t].querySelectorAll('tbody tr');
      for(var r=0;r<rows.length;r++){
        var lab=rows[r].querySelector('td.lbl');
        if(!lab||words(lab.textContent)!==words(s.label)) continue;
        var vals=rows[r].querySelectorAll('td.v');
        var want=s.adjust?(s.column*2):(s.column*2-(s.column?1:0));
        var cell=vals[Math.min(Math.max(want,0),vals.length-1)];
        if(cell) return cell;
      }
    }
    return null;
  }
  function control(s){
    if(s.kind==='check')
      return document.querySelector('.bx[data-fid="'+s.fid+'"][data-pick="'+s.value+'"]');
    if(s.kind==='grid') return gridCell(s);
    if(s.kind==='cell') return cellFor(s);
    if(s.kind==='photo') return document.querySelector('.exadd,.exdrop,.photo,.exbox');
    if(!s.fid) return null;
    return document.querySelector('[data-fid="'+s.fid+'"]')||cellFor(s);
  }"""
assert old in s
s = s.replace(old, new, 1)

# the runner: handle the new kinds, and blank a value before replaying it
old_run = """      if(s.kind==='pick'){
        return optionsFor(s.fid).then(function(options){
          el.classList.add('open');
          var list=showList(el,options,s.value);
          return wait(pace*1.6).then(function(){
            list.remove(); el.classList.remove('open');
            el.textContent=s.display||s.value;
            return wait(pace*0.4);
          });
        }).then(quiet);
      }
      return typeInto(el,s.display||s.value,Math.max(12,pace/5)).then(function(){
        return wait(pace*0.5); }).then(quiet);"""
new_run = """      if(s.kind==='pick'){
        return optionsFor(s.fid).then(function(options){
          el.classList.add('open');
          var list=showList(el,options,s.value);
          return wait(pace*1.6).then(function(){
            list.remove(); el.classList.remove('open');
            el.textContent=s.display||s.value;
            return wait(pace*0.4);
          });
        }).then(quiet);
      }
      // A cell or a grid cell the server has already written still reads as
      // filling: it is emptied for the moment it takes to enter it again.
      var into=el.querySelector('span')||el;
      if(s.kind==='cell'||s.kind==='grid'||s.kind==='data') into.textContent='';
      return typeInto(into,s.display||s.value,Math.max(8,pace/6)).then(function(){
        return wait(pace*0.4); }).then(quiet);"""
assert old_run in s
s = s.replace(old_run, new_run, 1)

# a step with nowhere to show still counts, and the section still opens
old_miss = """      var el=control(s);
      if(!el){ missed++; return setTimeout(next,0); }"""
new_miss = """      var el=control(s);
      if(!el){
        // The value is written; this page has no control for it yet (a row
        // that only appears once the report is laid out again).  The section
        // is still opened, so the filling is seen to move through the report.
        missed++; return setTimeout(next,4);
      }"""
assert old_miss in s
s = s.replace(old_miss, new_miss, 1)

# let the shell hand the frame the rest of a run after a swap
old_msg = """    if(m.uad==='autofill'){ fill(m.steps||[],m.pace); }"""
new_msg = """    if(m.uad==='autofill'){ fill(m.steps||[],m.pace); }
    if(m.uad==='autofill-stop'){ filling=false; }"""
assert old_msg in s
s = s.replace(old_msg, new_msg, 1)
p.write_text(s, encoding="utf-8")
print("ok")
