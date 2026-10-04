import pathlib
p=pathlib.Path("engine/uad/report/flow.py"); s=p.read_text(encoding="utf-8")

old = """    function next(){
      if(i>=steps.length) return finish();
      var s=steps[i++];
      tell({uad:'autofill-at',n:s.n,total:steps.length,secn:s.secn,
            section:s.section,label:s.label,value:s.display||s.value});
      if(s.secn!==atSection){ atSection=s.secn; goSection(s.secn); }"""
new = """    function next(){
      if(i>=steps.length) return finish();
      var s=steps[i++];
      // Values that have no control of their own -- what a block is linked to,
      // a measure's unit -- are written all the same; they are not acted out.
      if(s.kind==='data'||s.kind==='link'){
        if(s.n%12===0) tell({uad:'autofill-at',n:s.n,total:steps.length,secn:s.secn,
                             section:s.section,label:s.label,value:s.display||s.value});
        return setTimeout(next,0);
      }
      tell({uad:'autofill-at',n:s.n,total:steps.length,secn:s.secn,
            section:s.section,label:s.label,value:s.display||s.value});
      if(s.secn!==atSection){ atSection=s.secn; goSection(s.secn); }"""
assert old in s; s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8")

p=pathlib.Path("engine/app/ui/index.html"); s=p.read_text(encoding="utf-8")
old = """  f.contentWindow.postMessage({uad:'autofill',steps:r.data.steps,pace:70},'*');
  waitForFill();"""
new = """  // However big the case, the run takes about half a minute: the pace is set
  // by how many of its steps are acted out on the page.
  const acted=r.data.steps.filter(s=>s.kind!=='data'&&s.kind!=='link').length;
  S.autoPace=Math.max(18,Math.min(70,Math.round(26000/Math.max(acted,1))));
  f.contentWindow.postMessage({uad:'autofill',steps:r.data.steps,pace:S.autoPace},'*');
  waitForFill();"""
assert old in s; s=s.replace(old,new,1)
s=s.replace("{uad:'autofill',steps:S.autoSteps.slice(S.autoAt),pace:55},'*');",
            "{uad:'autofill',steps:S.autoSteps.slice(S.autoAt),pace:S.autoPace||45},'*');",1)
p.write_text(s,encoding="utf-8"); print("ok")
