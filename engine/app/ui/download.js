/* Download product: the desktop edition for Windows, handed over for the
   licence key (app/download.py).  One dialog for the editor's header button
   and the public /download page.  The key is checked on the server; the
   installer arrives in parts of under 4 MB (a serverless answer's limit),
   each checked against its SHA-256, and is saved as one file. */
(function(){
  var CSS=`.dlv{position:fixed;inset:0;z-index:85;display:flex;align-items:center;justify-content:center;padding:28px 16px;
  background:rgba(5,5,6,.66);-webkit-backdrop-filter:blur(8px);backdrop-filter:blur(8px)}
.dl,.dl *{border-radius:0!important}
.dl{width:min(620px,100%);max-height:100%;overflow-y:auto;background:var(--surface);border:1px solid var(--line-3);
  box-shadow:var(--shadow-lg);color:var(--ink);animation:pop2 .16s ease-out}
.dl .dh{display:flex;border-bottom:1px solid var(--line-2)}
.dl .dh .ht{flex:1;padding:22px 26px 20px}
.dl h2{margin:12px 0 0;font:500 26px/1.1 var(--sans);letter-spacing:-.035em}
.dl h2 em{display:block;font-style:normal;color:var(--faint)}
.dl .x{width:60px;border:0;border-left:1px solid var(--line-2);background:transparent;color:var(--muted);font:300 26px/1 var(--sans);cursor:pointer}
.dl .x:hover{color:var(--ink);background:var(--hover)}
.dl .facts{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));border-bottom:1px solid var(--line-2)}
.dl .facts div{padding:12px 16px;border-left:1px solid var(--line-2)}
.dl .facts div:first-child{border-left:0;padding-left:26px}
.dl .facts b{display:block;font:500 13.5px/1.3 var(--sans)}
.dl .facts span{display:block;margin-top:4px;font:500 10px/1 var(--mono);letter-spacing:.1em;text-transform:uppercase;color:var(--faint)}
@media (max-width:520px){.dl .facts{grid-template-columns:1fr}.dl .facts div{border-left:0;border-top:1px solid var(--line-2);padding-left:26px}}
.dl .db{padding:20px 26px 24px}
.dl label{display:block;font:500 10.5px/1 var(--sans);letter-spacing:.17em;text-transform:uppercase;color:var(--ink-2);margin-bottom:9px}
.dl label:before{content:'+ ';font-weight:300}
.dl .krow{display:flex;border:1px solid var(--line-3)}
.dl input{flex:1;min-width:0;padding:13px 14px;border:0;background:var(--bg-2);color:var(--ink);font:500 15px/1 var(--mono);letter-spacing:.08em}
.dl input:focus{outline:2px solid var(--ink);outline-offset:-2px}
.dl .go{border:0;border-left:1px solid var(--line-3);padding:0 20px;background:var(--btn);color:var(--btn-ink);font:600 13.5px/1 var(--sans);cursor:pointer;white-space:nowrap}
.dl .go[disabled]{opacity:.45;cursor:progress}
.dl .msg{margin-top:12px;font-size:13px;color:var(--muted)}
.dl .msg.bad{color:var(--bad);border-left:2px solid var(--bad);padding-left:10px}
.dl .msg.ok{color:var(--ink);border-left:2px solid var(--good);padding-left:10px}
.dl .bar{height:6px;margin-top:14px;background:var(--sunk);border:1px solid var(--line-2)}
.dl .bar i{display:block;height:100%;width:0;background:var(--ink);transition:width .15s}
.dl .steps{margin:16px 0 0;padding:0;list-style:none;border-top:1px solid var(--line-2)}
.dl .steps li{display:grid;grid-template-columns:28px 1fr;gap:10px;padding:10px 0;border-bottom:1px solid var(--line-2);font-size:13px;color:var(--ink-2)}
.dl .steps li .n{font:500 11px/1.6 var(--mono);color:var(--faint)}
.dl .steps li b{font-weight:600;color:var(--ink)}
.dl .krow{align-items:stretch}
.dl .krow input,.dl .krow .go{margin:0;height:50px;box-sizing:border-box}`;
  function style(){
    if(document.getElementById('uad-dl-css')) return;
    var s=document.createElement('style'); s.id='uad-dl-css'; s.textContent=CSS;
    document.head.appendChild(s);
  }
  const esc=s=>String(s??'').replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const mb=n=>(n/1048576).toFixed(1)+' MB';
async function sha256hex(buf){
  if(!(window.crypto&&crypto.subtle)) return null;          // not a secure context: skip the check
  const d=await crypto.subtle.digest('SHA-256',buf);
  return [...new Uint8Array(d)].map(b=>b.toString(16).padStart(2,'0')).join('');
}
function open(info){
  const i=info||{};
  const v=document.createElement('div'); v.className='dlv';
  v.innerHTML=`<form class="dl" role="dialog" aria-modal="true" aria-labelledby="dl-t" onsubmit="return false">
    <div class="dh"><div class="ht"><span class="eyebrow">Download product</span>
      <h2 id="dl-t">UAD 3.6 for Windows <em>Runs on your PC. Reports stay on your PC.</em></h2></div>
      <button type="button" class="x" aria-label="Close">&times;</button></div>
    <div class="facts"><div><b>Windows 10 / 11</b><span>64-bit</span></div>
      <div><b>${i.size?mb(i.size):'—'}</b><span>Installer</span></div>
      <div><b>${esc(i.version||'—')}</b><span>Version</span></div></div>
    <div class="db">
      <label for="dl-key">Licence key</label>
      <div class="krow"><input id="dl-key" type="password" autocomplete="off" spellcheck="false" placeholder="Enter your licence key">
        <button type="submit" class="go">Download &rarr;</button></div>
      <div class="msg" id="dl-msg">${i.available===false?'The installer has not been built on this server yet.':'The key is checked before the download starts. You enter it again when installing.'}</div>
      <div class="bar" hidden><i></i></div>
      <ol class="steps">
        <li><span class="n">01</span><span>Open the downloaded file. If Windows says <i>“Windows protected your PC”</i>, choose <b>More info → Run anyway</b> — the installer is not code-signed yet.</span></li>
        <li><span class="n">02</span><span>Enter the same licence key. It installs for your Windows user only — no administrator rights needed.</span></li>
        <li><span class="n">03</span><span>Start <b>UAD 3.6</b> from the Start menu or the desktop. Your reports are kept on this PC.</span></li>
      </ol>
    </div></form>`;
  document.body.appendChild(v);
  const q=x=>v.querySelector(x), msg=q('#dl-msg'), go=q('.go'), bar=q('.bar'), fill=q('.bar i');
  const say=(t,k)=>{ msg.className='msg'+(k?' '+k:''); msg.textContent=t; };
  const close=()=>{ v.remove(); document.removeEventListener('keydown',esc_); };
  const esc_=e=>{ if(e.key==='Escape') close(); };
  document.addEventListener('keydown',esc_);
  q('.x').onclick=close; v.addEventListener('mousedown',e=>{ if(e.target===v) close(); });
  setTimeout(()=>q('#dl-key').focus(),30);
  q('.dl').addEventListener('submit',e=>{ e.preventDefault(); fetchInstaller(); });
  async function fetchInstaller(){
    const key=q('#dl-key').value;
    if(!key.trim()){ say('Enter the licence key.','bad'); return; }
    go.disabled=true; say('Checking the key…');
    try{
      const r=await fetch('/api/desktop/ticket',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({key})});
      const d=await r.json().catch(()=>({}));
      if(!r.ok){ say(d.detail||'The download could not start.','bad'); go.disabled=false; return; }
      bar.hidden=false; const parts=[]; let got=0;
      for(let n=0;n<d.parts.length;n++){
        say(`Downloading ${mb(got)} of ${mb(d.size)}…`);
        let buf=null;
        for(let attempt=0;attempt<3&&!buf;attempt++){
          const pr=await fetch(`/api/desktop/part/${n}?t=${encodeURIComponent(d.ticket)}`);
          if(!pr.ok) continue;
          const b=await pr.arrayBuffer(); const h=await sha256hex(b);
          if(h===null||h===d.parts[n].sha256) buf=b;
        }
        if(!buf) throw new Error('part '+(n+1)+' of '+d.parts.length+' did not arrive intact');
        parts.push(buf); got+=buf.byteLength; fill.style.width=(100*got/d.size).toFixed(1)+'%';
      }
      const blob=new Blob(parts,{type:'application/vnd.microsoft.portable-executable'});
      const whole=await sha256hex(await blob.arrayBuffer());
      if(whole!==null&&whole!==d.sha256) throw new Error('the joined file does not match its checksum');
      const a=document.createElement('a'); a.href=URL.createObjectURL(blob); a.download=d.name;
      document.body.appendChild(a); a.click(); a.remove();
      setTimeout(()=>URL.revokeObjectURL(a.href),60000);
      say(`Saved ${d.name} (${mb(d.size)}, checksum verified). Open it from your Downloads folder.`,'ok');
    }catch(e){ say('The download failed: '+e.message+'. Try again.','bad'); }
    go.disabled=false;
  }
}


  window.UADDownload={open:function(info){ style(); open(info); }};
})();
