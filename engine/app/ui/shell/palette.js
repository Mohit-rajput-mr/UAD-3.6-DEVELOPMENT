/* The command palette and the keyboard bindings (DR phase 2, step S5 /
   T-277; _work/dr/PHASE2_SHELL_PLAN.md "Keyboard and command palette").

   Ctrl+K: every command the editor has -- the shell's own (windows, zoom,
   problems) and the report bar's buttons, adopted by id so a click on either
   does the same -- plus "Go to" each section, filtered as you type, the ones
   used last first.  Enter runs it, Esc closes.  Keys are declared on the
   commands; UADShell's one keymap does the rest. */
(function(){
  if(!window.UADShell||!UADShell.enabled()) return;
  var C=UADShell.commands;
  // the report bar's buttons, as commands (adopted: the button stays the one truth)
  [['report.sketch','Open the Sketch','#rf-sketch'],['report.worksheets','Adjustment worksheets','#rf-sadj'],
   ['report.library','Comment library','#rf-lib'],['report.setup','Report setup','#rf-setup'],
   ['report.map','Generate the location map','#rf-maps'],['report.market','Import market charts','#rf-market'],
   ['report.msearch','Count the market search','#rf-msearch'],['report.fill','Fill the report from a file','#rf-auto'],
   ['report.reload','Reload the report','#rf-reload']].forEach(function(a){
    if(!C.has(a[0])) C.register({id:a[0],label:a[1],group:'Report',adopt:a[2]});
  });
  C.register({id:'palette.open',label:'Command palette',group:'View',keys:['Ctrl+K'],run:function(){ open(); }});
  C.register({id:'field.goto',label:'Go to a field\u2026',group:'View',keys:['Ctrl+G'],run:function(){ open('fields'); }});

  var box=null, list=[], at=0, mode='', LABELS=null;
  /* Ctrl+G: every field on the report, by where B-1 places it */
  function labels(){
    if(LABELS) return Promise.resolve(LABELS);
    return fetch('/api/field-labels',{credentials:'same-origin'}).then(function(r){ return r.json(); })
      .then(function(d){ LABELS=d.labels||{}; return LABELS; }).catch(function(){ return {}; });
  }
  function fields(){
    var f=document.getElementById('rf'), d=null;
    try{ d=f&&f.contentDocument; }catch(_){ d=null; }
    var seen={}, out=[];
    if(!d||!LABELS) return out;
    [].forEach.call(d.querySelectorAll('[data-fid]'),function(el){
      var fid=el.getAttribute('data-fid'); if(!fid||seen[fid]) return; seen[fid]=1;
      var where=LABELS[fid]; if(!where) return;
      out.push({id:'fid.'+fid,label:where,group:fid,keys:'',rank:Object.keys(seen).length,
                run:function(){ if(typeof goToReport==='function') goToReport({fid:fid}); }});
    });
    return out;
  }
  function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function entries(){
    if(mode==='fields') return fields();
    var mru=(UADShell.state.get('palette.mru')||[]);
    var out=C.list().filter(function(c){ return c.id!=='palette.open'&&C.available(c.id); }).map(function(c){
      return {id:c.id,label:c.label||c.id,group:c.group||'',keys:(c.keys||[])[0]||'',run:function(){ C.run(c.id); },
              rank:mru.indexOf(c.id)<0?99:mru.indexOf(c.id)};
    });
    var secs=(typeof S!=='undefined'&&S.sections)||[];
    secs.forEach(function(s){
      out.push({id:'go.'+s.number,label:'Go to '+s.name,group:'Section '+String(s.number).padStart(2,'0'),keys:'',rank:100,
                run:function(){ var r=document.querySelector('.railitem[data-secn="'+s.number+'"]'); if(r) r.click(); }});
    });
    return out;
  }
  function score(e,words){
    if(!words) return 1;
    var t=(e.label+' '+e.group).toLowerCase(), all=words.split(/\s+/);
    for(var i=0;i<all.length;i++) if(t.indexOf(all[i])<0) return 0;
    return t.indexOf(all[0])===0?3:(e.label.toLowerCase().indexOf(all[0])>=0?2:1);
  }
  function draw(){
    var words=box.querySelector('input').value.trim().toLowerCase();
    list=entries().map(function(e){ return {e:e,s:score(e,words)}; }).filter(function(x){ return x.s>0; })
      .sort(function(a,b){ return b.s-a.s||a.e.rank-b.e.rank||a.e.label.localeCompare(b.e.label); })
      .slice(0,60).map(function(x){ return x.e; });
    at=Math.min(at,Math.max(0,list.length-1));
    box.querySelector('.pal-list').innerHTML=list.length?list.map(function(e,n){
      return '<div class="pal-row'+(n===at?' on':'')+'" data-n="'+n+'" role="option" aria-selected="'+(n===at)+'">'
        +'<span class="pal-l">'+esc(e.label)+'</span><span class="pal-g">'+esc(e.group)+'</span>'
        +(e.keys?'<kbd>'+esc(e.keys)+'</kbd>':'')+'</div>';
    }).join(''):'<div class="pal-none">'+(mode==='fields'?'No field matches.':'No command matches.')+'</div>';
    var on=box.querySelector('.pal-row.on'); if(on) on.scrollIntoView({block:'nearest'});
  }
  function close(){ if(box){ box.remove(); box=null; } }
  function go(n){ var e=list[n]; close(); if(e) e.run(); }
  function open(m){
    m=m==='fields'?'fields':'';
    if(box&&mode===m){ box.querySelector('input').focus(); return; }
    close(); mode=m;
    if(m==='fields'&&!LABELS){ labels().then(function(){ open('fields'); }); return; }
    box=document.createElement('div'); box.className='pal-back'; box.id='palette';
    box.innerHTML='<div class="pal" role="dialog" aria-label="Command palette"><input type="text" placeholder="'+(m==='fields'?'Type a field: gross living area, 10.012\u2026':'Type a command or a section\u2026')+'" aria-label="'+(m==='fields'?'Field':'Command')+'">'
      +'<div class="pal-list" role="listbox"></div></div>';
    document.body.appendChild(box);
    var inp=box.querySelector('input');
    at=0; draw(); inp.focus();
    inp.addEventListener('input',function(){ at=0; draw(); });
    inp.addEventListener('keydown',function(e){
      if(e.key==='ArrowDown'||e.key==='ArrowUp'){ e.preventDefault(); at=(at+(e.key==='ArrowDown'?1:-1)+list.length)%Math.max(1,list.length); draw(); }
      else if(e.key==='Enter'){ e.preventDefault(); go(at); }
      else if(e.key==='Escape'){ e.preventDefault(); e.stopPropagation(); close(); }
    });
    box.addEventListener('mousedown',function(e){ if(e.target===box) close(); });
    box.addEventListener('click',function(e){ var r=e.target.closest('.pal-row'); if(r) go(Number(r.dataset.n)); });
  }
  if(UADShell.escape&&UADShell.escape.register)
    UADShell.escape.register({id:'palette',order:1,open:function(){ return !!box; },close:close});
  UADShell.palette={open:open,close:close,entries:entries};
})();
