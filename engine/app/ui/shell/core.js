/* The editor shell's core (DR phase 2, step S0a; _work/dr/PHASE2_SHELL_PLAN.md).

   window.UADShell is the one place the shell modules meet:

     enabled()      the kill switch.  On by default; ?shell=0 (or localStorage
                    uad-shell=off) gives the classic editor and is remembered,
                    ?shell=1 brings the shell back.  Under the shell <body>
                    carries class "shell" and every shell rule is scoped to it.
     on / emit      the bus.  index.html raises DOM CustomEvents 'uad:<name>'
                    (shellEmit: case-open, case-close, shell-built, view, head,
                    form-drawn, insp, write, review); modules listen here.
     state          per-browser layout state, localStorage 'uad-shell-v1',
                    versioned, clamped on load, every access in try/catch.
     commands       the one registry behind the ribbon, palette, keys, tests.
     panels         side panels; a stub host mounts them at the top of #insp
                    until docks.js installs the real one.
     keys / escape  one normaliser, one capture keydown listener, the combos
                    pushed to every report frame, one Esc priority stack.
     frames         the report panes (#rf is pane 1, #rf2 pane 2): send to all
                    or to the active one, and replay what a fresh frame must
                    know (theme, gaps, imported, marks, side, zoom, keys).

   The frames registry and the bus serve the classic editor too (?shell=0):
   they carry the fix for outlines lost after a swap (CATALOG E-189) without
   changing what the classic editor shows.  Everything that changes the
   screen or the keyboard is gated by enabled(). */
(function(){
  'use strict';
  if(window.UADShell) return;

  var FLAG='uad-shell', STORE='uad-shell-v1', VERSION=1;
  function lsGet(k){ try{ return localStorage.getItem(k); }catch(_){ return null; } }
  function lsSet(k,v){ try{ localStorage.setItem(k,v); }catch(_){ } }

  /* ------------------------------------------------------------ kill switch */
  var ON=(function(){
    var q=null;
    try{ q=new URLSearchParams(location.search).get('shell'); }catch(_){ }
    if(q==='0'||q==='off'){ lsSet(FLAG,'off'); return false; }
    if(q==='1'||q==='on'){ lsSet(FLAG,'on'); return true; }
    return lsGet(FLAG)!=='off';
  })();
  if(ON&&document.body) document.body.classList.add('shell');
  function enabled(){ return ON; }

  /* -------------------------------------------------------------------- bus */
  function on(t,fn){
    var h=function(e){ fn(e.detail,e); };
    document.addEventListener('uad:'+t,h);
    return function(){ document.removeEventListener('uad:'+t,h); };
  }
  function emit(t,d){ document.dispatchEvent(new CustomEvent('uad:'+t,{detail:d})); }
  /* body.shell-case while a report is open: the launcher keeps its own look */
  if(ON){
    on('case-open',function(){ document.body.classList.add('shell-case'); });
    on('case-close',function(){ document.body.classList.remove('shell-case'); });
  }

  /* ------------------------------------------------------------------ state */
  function vw(){ return window.innerWidth||1600; }
  function vh(){ return window.innerHeight||1000; }
  function defaults(){
    var wide=vw()>=1600;
    return {v:VERSION,
      ribbon:{tab:'home',collapsed:vh()<800},
      left:{w:220,pinned:wide,collapsed:!wide},
      right:{w:340,pinned:wide,collapsed:!wide,open:{problems:true,guide:true,signoff:true}},
      problems:{sev:['Fatal','Warning','schema'],src:[],group:'section',thisSection:false},
      split:{mode:'off',ratio:0.5},
      zoom:'fit',
      palette:{mru:[]},
      /* every region is a window (owner 2026-10-11, T-1210): 'normal',
         'min' (to the tray), 'max' (takes the work area) or 'closed' */
      win:{top:'normal',left:'normal',right:'normal',report:'normal',
           sketch:'max',sx:0.1,sy:0.08,sw:0.8,sh:0.84}};
  }
  function clamp(n,lo,hi){ return Math.max(lo,Math.min(hi,n)); }
  function merge(def,got){
    var out={};
    Object.keys(def).forEach(function(k){
      var d=def[k], g=got?got[k]:undefined;
      if(d&&typeof d==='object'&&!Array.isArray(d)) out[k]=merge(d,g&&typeof g==='object'?g:{});
      else if(Array.isArray(d)) out[k]=Array.isArray(g)?g.filter(function(x){ return typeof x==='string'; }):d.slice();
      else out[k]=(typeof g===typeof d&&!(typeof g==='number'&&!isFinite(g)))?g:d;
    });
    return out;
  }
  function sane(s){
    var maxW=Math.max(180,Math.round(vw()*0.5));
    s.left.w=clamp(s.left.w,180,maxW);
    s.right.w=clamp(s.right.w,180,maxW);
    s.split.ratio=clamp(s.split.ratio,0.2,0.8);
    if(['off','side','stacked'].indexOf(s.split.mode)<0) s.split.mode='off';
    if(['section','severity','rule'].indexOf(s.problems.group)<0) s.problems.group='section';
    s.palette.mru=s.palette.mru.slice(0,30);
    ['top','left','right','report','sketch'].forEach(function(k){
      if(['normal','min','max','closed'].indexOf(s.win[k])<0) s.win[k]=k==='sketch'?'max':'normal';
    });
    s.win.sw=clamp(s.win.sw,0.25,1); s.win.sh=clamp(s.win.sh,0.25,1);
    s.win.sx=clamp(s.win.sx,0,1-s.win.sw); s.win.sy=clamp(s.win.sy,0,1-s.win.sh);
    return s;
  }
  function loadState(){
    var raw=lsGet(STORE), got=null;
    try{ got=raw?JSON.parse(raw):null; }catch(_){ got=null; }
    if(!got||got.v!==VERSION) got=null;
    var s=sane(merge(defaults(),got||{}));
    // zoom is 'fit' (the page fits the report window's width) or a size, 50-200 %
    var z=got&&got.zoom;
    s.zoom=(typeof z==='number'&&isFinite(z))?clamp(z,0.5,2):'fit';
    return s;
  }
  var ST=loadState();
  function walk(path,make){
    var parts=String(path).split('.'), o=ST;
    for(var i=0;i<parts.length-1;i++){
      if(o[parts[i]]==null||typeof o[parts[i]]!=='object'){ if(!make) return [null,null]; o[parts[i]]={}; }
      o=o[parts[i]];
    }
    return [o,parts[parts.length-1]];
  }
  var state={
    get:function(path){ if(!path) return ST; var w=walk(path,false); return w[0]?w[0][w[1]]:undefined; },
    set:function(path,value){
      var w=walk(path,true); w[0][w[1]]=value;
      ST=sane(ST); lsSet(STORE,JSON.stringify(ST));
      emit('shell-state',{path:path,value:value});
      return value;
    },
    defaults:defaults,
    reset:function(){ ST=sane(defaults()); lsSet(STORE,JSON.stringify(ST)); emit('shell-state',{path:'',value:ST}); }
  };

  /* ---------------------------------------------------------------- keymap */
  var MAC=/Mac|iPhone|iPad/.test((navigator.platform||'')+(navigator.userAgent||''));
  function normalise(e){
    var k=e.key;
    if(!k||k==='Control'||k==='Shift'||k==='Alt'||k==='Meta'||k==='Dead'||k==='Unidentified') return '';
    if(k===' ') k='Space';
    else if(k.length===1) k=k.toUpperCase();
    var ctrl=MAC?e.metaKey:e.ctrlKey;
    return (ctrl?'Ctrl+':'')+(e.altKey?'Alt+':'')+(e.shiftKey?'Shift+':'')+k;
  }
  /* 'ctrl+shift+s', 'Shift+F8', 'Ctrl+\\' -> the normaliser's own spelling */
  function combo(spec){
    var s=String(spec||'').trim(); if(!s) return '';
    var parts=s.split('+'), key=parts.pop();
    if(key===''&&parts.length&&parts[parts.length-1]===''){ parts.pop(); key='+'; }
    var m={ctrl:false,alt:false,shift:false};
    parts.forEach(function(p){
      p=p.toLowerCase();
      if(p==='ctrl'||p==='control'||p==='cmd'||p==='meta'||p==='mod') m.ctrl=true;
      else if(p==='alt'||p==='option') m.alt=true;
      else if(p==='shift') m.shift=true;
    });
    if(key===' '||key.toLowerCase()==='space') key='Space';
    else if(key.length===1) key=key.toUpperCase();
    else if(/^esc(ape)?$/i.test(key)) key='Escape';
    else if(/^f\d{1,2}$/i.test(key)) key=key.toUpperCase();
    return (m.ctrl?'Ctrl+':'')+(m.alt?'Alt+':'')+(m.shift?'Shift+':'')+key;
  }
  var KEYMAP={};
  function rebuildKeys(){
    KEYMAP={};
    ORDER.forEach(function(id){
      (CMDS[id].keys||[]).forEach(function(k){ var c=combo(k); if(c&&!KEYMAP[c]) KEYMAP[c]=id; });
    });
    clearTimeout(rebuildKeys.t);
    rebuildKeys.t=setTimeout(function(){ frames.all().forEach(function(f){ pushKeys(f.win); }); },0);
  }
  function combos(){ return Object.keys(KEYMAP); }
  function pushKeys(win){
    if(!ON||!win) return;
    try{ win.postMessage({uad:'shell-keys',combos:combos()},'*'); }catch(_){ }
  }
  function typing(t){
    return !!(t&&(t.isContentEditable||/^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName||'')));
  }
  function modalOpen(){ return !!document.querySelector('.uadd-back'); }
  /* a combo from the parent's keydown or forwarded by a report frame */
  function dispatch(c,ctx){
    var id=KEYMAP[c]; if(!id) return false;
    var cmd=CMDS[id]; if(!cmd||(cmd.when&&!cmd.when())) return false;
    run(id,Object.assign({via:'key',combo:c},ctx||{}));
    return true;
  }
  document.addEventListener('keydown',function(e){
    if(!ON) return;
    if(e.key==='Escape'){ escKey(e); return; }
    if(e.defaultPrevented||e.isComposing||modalOpen()) return;
    var c=normalise(e); if(!c||!KEYMAP[c]) return;
    // a plain character (with or without Shift) is never taken from a field
    if(typing(e.target)&&/^(Shift\+)?.$/.test(c)) return;
    var cmd=CMDS[KEYMAP[c]]; if(!cmd||(cmd.when&&!cmd.when())) return;
    e.preventDefault(); e.stopPropagation();
    dispatch(c,{pane:0});
  },true);

  /* ---------------------------------------------------------- Esc priority
     1 palette, 2 marker card       -- closed here, first
     3 UADDialog, 4 #libpop / sheets, 5 the worksheet drawer
                                    -- their own handlers act; the shell yields
     6 an open dock shutter, 7 focus mode
                                    -- closed here, last
     Inside a report frame EDIT_JS keeps first claim (a field reverts, a list
     closes) and never forwards Esc; its 'ws-esc' arrives when nothing there
     took it, and runs the late steps when no worksheet is open. */
  var ESC=[];
  function nativeOpen(){
    return modalOpen()||!!document.querySelector('#libpop,.su-veil,.sheet')
      ||document.body.classList.contains('ws-open');
  }
  /* close the first open item with from <= order < upto; true when one was */
  function escRun(from,e,upto){
    var items=ESC.slice().sort(function(a,b){ return a.order-b.order; });
    for(var i=0;i<items.length;i++){
      var it=items[i];
      if(it.order<from||(upto&&it.order>=upto)) continue;
      if(it.order>=3&&it.order<6) continue;
      var open=false; try{ open=!!it.open(); }catch(_){ }
      if(!open) continue;
      if(e){ e.preventDefault(); e.stopImmediatePropagation(); }
      it.close();
      return true;
    }
    return false;
  }
  function escKey(e){
    if(e.defaultPrevented||modalOpen()) return;
    if(escRun(0,e,3)) return;                  // the palette, the marker card
    if(nativeOpen()) return;                   // their own handlers act
    escRun(6,e);                               // a dock shutter, focus mode
  }
  var escape={
    /* {id, order (1-7, see above), open:()=>bool, close:()=>void} */
    register:function(item){
      ESC=ESC.filter(function(x){ return x.id!==item.id; });
      ESC.push(item); return item;
    },
    list:function(){ return ESC.slice(); },
    /* what an Esc that nothing in a frame took does: the late steps */
    late:function(){ if(!ON||nativeOpen()) return false; return escRun(6,null); }
  };

  /* -------------------------------------------------------------- commands */
  var CMDS={}, ORDER=[];
  function adoptEl(cmd){ return cmd&&cmd.adopt?document.querySelector(cmd.adopt):null; }
  function run(id,ctx){
    var cmd=CMDS[id];
    if(!cmd) return false;                     // modules land in any order
    if(cmd.when&&!cmd.when()) return false;
    if(typeof cmd.run==='function') { var r=cmd.run(ctx||{}); recent(id); return r===undefined?true:r; }
    var el=adoptEl(cmd);
    if(el&&!el.disabled){ el.click(); recent(id); return true; }
    return false;
  }
  function recent(id){
    if(!ON) return;
    var mru=(ST.palette.mru||[]).filter(function(x){ return x!==id; });
    mru.unshift(id); ST.palette.mru=mru.slice(0,30);
    lsSet(STORE,JSON.stringify(ST));
  }
  var commands={
    /* {id, label, tab, group, icon, keys, run, when, state, adopt:'#id'} */
    register:function(spec){
      if(!spec||!spec.id) throw new Error('UADShell.commands.register: an id is required');
      if(!CMDS[spec.id]) ORDER.push(spec.id);
      CMDS[spec.id]=spec;
      if(spec.keys&&spec.keys.length) rebuildKeys();
      emit('commands',{id:spec.id});
      return spec;
    },
    unregister:function(id){
      if(!CMDS[id]) return;
      delete CMDS[id]; ORDER=ORDER.filter(function(x){ return x!==id; });
      rebuildKeys(); emit('commands',{id:id});
    },
    run:run,
    get:function(id){ return CMDS[id]||null; },
    has:function(id){ return !!CMDS[id]; },
    list:function(){ return ORDER.map(function(id){ return CMDS[id]; }); },
    /* can it run now: its predicate, and an adopted original that is not disabled */
    available:function(id){
      var cmd=CMDS[id]; if(!cmd) return false;
      if(cmd.when&&!cmd.when()) return false;
      if(typeof cmd.run==='function') return true;
      var el=adoptEl(cmd); return !!(el&&!el.disabled);
    }
  };
  var keys={normalise:normalise,combo:combo,combos:combos,dispatch:dispatch,
    map:function(){ return Object.assign({},KEYMAP); }};

  /* ---------------------------------------------------------------- panels
     docks.js (S2) installs the real host with panels.useHost(host); until
     then a stub mounts each registered panel at the top of #insp. */
  var PANELS={}, PORDER=[];
  function wrap(p){
    if(p.box) return p.box;
    var box=document.createElement('section');
    box.className='shell-panel'; box.id='shell-panel-'+p.id; box.dataset.panel=p.id;
    var h=document.createElement('div'); h.className='panelhead k';
    var t=document.createElement('span'); t.className='shell-panel-t'; t.textContent=p.title||p.id;
    var b=document.createElement('span'); b.className='shell-panel-badge'; b.hidden=true;
    h.appendChild(t); h.appendChild(b); box.appendChild(h);
    if(p.el) box.appendChild(p.el);
    p.box=box; return box;
  }
  var stubHost={
    mount:function(){
      var insp=document.getElementById('insp'); if(!insp) return;
      var want=PORDER.map(function(id){ return wrap(PANELS[id]); });
      if(want.every(function(b,i){ return insp.children[i]===b; })) return;
      want.forEach(function(b){ if(b.parentNode) b.parentNode.removeChild(b); });
      var first=insp.firstChild;
      want.forEach(function(b){ insp.insertBefore(b,first); });
    },
    unmount:function(p){ if(p.box&&p.box.parentNode) p.box.parentNode.removeChild(p.box); }
  };
  var HOST=stubHost;
  function mountAll(){ if(ON&&PORDER.length) HOST.mount(); }
  var panels={
    /* {id, title, icon, el, badge, side} */
    register:function(p){
      if(!p||!p.id) throw new Error('UADShell.panels.register: an id is required');
      if(!PANELS[p.id]) PORDER.push(p.id);
      PANELS[p.id]=p; mountAll(); emit('panels',{id:p.id});
      return p;
    },
    unregister:function(id){
      var p=PANELS[id]; if(!p) return;
      try{ HOST.unmount&&HOST.unmount(p); }catch(_){ }
      delete PANELS[id]; PORDER=PORDER.filter(function(x){ return x!==id; });
      emit('panels',{id:id});
    },
    get:function(id){ return PANELS[id]||null; },
    list:function(){ return PORDER.map(function(id){ return PANELS[id]; }); },
    setBadge:function(id,n){
      var p=PANELS[id]; if(!p) return; p.badge=n;
      if(p.box){ var b=p.box.querySelector('.shell-panel-badge'); if(b){ b.hidden=!n; b.textContent=n?String(n):''; } }
      emit('panel-badge',{id:id,n:n});
    },
    useHost:function(h){
      PORDER.forEach(function(id){ try{ HOST.unmount&&HOST.unmount(PANELS[id]); }catch(_){ } });
      HOST=h||stubHost; mountAll();
    },
    host:function(){ return HOST; },
    wrap:wrap
  };
  on('shell-built',mountAll);
  on('insp',mountAll);

  /* ---------------------------------------------------------------- frames */
  var ACTIVE=1, KEPT={};
  var PANES=[['rf',1],['rf2',2]];
  /* a frame being loaded out of sight to replace a pane is not the pane yet:
     index.html's swaps live in S.swaps, split.js tags its own data-shell-swap */
  function isSwap(el){
    if(!el) return false;
    if(el.dataset&&el.dataset.shellSwap) return true;
    var sw=(typeof S!=='undefined'&&S)?S.swaps:null;
    if(sw) for(var k in sw){ if(sw[k]===el) return true; }
    return false;
  }
  function all(){
    var out=[];
    PANES.forEach(function(p){
      var el=document.getElementById(p[0]);
      if(el&&el.contentWindow&&!isSwap(el)) out.push({pane:p[1],el:el,win:el.contentWindow});
    });
    return out;
  }
  function active(){
    var list=all();
    for(var i=0;i<list.length;i++) if(list[i].pane===ACTIVE) return list[i];
    return list[0]||null;
  }
  function of(src){
    if(!src) return 0;
    var list=all();
    for(var i=0;i<list.length;i++) if(list[i].win===src) return list[i].pane;
    return 0;
  }
  function post(win,msg){ try{ win.postMessage(msg,'*'); return true; }catch(_){ return false; } }
  function send(msg,opts){
    var to=(opts&&opts.to)||'all', n=0;
    var targets=to==='active'?[active()].filter(Boolean):all();
    targets.forEach(function(f){ if(post(f.win,msg)) n++; });
    // the preview frame takes the theme and nothing else
    if(msg&&msg.uad==='theme'&&to==='all'){
      var pv=document.getElementById('pv');
      if(pv&&pv.contentWindow&&post(pv.contentWindow,msg)) n++;
    }
    return n;
  }
  /* a message every pane keeps, now and after a reload or swap (side, zoom) */
  function keep(key,msg){ KEPT[key]=msg; return send(msg,{to:'all'}); }
  /* What a newly loaded or swapped-in frame must be told so it shows what the
     one before it showed: the theme, the "unanswered" and "imported" marking
     when switched off, the problem outlines, the kept side / zoom messages and
     the shell's keys.  CATALOG: marks were not replayed after a swap. */
  function replay(win){
    if(!win) return;
    post(win,{uad:'theme',theme:document.documentElement.dataset.theme});
    var g=document.getElementById('rf-gaps');
    if(g&&!g.checked) post(win,{uad:'gaps',on:false});
    var im=document.getElementById('rf-imported');
    if(im&&!im.checked) post(win,{uad:'imported',on:false});
    var mk=typeof window.marksMsg==='function'?window.marksMsg():null;
    if(mk) post(win,mk);
    Object.keys(KEPT).forEach(function(k){ post(win,KEPT[k]); });
    pushKeys(win);
    emit('frame-replay',{pane:of(win)});
  }
  var frames={all:all,active:active,of:of,send:send,keep:keep,replay:replay,
    kept:function(){ return Object.assign({},KEPT); },
    setActive:function(p){ ACTIVE=p; emit('pane',{pane:p}); },
    activePane:function(){ var a=active(); return a?a.pane:0; }};

  /* -------------------------------------------------------- message router
     Every message from a pane is re-emitted on the bus, tagged with the pane:
     'frame' with {pane, msg}, and 'frame:<uad>'. */
  window.addEventListener('message',function(e){
    var m=e.data; if(!m||typeof m!=='object'||!m.uad) return;
    var pane=of(e.source); if(!pane) return;
    if(m.uad==='focus'&&pane!==ACTIVE) frames.setActive(pane);
    if(m.uad==='ready'||m.uad==='frame-ready') pushKeys(e.source);
    if(m.uad==='key'&&ON&&typeof m.combo==='string'&&!modalOpen()) dispatch(m.combo,{pane:pane});
    if(m.uad==='ws-esc'&&!document.body.classList.contains('ws-open')) escape.late();
    var d={pane:pane,msg:m,source:e.source};
    emit('frame',d); emit('frame:'+m.uad,d);
  });

  /* the docks own narrow widths once docks.js claims them (S2): until then
     the classic Sign-off tab stays the way to it below 1240 px */
  var NARROW_OWNED=false;
  function ownsNarrow(){ return ON&&NARROW_OWNED; }
  function claimNarrow(v){ NARROW_OWNED=v!==false; }

  window.UADShell={
    version:VERSION,
    enabled:enabled, on:on, emit:emit,
    state:state, commands:commands, panels:panels,
    keys:keys, escape:escape, frames:frames,
    ownsNarrow:ownsNarrow, claimNarrow:claimNarrow
  };
})();
