/* -------------------------------------------- comparables, in row format */
async function drawComps(w){
  w.innerHTML='<div class="panel empty">Loading the grid…</div>';
  const kind=S.compKind||'sales';
  const r=await api(`/cases/${S.caseId}/comparables?kind=${kind}`);
  if(!r.ok){w.innerHTML='<div class="panel empty">Could not load the grid.</div>';return;}
  const g=r.data;
  const p=document.createElement('div'); p.className='panel';
  const bar=document.createElement('div'); bar.className='compbar';
  bar.innerHTML=`<span class="k">${esc(g.title)}</span>
    <span style="font:400 11px var(--mono);color:var(--muted)">
    ${g.comparables.length} comparable(s) · ${g.rows.length} rows from the B-1 supplement ·
    drag a column head to reorder · drag a divider to resize</span>`;
  const kinds=document.createElement('div'); kinds.className='kinds';
  for(const [k,label] of [['sales','Sales'],['rental','Rental'],['grm','GRM']]){
    const b=document.createElement('button'); b.className='tab'; b.textContent=label;
    b.style.borderBottom='1px solid var(--rule)';
    b.setAttribute('aria-selected',String(kind===k));
    b.onclick=()=>{S.compKind=k;drawComps(w);};
    kinds.appendChild(b);
  }
  const add=document.createElement('button'); add.className='addbtn';
  add.textContent='+ Add comparable';
  add.onclick=async()=>{
    const res=await api(`/cases/${S.caseId}/comparables`,
      {method:'POST',body:JSON.stringify({kind})});
    toast(res.ok?'Comparable added':'Could not add'); drawComps(w);};
  bar.appendChild(kinds);
  bar.appendChild(document.createElement('span')).style.flex='1';
  bar.appendChild(add);
  p.appendChild(bar);

  const wrap=document.createElement('div'); wrap.className='gridwrap';
  const n=g.comparables.length;
  const W=(S.compWidths=S.compWidths||{});
  const wid=(key,fallback)=>W[kind+'|'+key]||fallback;

  let head=`<colgroup><col style="width:${wid('row',210)}px">`
          +`<col style="width:${wid('subject',150)}px">`;
  for(let i=0;i<n;i++) head+=`<col style="width:${wid('c'+i,150)}px"><col style="width:${wid('a'+i,78)}px">`;
  head+='</colgroup><thead><tr>';
  head+=`<th data-col="row">Row<span class="grip"></span></th>`;
  head+=`<th data-col="subject">Subject<span class="grip"></span></th>`;
  for(const c of g.comparables){
    head+=`<th class="comp" colspan="2" draggable="true" data-index="${c.index}" data-col="c${c.index-1}">
      <div class="compcell">
        <label class="ph" title="Photo of comparable ${c.index}">
          ${c.photo?`<img src="${esc(c.photo)}" alt="">`:'<span>+ photo</span>'}
          <input type="file" accept="image/*" hidden>
        </label>
        <div class="meta">
          <div>Comparable #${c.index}</div>
          <div class="addr">${esc(c.address||'—')}</div>
          <div class="tools">
            <button data-act="remove" title="Remove this comparable">Remove</button>
          </div>
        </div>
      </div><span class="grip"></span></th>`;
  }
  head+='</tr></thead>';

  let body='';
  for(const row of g.rows){
    if(row.heading){
      body+=`<tr class="head"><td class="lbl">${esc(row.label)}</td><td colspan="${1+2*n}"></td></tr>`;
      continue;}
    const opts=row.options||[];
    body+=`<tr><td class="lbl">${esc(row.label)}</td>`;
    body+=`<td>${cell(row.subject_fid,row.subject,1,opts)}</td>`;
    for(let i=0;i<n;i++){
      const c=row.cells[i]||{};
      body+=`<td>${cell(row.comp_fid,c.value||'',i+1,opts)}</td>`;
      body+=`<td class="adj">${row.adjustable?cell(row.adjust_fid,c.adjustment||'',i+1):''}</td>`;
    }
    body+='</tr>';
  }
  wrap.innerHTML=`<table class="comps">${head}<tbody>${body}</tbody></table>`;
  p.appendChild(wrap);
  w.innerHTML=''; w.appendChild(p);
  wireGrid(wrap,g,kind,w);
  if(kind==='sales') p.appendChild(transferBlock());
  p.appendChild(saveBar(S.sections.find(x=>x.number===22)||S.sections[0]));
}

function cell(fid,value,ordinal,options){
  if(!fid) return `<span style="color:var(--muted)">—</span>`;
  if(options&&options.length&&options.length<=60){
    const opts=['<option value=""></option>'].concat(options.map(o=>
      `<option value="${esc(o.value)}"${o.label===value||o.value===value?' selected':''}>${esc(o.label)}</option>`));
    return `<select data-fid="${esc(fid)}" data-ord="${ordinal}" onchange="saveCell(this)">${opts.join('')}</select>`;
  }
  return `<input value="${esc(value)}" data-fid="${esc(fid)}" data-ord="${ordinal}"
    onchange="saveCell(this)">`;
}

/* Column resizing, comparable reordering, removal and photos. */
function wireGrid(wrap,g,kind,w){
  const table=wrap.querySelector('table');
  const cols=[...table.querySelectorAll('col')];
  const key=name=>kind+'|'+name;

  table.querySelectorAll('th .grip').forEach(grip=>{
    grip.addEventListener('mousedown',e=>{
      e.preventDefault(); e.stopPropagation();
      const th=grip.closest('th');
      const start=e.clientX;
      const index=[...th.parentNode.children].indexOf(th);
      const colIndex=th.classList.contains('comp')? 2+2*([...table.querySelectorAll('th.comp')].indexOf(th)) : index;
      const col=cols[colIndex];
      const startW=parseFloat(col.style.width)||th.getBoundingClientRect().width;
      const move=ev=>{
        const next=Math.max(46,startW+(ev.clientX-start));
        col.style.width=next+'px';
        S.compWidths[key(th.dataset.col)]=next;
      };
      const up=()=>{document.removeEventListener('mousemove',move);
        document.removeEventListener('mouseup',up);};
      document.addEventListener('mousemove',move);
      document.addEventListener('mouseup',up);
    });
  });

  let dragged=null;
  table.querySelectorAll('th.comp').forEach(th=>{
    th.addEventListener('dragstart',e=>{dragged=th;th.classList.add('drag');
      e.dataTransfer.effectAllowed='move';e.dataTransfer.setData('text/plain',th.dataset.index);});
    th.addEventListener('dragend',()=>{th.classList.remove('drag');
      table.querySelectorAll('th.comp').forEach(x=>x.classList.remove('over'));});
    th.addEventListener('dragover',e=>{e.preventDefault();th.classList.add('over');});
    th.addEventListener('dragleave',()=>th.classList.remove('over'));
    th.addEventListener('drop',async e=>{
      e.preventDefault(); th.classList.remove('over');
      if(!dragged||dragged===th) return;
      const from=Number(dragged.dataset.index), to=Number(th.dataset.index);
      const order=g.comparables.map(c=>c.index);
      order.splice(order.indexOf(from),1);
      order.splice(order.indexOf(to)+(to>from?1:0),0,from);
      const res=await api(`/cases/${S.caseId}/comparables/order`,
        {method:'POST',body:JSON.stringify({kind,order})});
      toast(res.ok?`Comparable ${from} is now #${order.indexOf(from)+1}`:'Could not reorder');
      drawComps(w);
    });
    const remove=th.querySelector('[data-act=remove]');
    if(remove) remove.onclick=async()=>{
      if(!confirm(`Remove comparable #${th.dataset.index}? The ones after it move up.`))return;
      const res=await api(`/cases/${S.caseId}/comparables/${th.dataset.index}?kind=${kind}`,
        {method:'DELETE'});
      toast(res.ok?'Comparable removed':'Could not remove'); drawComps(w);
    };
    const file=th.querySelector('input[type=file]');
    if(file) file.onchange=async()=>{
      if(!file.files.length)return;
      const fd=new FormData(); fd.append('file',file.files[0]);
      const q=`?category=comparable&comparable=${th.dataset.index}&section=22`
             +`&caption=${encodeURIComponent('Comparable #'+th.dataset.index)}`;
      const res=await fetch(`/api/cases/${S.caseId}/media${q}`,{method:'POST',body:fd});
      toast(res.ok?'Photo added':'Could not add the photo'); drawComps(w);
    };
  });
}

/* Prior sale and transfer history reads the same comparables, so it is edited
   here, under the grid, rather than in a section of its own. */
function transferBlock(){
  const box=document.createElement('div');
  const s=S.sections.find(x=>x.number===21);
  if(!s) return box;
  box.innerHTML='<div class="bar k" style="margin-top:20px">Prior sale and transfer history — subject and comparables</div>'
    +'<p style="font-size:11.5px;color:var(--muted);margin:7px 0 4px">'
    +'Whether or not a property transferred, this is where its history is recorded; '
    +'it prints in the report’s own Prior Sale and Transfer History section.</p>';
  let sub=null;
  for(const f of s.fields){
    if(f.subsection&&f.subsection!==sub){sub=f.subsection;
      const b=document.createElement('div');b.className='groupbar';
      b.innerHTML=`<span class="k">${esc(sub)}</span>`;
      const add=document.createElement('button');add.className='addbtn';add.textContent='+ Add row';
      add.onclick=()=>addRow(f); b.appendChild(add); box.appendChild(b);}
    box.appendChild(fieldRow(f));
  }
  return box;
}
