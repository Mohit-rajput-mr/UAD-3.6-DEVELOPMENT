/* Every region is a window (owner 2026-10-11, T-1210; DR phase 2 step S2 /
   T-273, _work/dr/PHASE2_SHELL_PLAN.md).

   The Sections rail (left), the side panels (right: Field guidance,
   Sign-off, ...), the top bar and the report each carry window controls --
   minimize (to the tray at the bottom left), maximize (the region takes the
   work area), close (gone until restored from the tray's Windows list) and,
   for the side regions, a splitter to drag to any width (double-click
   resets).  The state is the user's (UADShell.state 'win', 'left.w',
   'right.w'), so the editor opens as it was left.  The Sketch window uses the
   same tray and buttons (index.html openSketch).

   The rail and the side panels are wrapped, not rebuilt: #rail and #insp keep
   their ids and their content is still drawn by index.html, so nothing that
   writes into them changes.  The report frame is never reloaded: only the
   grid around it moves, and the page inside fits itself to the new width. */
(function(){
  if(!window.UADShell||!UADShell.enabled()) return;
  var S=UADShell.state;
  var REGIONS={
    left:{title:'Sections',icon:'☰'},
    right:{title:'Side panels',icon:'▤'},
    top:{title:'Top bar',icon:'▔'},
    report:{title:'Report',icon:'▣'},
    sketch:{title:'Sketch',icon:'✎'}
  };
  var DEF_W={left:220,right:340};
  function $(s,r){ return (r||document).querySelector(s); }
  function el(tag,cls,html){ var e=document.createElement(tag); if(cls) e.className=cls; if(html!=null) e.innerHTML=html; return e; }
  function mode(k){ return S.get('win.'+k)||'normal'; }
  function setMode(k,m){ S.set('win.'+k,m); apply(); UADShell.emit('win',{region:k,mode:m}); }

  /* the buttons every window bar carries: what a window offers in its state */
  function buttons(k,opts){
    opts=opts||{};
    var m=mode(k), b='';
    if(opts.min!==false) b+='<button type="button" class="wb wb-min" data-win="'+k+'" data-act="min" title="Minimize to the tray" aria-label="Minimize '+REGIONS[k].title+'">&#8211;</button>';
    if(opts.max!==false) b+=m==='max'
      ?'<button type="button" class="wb wb-res" data-win="'+k+'" data-act="normal" title="Restore" aria-label="Restore '+REGIONS[k].title+'">&#10064;</button>'
      :'<button type="button" class="wb wb-max" data-win="'+k+'" data-act="max" title="Maximize" aria-label="Maximize '+REGIONS[k].title+'">&#9633;</button>';
    if(opts.close!==false) b+='<button type="button" class="wb wb-close" data-win="'+k+'" data-act="closed" title="Close (restore it from Windows, bottom left)" aria-label="Close '+REGIONS[k].title+'">&#215;</button>';
    return b;
  }
  function bar(k,title){
    return '<div class="winbar" data-region="'+k+'"><span class="wt">'+title+'</span><span class="wbs">'+buttons(k)+'</span></div>';
  }

  /* ------------------------------------------------------------- build */
  function wrap(id,dockId,k){
    var inner=document.getElementById(id);
    if(!inner) return null;
    var dock=document.getElementById(dockId);
    if(dock&&dock.contains(inner)) return dock;
    dock=el('div','dock dock-'+k);
    dock.id=dockId;
    dock.setAttribute('data-region',k);
    inner.parentNode.insertBefore(dock,inner);
    dock.insertAdjacentHTML('beforeend',bar(k,REGIONS[k].title));
    dock.appendChild(inner);
    var sp=el('div','dock-split');
    sp.setAttribute('data-region',k);
    sp.title='Drag to resize · double-click resets';
    sp.setAttribute('role','separator');
    sp.setAttribute('aria-orientation','vertical');
    dock.appendChild(sp);
    splitter(sp,k);
    return dock;
  }
  function build(){
    var shell=document.getElementById('shell');
    if(!shell||shell.classList.contains('launcher')) return;
    wrap('rail','dock-l','left');
    wrap('insp','dock-r','right');
    var work=shell.querySelector('section.work');
    if(work&&!work.querySelector('.winctl-report')){
      var c=el('div','winctl winctl-report');
      c.setAttribute('data-region','report');
      work.appendChild(c);
    }
    var head=document.querySelector('body > header');
    if(head&&!head.querySelector('.winctl-top')){
      var t=el('div','winctl winctl-top');
      t.setAttribute('data-region','top');
      head.appendChild(t);
    }
    apply();
    zoomSend();
  }

  /* ------------------------------------------------------------- apply */
  function apply(){
    var body=document.body;
    ['top','left','right','report'].forEach(function(k){
      ['min','max','closed'].forEach(function(m){ body.classList.toggle('win-'+k+'-'+m,mode(k)===m); });
    });
    var root=document.documentElement;
    root.style.setProperty('--wl',(S.get('left.w')||DEF_W.left)+'px');
    root.style.setProperty('--wr',(S.get('right.w')||DEF_W.right)+'px');
    document.querySelectorAll('.winbar[data-region]').forEach(function(b){
      var k=b.getAttribute('data-region'); var s=b.querySelector('.wbs'); if(s) s.innerHTML=buttons(k);
    });
    var rc=$('.winctl-report');
    if(rc){ rc.innerHTML=zoomButtons()+buttons('report',{min:false,close:false}); zoomLabel(); }
    var tc=$('.winctl-top');
    if(tc) tc.innerHTML=buttons('top',{max:false});
    tray();
    // the report fits itself to its new width (it listens to resize)
    try{ var f=document.getElementById('rf'); if(f&&f.contentWindow) f.contentWindow.dispatchEvent(new Event('resize')); }catch(_){}
  }

  /* -------------------------------------------------------------- zoom
     The report's size (owner 2026-10-11: "report looks too small").  Fit
     (the default) fills the report window's width and grows into the room
     the other windows give up; - and + set a fixed 50-200 %.  A kept frame
     message, so a reloaded or swapped-in page is drawn the same. */
  var ZAT=null;                                  // what the page is drawn at
  function zoomPref(){ var z=S.get('zoom'); return typeof z==='number'?z:'fit'; }
  function zoomSend(){
    var z=zoomPref();
    if(UADShell.frames&&UADShell.frames.keep) UADShell.frames.keep('zoom',{uad:'zoom',z:z==='fit'?'width':z});
  }
  function zoomSet(z){
    if(z!=='fit') z=Math.round(Math.max(0.5,Math.min(2,z))*20)/20;   // 5 % steps
    S.set('zoom',z); zoomSend(); zoomLabel();
  }
  function zoomStep(d){ var z=zoomPref(); zoomSet((typeof z==='number'?z:(ZAT||1))+d); }
  function zoomButtons(){
    return '<span class="wz" role="group" aria-label="Report size">'
      +'<button type="button" class="wb" data-act="zout" title="Smaller (Ctrl+-)" aria-label="Smaller">&#8722;</button>'
      +'<button type="button" class="wb wz-v" data-act="zfit" title="Fit the window\'s width (Ctrl+0)" aria-label="Fit width"></button>'
      +'<button type="button" class="wb" data-act="zin" title="Larger (Ctrl+=)" aria-label="Larger">+</button></span>';
  }
  function zoomLabel(){
    var b=$('.winctl-report .wz-v'); if(!b) return;
    var z=zoomPref(), n=Math.round((typeof z==='number'?z:(ZAT||1))*100);
    b.textContent=(z==='fit'?'Fit ':'')+n+'%';
    b.classList.toggle('on',z==='fit');
  }
  UADShell.on('frame:zoom-at',function(d){
    if(UADShell.frames.activePane&&d.pane!==UADShell.frames.activePane()) return;
    var z=d.msg&&d.msg.z; if(typeof z==='number'&&isFinite(z)){ ZAT=z; zoomLabel(); }
  });

  /* -------------------------------------------------------------- tray */
  function tray(){
    var t=document.getElementById('wintray');
    var inCase=document.body.classList.contains('shell-case');
    if(!t){ t=el('div','wintray'); t.id='wintray'; t.setAttribute('role','toolbar'); t.setAttribute('aria-label','Windows'); document.body.appendChild(t); }
    t.hidden=!inCase;
    var chips='';
    Object.keys(REGIONS).forEach(function(k){
      var m=mode(k);
      if(k==='sketch'&&!document.getElementById('sketch-ov')) return;
      if(m==='min') chips+='<button type="button" class="wchip" data-win="'+k+'" data-act="normal" title="Restore '+REGIONS[k].title+'">'+REGIONS[k].icon+' '+REGIONS[k].title+'</button>';
    });
    t.innerHTML='<button type="button" class="wchip wmenu" data-act="menu" aria-haspopup="true" title="Every window: restore, minimize, maximize, close">&#10697; Windows</button>'+chips;
  }
  function menu(anchor){
    var old=document.getElementById('winmenu'); if(old){ old.remove(); return; }
    var m=el('div','winmenu'); m.id='winmenu'; m.setAttribute('role','menu');
    var rows='';
    Object.keys(REGIONS).forEach(function(k){
      if(k==='sketch'&&!document.getElementById('sketch-ov')) return;
      var st=mode(k), label={normal:'open',min:'minimized',max:'maximized',closed:'closed'}[st];
      rows+='<div class="wm-row"><span class="wm-t">'+REGIONS[k].icon+' '+REGIONS[k].title+' <small>'+label+'</small></span><span class="wm-b">'
        +(st!=='normal'?'<button type="button" data-win="'+k+'" data-act="normal">Restore</button>':'')
        +(st!=='max'&&k!=='top'?'<button type="button" data-win="'+k+'" data-act="max">Maximize</button>':'')
        +(st!=='min'&&k!=='report'?'<button type="button" data-win="'+k+'" data-act="min">Minimize</button>':'')
        +(st!=='closed'&&k!=='report'?'<button type="button" data-win="'+k+'" data-act="closed">Close</button>':'')
        +'</span></div>';
    });
    rows+='<div class="wm-row wm-reset"><button type="button" data-act="reset">Reset the layout</button></div>';
    m.innerHTML=rows;
    document.body.appendChild(m);
    var r=anchor.getBoundingClientRect();
    m.style.left=Math.max(8,r.left)+'px';
    m.style.bottom=(window.innerHeight-r.top+6)+'px';
  }

  /* ----------------------------------------------------------- actions */
  function act(k,a){
    if(k==='sketch'){ UADShell.emit('sketch-cmd',{act:a}); return; }
    if(a==='max'){
      // one region takes the work area: the others step aside, and come back on restore
      ['left','right','report'].forEach(function(o){ if(o!==k&&mode(o)==='max') S.set('win.'+o,'normal'); });
    }
    setMode(k,a);
  }
  document.addEventListener('click',function(e){
    var b=e.target.closest&&e.target.closest('[data-act]');
    if(!b) { var mm=document.getElementById('winmenu'); if(mm&&!e.target.closest('#winmenu')) mm.remove(); return; }
    if(!b.closest('.winbar,.winctl,#wintray,#winmenu,.sketch-ov')) return;
    var a=b.getAttribute('data-act'), k=b.getAttribute('data-win');
    if(a==='menu'){ menu(b); return; }
    if(a==='zin'){ zoomStep(0.1); return; }
    if(a==='zout'){ zoomStep(-0.1); return; }
    if(a==='zfit'){ zoomSet('fit'); return; }
    var m=document.getElementById('winmenu'); if(m) m.remove();
    if(a==='reset'){
      ['top','left','right','report'].forEach(function(o){ S.set('win.'+o,'normal'); });
      S.set('left.w',DEF_W.left); S.set('right.w',DEF_W.right); apply(); return;
    }
    if(k&&REGIONS[k]) act(k,a);
  });

  /* ---------------------------------------------------------- splitter */
  function splitter(sp,k){
    sp.addEventListener('pointerdown',function(e){
      if(e.button!==0) return;
      e.preventDefault();
      var dock=sp.parentNode, start=e.clientX, w0=dock.getBoundingClientRect().width;
      try{ sp.setPointerCapture(e.pointerId); }catch(_){}
      document.body.classList.add('shell-drag');
      function move(ev){
        var dx=ev.clientX-start, w=k==='left'?w0+dx:w0-dx;
        w=Math.max(160,Math.min(Math.round(window.innerWidth*0.6),Math.round(w)));
        document.documentElement.style.setProperty(k==='left'?'--wl':'--wr',w+'px');
      }
      function up(ev){
        sp.removeEventListener('pointermove',move); sp.removeEventListener('pointerup',up); sp.removeEventListener('pointercancel',up);
        document.body.classList.remove('shell-drag');
        var w=parseInt(getComputedStyle(document.documentElement).getPropertyValue(k==='left'?'--wl':'--wr'),10);
        if(isFinite(w)) S.set(k+'.w',w);
        if(mode(k)!=='normal') S.set('win.'+k,'normal');
        apply();
      }
      sp.addEventListener('pointermove',move); sp.addEventListener('pointerup',up); sp.addEventListener('pointercancel',up);
    });
    sp.addEventListener('dblclick',function(){ S.set(k+'.w',DEF_W[k]); apply(); });
  }

  /* --------------------------------------------- keys and the Esc stack */
  if(UADShell.commands&&UADShell.commands.register){
    UADShell.commands.register({id:'win.report.max',label:'Report: maximize / restore (focus)',group:'View',keys:['F11'],
      run:function(){ act('report',mode('report')==='max'?'normal':'max'); }});
    UADShell.commands.register({id:'win.left',label:'Sections window: show / hide',group:'View',
      run:function(){ act('left',mode('left')==='normal'?'min':'normal'); }});
    UADShell.commands.register({id:'win.right',label:'Side panels window: show / hide',group:'View',
      run:function(){ act('right',mode('right')==='normal'?'min':'normal'); }});
    UADShell.commands.register({id:'win.top',label:'Top bar: show / hide',group:'View',
      run:function(){ act('top',mode('top')==='normal'?'min':'normal'); }});
    UADShell.commands.register({id:'zoom.in',label:'Report: larger',group:'View',keys:['Ctrl+=','Ctrl+Shift++'],run:function(){ zoomStep(0.1); }});
    UADShell.commands.register({id:'zoom.out',label:'Report: smaller',group:'View',keys:['Ctrl+-'],run:function(){ zoomStep(-0.1); }});
    UADShell.commands.register({id:'zoom.fit',label:'Report: fit the window\'s width',group:'View',keys:['Ctrl+0'],run:function(){ zoomSet('fit'); }});
    UADShell.commands.register({id:'win.reset',label:'Reset the window layout',group:'View',
      run:function(){ ['top','left','right','report'].forEach(function(o){ S.set('win.'+o,'normal'); }); apply(); }});
  }
  if(UADShell.escape&&UADShell.escape.register){
    UADShell.escape.register({id:'win-report-max',order:7,
      open:function(){ return mode('report')==='max'; },
      close:function(){ act('report','normal'); }});
  }

  UADShell.on('shell-built',build);
  UADShell.on('insp',function(){ if(!document.getElementById('dock-r')) build(); });
  UADShell.on('case-open',function(){ setTimeout(build,0); });
  UADShell.on('case-close',function(){ tray(); });
  UADShell.on('sketch-win',function(){ tray(); });
  window.addEventListener('resize',function(){ tray(); });
  UADShell.windows={mode:mode,set:act,apply:apply,regions:REGIONS,buttons:buttons};
  if(document.getElementById('rail')) build();
})();
