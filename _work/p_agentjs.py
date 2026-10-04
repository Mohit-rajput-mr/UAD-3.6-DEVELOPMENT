import pathlib
p = pathlib.Path("engine/uad/report/flow.py"); s = p.read_text(encoding="utf-8")

agent = r"""
  /* --------------------------------------------------------- the filler
     A case arrives as an order sheet, an MLS export and a folder of
     photographs.  The server writes the whole document in one pass; this
     replays the same list of steps on the page so the appraiser watches the
     report being filled in rather than being handed it finished.  Nothing
     here writes: every value shown has already been saved by the step the
     server ran, and the form is reloaded from the server at the end, so what
     is left on the screen is the saved document and not this animation.
  */
  var TICK='\uF052', CLEAR='\uF0A3';
  var agentStyle=document.createElement('style');
  agentStyle.textContent=
    ".agent-on{outline:1.5pt solid #231f20;outline-offset:1pt;background:#fff3b0!important}"
    +".agent-typed{background:#fff9d6}"
    +"@keyframes agentpulse{from{box-shadow:0 0 0 0 rgba(35,31,32,.35)}"
    +"to{box-shadow:0 0 0 6pt rgba(35,31,32,0)}}"
    +".agent-on{animation:agentpulse .5s ease-out}";
  document.head.appendChild(agentStyle);

  var optionCache={};
  function optionsFor(fid){
    if(optionCache[fid]) return Promise.resolve(optionCache[fid]);
    return fetch('/api/fields/'+fid+'/options').then(function(r){return r.json();})
      .then(function(d){ optionCache[fid]=d.options||[]; return optionCache[fid]; })
      .catch(function(){ optionCache[fid]=[]; return []; });
  }
  function control(s){
    if(s.kind==='check')
      return document.querySelector('.bx[data-fid="'+s.fid+'"][data-pick="'+s.value+'"]');
    return document.querySelector('[data-fid="'+s.fid+'"]');
  }
  function wait(ms){ return new Promise(function(go){ setTimeout(go,ms); }); }

  function showList(el,options,chosen){
    var list=document.createElement('div');
    list.className='picklist';
    var hit=null;
    options.slice(0,12).forEach(function(o){
      var row=document.createElement('div');
      row.textContent=o.label;
      if(o.value===chosen||o.label===chosen){ row.className='on'; hit=row; }
      list.appendChild(row);
    });
    var host=el.closest('.hz')||document.body;
    host.appendChild(list);
    var a=el.getBoundingClientRect(), b=host.getBoundingClientRect();
    var scale=(b.width/host.offsetWidth)||1;
    list.style.left=((a.left-b.left)/scale)+'px';
    list.style.top=((a.bottom-b.top)/scale)+'px';
    if(hit) hit.scrollIntoView({block:'nearest'});
    return list;
  }
  function typeInto(el,text,pace){
    return new Promise(function(done){
      var i=0, size=Math.max(2,Math.ceil(text.length/6));
      el.classList.add('agent-typed');
      (function beat(){
        i=Math.min(text.length,i+size);
        el.textContent=text.slice(0,i);
        if(i>=text.length){ el.classList.remove('agent-typed'); return done(); }
        setTimeout(beat,pace);
      })();
    });
  }
  var filling=false;
  function fill(steps,pace){
    if(filling) return;
    filling=true;
    pace=pace||70;
    var i=0, atSection=null, shown=0, missed=0;
    function finish(){
      filling=false;
      tell({uad:'autofill-done',shown:shown,missed:missed});
    }
    function next(){
      if(i>=steps.length) return finish();
      var s=steps[i++];
      tell({uad:'autofill-at',n:s.n,total:steps.length,secn:s.secn,
            section:s.section,label:s.label,value:s.display||s.value});
      if(s.secn!==atSection){ atSection=s.secn; goSection(s.secn); }
      var el=control(s);
      if(!el){ missed++; return setTimeout(next,0); }
      el.scrollIntoView({block:'center',behavior:'auto'});
      el.classList.add('agent-on');
      var quiet=function(){
        el.classList.remove('agent-on'); shown++; setTimeout(next,pace*0.4);
      };
      if(s.kind==='check'){
        var run=el.parentNode.querySelectorAll('.bx[data-pick]');
        [].forEach.call(run,function(b){ b.innerHTML=CLEAR; });
        return wait(pace).then(function(){ el.innerHTML=TICK; }).then(function(){
          return wait(pace*0.6); }).then(quiet);
      }
      if(s.kind==='pick'){
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
        return wait(pace*0.5); }).then(quiet);
    }
    next();
  }
"""

hook = """    if(m.uad==='goto'){"""
new_hook = """    if(m.uad==='autofill'){ fill(m.steps||[],m.pace); }
    if(m.uad==='goto'){"""
assert hook in s
s = s.replace(hook, new_hook, 1)

anchor = "  /* Follow the reader: the section at the top quarter of the window is the"
assert anchor in s
s = s.replace(anchor, agent.strip("\n") + "\n\n" + anchor, 1)
p.write_text(s, encoding="utf-8")
print("ok")
