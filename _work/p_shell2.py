import pathlib
p=pathlib.Path("engine/app/ui/index.html"); s=p.read_text(encoding="utf-8")

# 1. remember the run so it can continue in the swapped-in frame
old = """  S.autoTotal=r.data.total;
  if(!r.data.total){"""
new = """  S.autoTotal=r.data.total; S.autoSteps=r.data.steps; S.autoAt=0; S.autoSwapped=false;
  if(!r.data.total){"""
assert old in s; s=s.replace(old,new,1)

old = """  f.contentWindow.postMessage({uad:'autofill',steps:r.data.steps,pace:70},'*');
}"""
new = """  f.contentWindow.postMessage({uad:'autofill',steps:r.data.steps,pace:70},'*');
  waitForFill();
}

/* The server finishes writing long before the page finishes showing it.  As
   soon as it has, the report is laid out again out of sight and swapped in,
   and the rest of the run carries on against that -- so the rows, the grid
   cells and the photographs the case brought are there to be filled in. */
async function waitForFill(){
  for(let i=0;i<400;i++){
    const st=await apiRaw(`/cases/${S.caseId}/autofill`);
    if(st&&st.ok&&!st.data.running){ S.autoResult=st.data; break; }
    await new Promise(go=>setTimeout(go,250));
  }
  if(S.autoSwapped||!S.autoSteps) return;
  S.autoSwapped=true;
  const f=$('#rf'); if(f&&f.contentWindow) f.contentWindow.postMessage({uad:'autofill-stop'},'*');
  S.dirty=false;
  swapFrame('form');
}"""
assert old in s; s=s.replace(old,new,1)

# 2. when the swapped frame is ready, hand it the rest of the run
old = """    if(nf&&e.source===nf.contentWindow){ if(m.uad==='frame-ready') finishSwap(kind,nf); return; }"""
new = """    if(nf&&e.source===nf.contentWindow){ if(m.uad==='frame-ready') finishSwap(kind,nf); return; }
    if(nf&&e.source===nf.contentWindow&&m.uad==='ready') return;"""
assert old in s; s=s.replace(old,new,1)

old = """  if(m.uad==='ready'){ S.formReady=true; const b=$('#rf-busy'); if(b) b.remove();"""
new = """  if(m.uad==='ready'){ S.formReady=true; const b=$('#rf-busy'); if(b) b.remove();
    // a run in progress continues in the frame that has just been swapped in
    if(S.autoSteps&&S.autoAt<S.autoSteps.length&&S.autoSwapped){
      f.contentWindow.postMessage(
        {uad:'autofill',steps:S.autoSteps.slice(S.autoAt),pace:55},'*');
    }"""
assert old in s; s=s.replace(old,new,1)

# 3. track where the run has reached
old = """function autoFillAt(m){
  const what=$('#rf-agent-what'), count=$('#rf-agent-count'), bar=$('#rf-agent-bar');
  if(!what) return;
  what.textContent=m.section+' — '+(m.label||m.value||'');
  count.textContent=m.n+' of '+m.total;
  bar.style.width=Math.round((m.n/m.total)*100)+'%';"""
new = """function autoFillAt(m){
  const what=$('#rf-agent-what'), count=$('#rf-agent-count'), bar=$('#rf-agent-bar');
  if(!what) return;
  S.autoAt=Math.max(S.autoAt||0,m.n);
  const total=S.autoTotal||m.total;
  what.textContent=m.section+' — '+(m.label||m.value||'');
  count.textContent=m.n+' of '+total;
  bar.style.width=Math.round((m.n/total)*100)+'%';"""
assert old in s; s=s.replace(old,new,1)

# 4. the end of the run
old = """async function autoFillDone(){
  const what=$('#rf-agent-what');
  if(what) what.textContent='Saving and laying the report out again…';
  for(let i=0;i<80;i++){
    const st=await api(`/cases/${S.caseId}/autofill`);
    if(st&&st.ok&&!st.data.running){
      const bad=(st.data.failed||[]).length;
      toast(bad?`${st.data.written} values entered, ${bad} refused — see the Review Master.`
               :`${st.data.written} values entered.`,5000);
      break;
    }
    await new Promise(go=>setTimeout(go,250));
  }
  const btn=$('#rf-auto'), bar=$('#rf-agent');
  if(btn){ btn.disabled=false; btn.textContent='Fill the report'; }
  if(bar) bar.hidden=true;
  S.dirty=false;
  await refreshMedia();
  swapFrame('form');
}"""
new = """async function autoFillDone(){
  if(S.autoSteps&&S.autoAt<S.autoSteps.length-1&&!S.autoSwapped) return;  // a swap is coming
  const what=$('#rf-agent-what');
  if(what) what.textContent='Saving and laying the report out again…';
  let result=S.autoResult;
  for(let i=0;i<80&&!result;i++){
    const st=await api(`/cases/${S.caseId}/autofill`);
    if(st&&st.ok&&!st.data.running){ result=st.data; break; }
    await new Promise(go=>setTimeout(go,250));
  }
  const bad=((result&&result.failed)||[]).length;
  toast(bad?`${(result||{}).written} values entered, ${bad} refused — see the Review Master.`
           :`${(result||{}).written||0} values entered.`,5000);
  const btn=$('#rf-auto'), bar=$('#rf-agent');
  if(btn){ btn.disabled=false; btn.textContent='Fill the report'; }
  if(bar) bar.hidden=true;
  S.autoSteps=null; S.autoResult=null; S.dirty=false;
  await refreshMedia();
  const rv=await api('/cases/'+S.caseId+'/review');
  if(rv&&rv.ok){ S.review=rv.data; drawRail(); markRail(); }
  swapFrame('form');
}"""
assert old in s; s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8"); print("ok")
