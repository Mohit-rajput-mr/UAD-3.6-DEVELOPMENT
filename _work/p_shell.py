import pathlib
p=pathlib.Path("engine/app/ui/index.html"); s=p.read_text(encoding="utf-8")

# 1. the button
old = '''      <button class="addbtn" id="rf-market">Import market charts</button>
      <button class="addbtn" id="rf-reload">Reload</button>
    </div>'''
new = '''      <button class="addbtn" id="rf-market">Import market charts</button>
      <button class="addbtn primary" id="rf-auto" title="Enter the case: the server writes the whole document while the report is filled in on screen, section by section">Fill the report</button>
      <button class="addbtn" id="rf-reload">Reload</button>
    </div>
    <div class="rf-agent" id="rf-agent" hidden>
      <span class="rf-agent-dot"></span>
      <span class="rf-agent-what" id="rf-agent-what">Preparing the case…</span>
      <span class="rf-agent-count" id="rf-agent-count"></span>
      <span class="rf-agent-track"><i id="rf-agent-bar"></i></span>
    </div>'''
assert old in s; s=s.replace(old,new,1)

# 2. the handler
old = """  $('#rf-reload').onclick=()=>{S.dirty=false;swapFrame('form');};"""
new = """  $('#rf-reload').onclick=()=>{S.dirty=false;swapFrame('form');};
  $('#rf-auto').onclick=()=>autoFill();"""
assert old in s; s=s.replace(old,new,1)

# 3. the driver, placed beside the other report helpers
anchor = """/* The five Market graphs are the numbers the appraisal already argues from, so"""
driver = """/* Filling the report by itself.

   The server plans the steps and writes the whole document in one pass -- the
   case is correct within a second of the button being pressed.  The page is
   given the same list and replays it: it opens each section, goes to the
   control, opens the list and picks the value, ticks the box, types the text.
   When the writing is finished the report is reloaded from the server, so the
   appraiser is left looking at the saved document rather than the animation.
*/
async function autoFill(){
  const btn=$('#rf-auto'), bar=$('#rf-agent');
  const f=$('#rf');
  if(!f||!f.contentWindow){ toast('Open the report first.',3000); return; }
  const source=S.autoSource||prompt(
    'Fill this report from which case or sample?', 'sf1_appraisal_v1_4');
  if(!source) return;
  btn.disabled=true; btn.textContent='Filling…';
  bar.hidden=false; $('#rf-agent-what').textContent='Planning the case…';
  $('#rf-agent-bar').style.width='0%';
  const r=await api(`/cases/${S.caseId}/autofill`,{method:'POST',body:{source}});
  if(!r||!r.ok){
    bar.hidden=true; btn.disabled=false; btn.textContent='Fill the report';
    toast('Could not read that case: '+((r&&r.data&&r.data.detail)||'unknown'),6000);
    return;
  }
  S.autoTotal=r.data.total;
  if(!r.data.total){
    bar.hidden=true; btn.disabled=false; btn.textContent='Fill the report';
    toast('Nothing to fill: this report already holds those values.',4500);
    return;
  }
  f.contentWindow.postMessage({uad:'autofill',steps:r.data.steps,pace:70},'*');
}

/* The report tells the shell where the filler has reached. */
function autoFillAt(m){
  const what=$('#rf-agent-what'), count=$('#rf-agent-count'), bar=$('#rf-agent-bar');
  if(!what) return;
  what.textContent=m.section+' — '+(m.label||m.value||'');
  count.textContent=m.n+' of '+m.total;
  bar.style.width=Math.round((m.n/m.total)*100)+'%';
  if(m.secn&&m.secn!==S.section){ S.section=m.secn; markRail(); }
}
async function autoFillDone(){
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
}

""" + anchor
assert anchor in s; s=s.replace(anchor,driver,1)

# 4. route the messages
old = """  if(m.uad==='media') refreshMedia();"""
new = """  if(m.uad==='autofill-at') autoFillAt(m);
  if(m.uad==='autofill-done') autoFillDone();
  if(m.uad==='media') refreshMedia();"""
assert old in s; s=s.replace(old,new,1)
p.write_text(s,encoding="utf-8"); print("ok")
