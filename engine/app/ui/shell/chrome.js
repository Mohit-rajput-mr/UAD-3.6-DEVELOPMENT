/* The status bar (DR phase 2, step S3 / T-276; _work/dr/PHASE2_SHELL_PLAN.md):
   one thin line under the work area -- the report type, the section on
   screen, when the report was last saved, the problems it has (a click opens
   them) and the size the report is drawn at.  Everything in it is read from
   what the editor already knows; nothing here is a control without a target.
   (Focus mode and zoom live with the report window, docks.js.) */
(function(){
  if(!window.UADShell||!UADShell.enabled()) return;
  var bar=null, st={section:'',saved:null,zoom:null};
  function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function hasS(){ return typeof S!=='undefined'&&S; }
  function sectionName(n){
    var s=hasS()&&(S.sections||[]).filter(function(x){ return x.number===n; })[0];
    return s?String(n).padStart(2,'0')+' '+s.name:'';
  }
  function counts(){
    var n={Fatal:0,Warning:0};
    ((hasS()&&S.review&&S.review.items)||[]).forEach(function(i){
      if(!/^not counted/.test(i.detail||'')&&n[i.severity]!==undefined) n[i.severity]++; });
    return n;
  }
  function draw(){
    if(!bar){
      bar=document.getElementById('statusbar');
      if(!bar){ bar=document.createElement('div'); bar.id='statusbar'; bar.setAttribute('role','status'); document.body.appendChild(bar); }
    }
    if(!hasS()||!S.case){ bar.innerHTML=''; return; }
    var c=counts(), t=(S.case.property_type||'').replace(/_/g,' ');
    var saved=st.saved?'Saved '+st.saved.toLocaleTimeString([],{hour:'2-digit',minute:'2-digit'}):'Saved';
    bar.innerHTML='<span class="sb-i sb-type">'+esc(t)+'</span>'
      +'<span class="sb-i sb-sec">'+esc(st.section||sectionName(S.section))+'</span>'
      +'<span class="sb-sp"></span>'
      +'<span class="sb-i sb-save">'+esc(saved)+'</span>'
      +'<button type="button" class="sb-i sb-prob" title="Show the problems">'
        +'<i class="f"></i>'+c.Fatal+' fatal <i class="w"></i>'+c.Warning+' warning</button>'
      +(st.zoom?'<span class="sb-i sb-zoom">'+Math.round(st.zoom*100)+'%</span>':'');
  }
  document.addEventListener('click',function(e){
    if(!e.target.closest('#statusbar .sb-prob')) return;
    var W=UADShell.windows;
    if(W&&W.mode('right')!=='normal') W.set('right','normal');
    var p=document.getElementById('shell-panel-problems');
    if(p){ p.scrollIntoView({block:'start'}); var r=p.querySelector('.prb-row'); if(r) r.focus(); }
  });
  UADShell.on('review',draw);
  UADShell.on('case-open',function(){ st={section:'',saved:null,zoom:st.zoom}; draw(); });
  UADShell.on('case-close',draw);
  UADShell.on('frame:saved',function(){ st.saved=new Date(); draw(); });
  UADShell.on('frame:at',function(d){ var n=d.msg&&d.msg.secn; if(n){ st.section=sectionName(Number(n)); draw(); } });
  UADShell.on('frame:zoom-at',function(d){ var z=d.msg&&d.msg.z; if(typeof z==='number'){ st.zoom=z; draw(); } });
  UADShell.on('insp',draw);
  UADShell.statusbar={draw:draw};
})();
