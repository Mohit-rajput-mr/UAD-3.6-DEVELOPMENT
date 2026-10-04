"""Editor: save buttons, required marks, the comparables grid, and the map tab."""
import re
p = r"engine/app/ui/index.html"
s = open(p, encoding='utf-8').read()


def rep(old, new):
    global s
    assert old in s, old[:90]
    s = s.replace(old, new, 1)


# ---------------------------------------------------------------- styles
rep("""/* comparables, in row format -------------------------------------------- */""",
    """/* required marks and warnings ------------------------------------------- */
.req{color:var(--ink);font-weight:700;margin-left:2px}
.field[data-flag=Warning]{background:transparent}
.flag.Warning code{border:1px solid var(--rule-2);background:var(--surface)}
.savebar{position:sticky;bottom:0;z-index:4;display:flex;gap:8px;align-items:center;
  padding:9px 0 12px;background:linear-gradient(to top,var(--paper) 72%,transparent)}
.savebar .note{font-size:11px;color:var(--muted)}
.savebar .spacer{flex:1}

/* comparables, in row format -------------------------------------------- */""")
rep("""table.comps td.adj{width:78px;background:var(--paper)}""",
    """table.comps td.adj{width:78px;background:var(--paper)}
table.comps th{position:relative;user-select:none}
table.comps th .grip{position:absolute;top:0;right:0;width:6px;height:100%;
  cursor:col-resize;background:transparent}
table.comps th .grip:hover{background:var(--rule-2)}
table.comps thead th.comp{cursor:grab}
table.comps thead th.comp.drag{opacity:.45}
table.comps thead th.comp.over{box-shadow:inset 3px 0 0 var(--paper)}
.compcell{display:flex;gap:7px;align-items:flex-start}
.compcell .ph{width:54px;height:40px;flex:none;background:#3a3a38;border:1px solid #55554f;
  display:flex;align-items:center;justify-content:center;cursor:pointer;overflow:hidden}
.compcell .ph img{width:100%;height:100%;object-fit:cover}
.compcell .ph span{font:400 8px/1.1 var(--sans);color:#b9b9b4;text-align:center;padding:2px}
.compcell .meta{min-width:0}
.compcell .addr{font:400 10px/1.3 var(--sans);text-transform:none;letter-spacing:0;
  color:#d8d8d4;white-space:normal;word-break:break-word;max-width:150px}
.compcell .tools{display:flex;gap:4px;margin-top:3px}
.compcell button{border:1px solid #6d6d66;background:transparent;color:var(--paper);
  cursor:pointer;font:600 9px/1 var(--sans);letter-spacing:.08em;padding:2px 5px}
.compcell button:hover{background:var(--paper);color:var(--ink)}
table.comps select{width:100%;border:0;background:transparent;padding:1px 2px;font-size:11.5px}
table.comps select:focus{outline:2px solid var(--ink);outline-offset:-2px;background:#fff}""")

# ---------------------------------------------------------------- tabs
rep("""  const tabs=[['form','Section'],['comps','Comparables'],['review','Review Master'],
              ['preview','Preview'],['history','History']];""",
    """  const tabs=[['form','Section'],['comps','Comparables'],['map','Location Map'],
              ['review','Review Master'],['preview','Preview'],['history','History']];""")
rep("""  if(S.view==='comps')   return drawComps(w);""",
    """  if(S.view==='comps')   return drawComps(w);
  if(S.view==='map'){
    w.innerHTML=`<div class="panel"><p style="margin:0 0 9px;font-size:11.5px;color:var(--muted)">
      The subject and the comparables are read from this case. Drag a callout to place it,
      switch between <b>Location Map</b> and <b>Aerial Map</b>, then <b>Save to report</b> —
      the exhibit lands in the report as an image.</p>
      <iframe class="frame" style="height:calc(100vh - 210px)" src="/ui/map/index.html?case=${S.caseId}&seed=1"></iframe></div>`;
    return;}""")

# ---------------------------------------------------------------- required mark
rep("""  name.innerHTML=`<span class="lbl">${esc(f.label)}</span>
    <span class="fid">${esc(f.field_id)}${f.ordinal>1?' #'+f.ordinal:''}</span>`;""",
    """  const required=(f.conditionality||'').toUpperCase()==='R';
  name.innerHTML=`<span class="lbl">${esc(f.label)}${required?'<span class="req" title="Required">*</span>':''}</span>
    <span class="fid">${esc(f.field_id)}${f.ordinal>1?' #'+f.ordinal:''}</span>`;""")

# ---------------------------------------------------------------- save bar
rep("""  w.innerHTML=''; w.appendChild(p);
  w.appendChild(sectionImages(s));
  w.appendChild(ackBlock(s));
}""",
    """  w.innerHTML=''; w.appendChild(p);
  w.appendChild(sectionImages(s));
  w.appendChild(ackBlock(s));
  w.appendChild(saveBar(s));
}

/* Every change is written as it is made; these buttons flush anything still
   in flight, confirm it, and move on. */
function saveBar(s){
  const i=S.sections.findIndex(x=>x.number===s.number);
  const next=S.sections[i+1];
  const bar=document.createElement('div'); bar.className='panel'; bar.style.paddingTop='0';
  const box=document.createElement('div'); box.className='savebar';
  box.innerHTML=`<span class="note">Saved as you type · ${S.pending?'saving…':'all changes stored'}</span>
    <span class="spacer"></span>`;
  const save=document.createElement('button'); save.className='btn'; save.textContent='Save';
  save.onclick=async()=>{await flush(); toast('Section saved');};
  const nextBtn=document.createElement('button');
  nextBtn.className='btn primary';
  nextBtn.textContent=next?'Save & next: '+next.tab:'Save & finish';
  nextBtn.onclick=async()=>{
    await flush();
    if(next){S.section=next.number;drawRail();drawHead();drawWork();
      document.querySelector('section.work').scrollTop=0;}
    else{S.view='review';drawHead();drawWork();}
  };
  box.appendChild(save); box.appendChild(nextBtn);
  bar.appendChild(box); return bar;
}
async function flush(){
  if(S.inflight) await S.inflight;
  await refresh();
}""")

# track in-flight saves so Save can wait for them
rep("""let t=null;
async function save(f,value){
  clearTimeout(t);
  const r=await api(`/cases/${S.caseId}/fields/${f.field_id}`,
    {method:'PATCH',body:JSON.stringify({value,ordinal:f.ordinal})});
  toast(r.ok?'Saved '+f.field_id:'Could not save');
  t=setTimeout(refresh,300);
}""",
    """let t=null;
async function save(f,value){
  clearTimeout(t);
  S.pending=true;
  S.inflight=api(`/cases/${S.caseId}/fields/${f.field_id}`,
    {method:'PATCH',body:JSON.stringify({value,ordinal:f.ordinal})});
  const r=await S.inflight;
  S.pending=false;
  toast(r.ok?'Saved '+f.field_id:'Could not save');
  t=setTimeout(refresh,300);
}""")
open(p, 'w', encoding='utf-8').write(s)
print("ok")
