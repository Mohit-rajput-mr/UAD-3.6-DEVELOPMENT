/* The report toolbar in one row (DR phase 2, step S1 / T-272, first part;
   _work/dr/PHASE2_SHELL_PLAN.md).

   At a laptop's width the report bar ran to three rows above the page
   (owner 2026-10-11: "too tight", "report looks too small").  Under the shell
   it keeps one row: the toggles and the tools used while filling (Comment
   library, Worksheets, Sketch) stay; the rest -- Fill the report, Report
   setup, Generate map, the market imports, Reload -- and the colour key go
   under "More".  Nothing is copied: each entry clicks the original button,
   so its own handler (and its disabled state) is the one truth, and the
   palette (Ctrl+K) reaches every one of them too. */
(function(){
  if(!window.UADShell||!UADShell.enabled()) return;
  var MORE=['rf-auto','rf-setup','rf-maps','rf-market','rf-msearch','rf-reload'];
  function esc(s){ return String(s==null?'':s).replace(/[&<>"']/g,function(c){ return {'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]; }); }
  function build(){
    var bar=document.querySelector('.rf-bar');
    if(!bar||bar.querySelector('.rf-more')) return;
    bar.classList.add('rf-one');
    MORE.forEach(function(id){ var b=document.getElementById(id); if(b) b.classList.add('rf-sec'); });
    var more=document.createElement('button');
    more.type='button'; more.className='addbtn rf-more'; more.setAttribute('aria-haspopup','menu');
    more.innerHTML='More &#9662;'; more.title='Report setup, map, market data, reload and the colour key';
    var sk=document.getElementById('rf-sketch');
    bar.insertBefore(more,sk?sk.nextSibling:null);
  }
  function close(){ var m=document.getElementById('rf-moremenu'); if(m) m.remove(); }
  function open(btn){
    close();
    var m=document.createElement('div'); m.id='rf-moremenu'; m.className='rf-moremenu'; m.setAttribute('role','menu');
    var rows=MORE.map(function(id){
      var b=document.getElementById(id); if(!b) return '';
      return '<button type="button" role="menuitem" data-for="'+id+'"'+(b.disabled?' disabled':'')+'>'+esc(b.textContent.trim())
        +(b.title?'<small>'+esc(b.title)+'</small>':'')+'</button>';
    }).join('');
    var key=document.querySelector('.rf-bar .rf-key');
    m.innerHTML=rows+(key?'<div class="rf-mk"><span>What each colour takes</span>'+key.innerHTML+'</div>':'');
    document.body.appendChild(m);
    var r=btn.getBoundingClientRect();
    m.style.top=(r.bottom+4)+'px';
    m.style.left=Math.max(8,Math.min(window.innerWidth-m.offsetWidth-8,r.left))+'px';
    m.querySelector('button[role=menuitem]:not([disabled])')&&m.querySelector('button[role=menuitem]:not([disabled])').focus();
  }
  document.addEventListener('click',function(e){
    var more=e.target.closest&&e.target.closest('.rf-more');
    if(more){ e.preventDefault(); if(document.getElementById('rf-moremenu')) close(); else open(more); return; }
    var item=e.target.closest&&e.target.closest('#rf-moremenu [data-for]');
    if(item){ var b=document.getElementById(item.dataset.for); close(); if(b&&!b.disabled) b.click(); return; }
    if(!(e.target.closest&&e.target.closest('#rf-moremenu'))) close();
  });
  document.addEventListener('keydown',function(e){ if(e.key==='Escape'&&document.getElementById('rf-moremenu')){ e.preventDefault(); close(); } },true);
  UADShell.on('form-drawn',build);
  UADShell.on('case-open',close);
  if(document.querySelector('.rf-bar')) build();
})();
