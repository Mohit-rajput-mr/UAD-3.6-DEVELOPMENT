import pathlib
p=pathlib.Path("engine/app/ui/index.html"); s=p.read_text(encoding="utf-8")

# the 'ready' hook was on the wrong frame: the new one is not #rf until the
# swap has finished, so the rest of the run is handed over there instead
old = """  if(m.uad==='ready'){ S.formReady=true; const b=$('#rf-busy'); if(b) b.remove();
    // a run in progress continues in the frame that has just been swapped in
    if(S.autoSteps&&S.autoAt<S.autoSteps.length&&S.autoSwapped){
      f.contentWindow.postMessage(
        {uad:'autofill',steps:S.autoSteps.slice(S.autoAt),pace:S.autoPace||45},'*');
    }"""
new = """  if(m.uad==='ready'){ S.formReady=true; const b=$('#rf-busy'); if(b) b.remove();"""
assert old in s; s=s.replace(old,new,1)

old = """    if(nf&&e.source===nf.contentWindow){ if(m.uad==='frame-ready') finishSwap(kind,nf); return; }
    if(nf&&e.source===nf.contentWindow&&m.uad==='ready') return;"""
new = """    if(nf&&e.source===nf.contentWindow){ if(m.uad==='frame-ready') finishSwap(kind,nf); return; }"""
assert old in s; s=s.replace(old,new,1)

old = """  requestAnimationFrame(()=>{
    nf.id=old.id; nf.style.cssText=''; old.remove();
    if(kind==='form'){ const g=$('#rf-gaps'); if(g&&!g.checked) nf.contentWindow.postMessage({uad:'gaps',on:false},'*'); }
  });"""
new = """  requestAnimationFrame(()=>{
    nf.id=old.id; nf.style.cssText=''; old.remove();
    if(kind==='form'){
      const g=$('#rf-gaps');
      if(g&&!g.checked) nf.contentWindow.postMessage({uad:'gaps',on:false},'*');
      // a run in progress carries on in the report that has just been swapped
      // in, which now holds the rows, the grid cells and the photographs
      if(S.autoSteps&&S.autoAt<S.autoSteps.length){
        nf.contentWindow.postMessage(
          {uad:'autofill',steps:S.autoSteps.slice(S.autoAt),pace:S.autoPace||45},'*');
      }
    }
  });"""
assert old in s; s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8"); print("ok")
