/* The Problems side panel: live filters, click to field, F8 (DR phase 2,
   step S4 / T-505; _work/dr/PHASE2_SHELL_PLAN.md "Problems side panel").

   Every problem the Review Master finds, beside the report and never over
   it: counted for the whole report whatever the filter, filtered by severity
   (kept in the shell state) and by words (this session only), grouped by
   section, and one click away from its field -- the same jump() the Review
   Master view uses.  F8 / Shift+F8 step through them.  Redraws on the
   'review' bus event setReview() raises, so it follows every save, and keeps
   what was open and where it was scrolled. */
(function(){
  if(!window.UADShell||!UADShell.enabled()) return;
  var S_=UADShell.state;
  var SEV=[{k:'Fatal',t:'Fatal'},{k:'Warning',t:'Warning'},{k:'Review',t:'Info'}];
  var el=document.createElement('div'); el.className='prb';
  var q='', at=-1, shown=[], lastKey='', closed={};
  function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function items(){ var r=(typeof S!=='undefined')&&S.review; return (r&&r.items)||[]; }
  function sevOn(){ var v=S_.get('problems.sev'); return Array.isArray(v)&&v.length?v:['Fatal','Warning']; }
  function notCounted(i){ return /^not counted/.test(i.detail||''); }
  function sevOf(i){ return i.severity==='Fatal'||i.severity==='Warning'?i.severity:'Review'; }
  function key(i){ return [i.code,i.field_id||'',i.path||'',i.message||''].join('|'); }
  function sectionName(i){
    if(i.section) return i.section;
    var s=((typeof S!=='undefined'&&S.sections)||[]).filter(function(x){ return x.number===i.section_number; })[0];
    return s?s.name:(i.source==='schema'?'Document structure (XSD)':'Whole report');
  }
  function filtered(){
    var on=sevOn(), words=q.trim().toLowerCase();
    return items().filter(function(i){
      if(on.indexOf(sevOf(i))<0) return false;
      if(!words) return true;
      return [i.code,i.message,i.label,i.field_id,i.section].join(' ').toLowerCase().indexOf(words)>=0;
    });
  }
  function draw(force){
    var all=items(), list=filtered();
    var k=sevOn().join(',')+'#'+q+'#'+all.map(key).join('\n');
    if(!force&&k===lastKey) return;
    lastKey=k;
    var counts={Fatal:0,Warning:0,Review:0};
    all.forEach(function(i){ if(!notCounted(i)) counts[sevOf(i)]++; });
    var chips=SEV.map(function(s){
      var on=sevOn().indexOf(s.k)>=0;
      return '<button type="button" class="prb-chip '+s.k+(on?' on':'')+'" data-sev="'+s.k+'" aria-pressed="'+on+'">'
        +s.t+' <b>'+counts[s.k]+'</b></button>';
    }).join('');
    // grouped by section, in report order; what is not counted goes last, folded
    var groups={}, order=[];
    list.forEach(function(i){
      var g=notCounted(i)?'Not counted (a section this report leaves out)':sectionName(i);
      if(!groups[g]){ groups[g]=[]; order.push({g:g,n:notCounted(i)?999:(i.section_number||(i.source==='schema'?0:998))}); }
      groups[g].push(i);
    });
    order.sort(function(a,b){ return a.n-b.n; });
    shown=[];
    var body=order.map(function(o){
      var rows=groups[o.g], fold=closed[o.g]!==undefined?closed[o.g]:o.n===999;
      var html='<div class="prb-g'+(fold?' shut':'')+'" data-g="'+esc(o.g)+'"><button type="button" class="prb-gh">'
        +'<span>'+esc(o.g)+'</span><b>'+rows.length+'</b></button><div class="prb-rows">';
      rows.forEach(function(i){
        var n=shown.length; shown.push(i);
        html+='<div class="prb-row '+sevOf(i)+(i.field_id?' go':'')+'" data-n="'+n+'" tabindex="0" title="'+esc(i.message)+'">'
          +'<i></i><span class="prb-m">'+esc(i.message)+'</span>'
          +'<span class="prb-c">'+esc(i.code)+(i.field_id?' · '+esc(i.field_id):'')+'</span></div>';
      });
      return html+'</div></div>';
    }).join('');
    var scroll=el.querySelector('.prb-list'); var top=scroll?scroll.scrollTop:0;
    el.innerHTML='<div class="prb-bar">'+chips+'</div>'
      +'<input class="prb-q" type="search" placeholder="Find a problem…" aria-label="Find a problem" value="'+esc(q)+'">'
      +'<div class="prb-list">'+(body||'<div class="prb-none">'+(all.length?(q?'Nothing matches.':'None of the kinds selected.'):'No problems found.')+'</div>')+'</div>';
    // a repair the specification leaves one answer for (T-510, T-1201)
    if(typeof window.applyFixButton==='function'){
      el.querySelectorAll('.prb-row').forEach(function(r){
        var i=shown[Number(r.dataset.n)]; if(i&&i.fix){ var b=applyFixButton(i.fix); b.classList.add('prb-fix'); r.appendChild(b); }
      });
    }
    var list2=el.querySelector('.prb-list'); if(list2) list2.scrollTop=top;
    var bad=counts.Fatal;
    UADShell.panels.setBadge('problems',bad);
    var t=el.closest('.shell-panel'); var tt=t&&t.querySelector('.shell-panel-t');
    if(tt) tt.textContent='Problems';
  }
  function go(n){
    var i=shown[n]; if(!i) return;
    at=n;
    el.querySelectorAll('.prb-row.at').forEach(function(r){ r.classList.remove('at'); });
    var r=el.querySelector('.prb-row[data-n="'+n+'"]');
    if(r){ r.classList.add('at'); r.scrollIntoView({block:'nearest'}); }
    if(i.field_id&&typeof window.jump==='function') window.jump(i);
    else if(i.section_number&&typeof window.jump==='function') window.jump(i);
  }
  function step(d){
    if(!shown.length) draw(true);
    if(!shown.length) return;
    var n=at+d; if(n<0) n=shown.length-1; if(n>=shown.length) n=0;
    go(n);
  }
  el.addEventListener('click',function(e){
    var c=e.target.closest('.prb-chip');
    if(c){
      var on=sevOn().slice(), k=c.dataset.sev, i=on.indexOf(k);
      if(i>=0) on.splice(i,1); else on.push(k);
      S_.set('problems.sev',on.length?on:[k]); draw(true); return;
    }
    var h=e.target.closest('.prb-gh');
    if(h){ var g=h.parentNode; g.classList.toggle('shut'); closed[g.dataset.g]=g.classList.contains('shut'); return; }
    if(e.target.closest('.prb-fix')) return;
    var r=e.target.closest('.prb-row'); if(r) go(Number(r.dataset.n));
  });
  el.addEventListener('keydown',function(e){
    var r=e.target.closest&&e.target.closest('.prb-row');
    if(r&&(e.key==='Enter'||e.key===' ')){ e.preventDefault(); go(Number(r.dataset.n)); }
    if(r&&(e.key==='ArrowDown'||e.key==='ArrowUp')){
      e.preventDefault();
      var rows=[].slice.call(el.querySelectorAll('.prb-row')), i=rows.indexOf(r)+(e.key==='ArrowDown'?1:-1);
      if(rows[i]) rows[i].focus();
    }
  });
  el.addEventListener('input',function(e){
    if(!e.target.classList.contains('prb-q')) return;
    q=e.target.value; var pos=e.target.selectionStart;
    draw(true);
    var inp=el.querySelector('.prb-q'); if(inp){ inp.focus(); try{ inp.setSelectionRange(pos,pos); }catch(_){ } }
  });

  function mount(){ UADShell.panels.register({id:'problems',title:'Problems',el:el}); draw(true); }
  UADShell.on('insp',mount);
  UADShell.on('review',function(){ at=-1; draw(false); });
  UADShell.on('case-open',function(){ q=''; closed={}; lastKey=''; });
  if(UADShell.commands&&UADShell.commands.register){
    UADShell.commands.register({id:'problems.next',label:'Next problem',group:'Review',keys:['F8'],run:function(){ step(1); }});
    UADShell.commands.register({id:'problems.prev',label:'Previous problem',group:'Review',keys:['Shift+F8'],run:function(){ step(-1); }});
  }
  UADShell.problems={draw:draw,next:function(){ step(1); },prev:function(){ step(-1); },shown:function(){ return shown.slice(); }};
  if(document.getElementById('insp')) mount();
})();
