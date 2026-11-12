const $ = s => document.querySelector(s);
const statuses = ['Запланирована','Отобрана','Передана в лабораторию','В анализе','Результаты готовы'];
const esc = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let samples = [], current = null, toastTimer, filteredSamples = [], pageIndex = 0, batchKey;
function toast(message) { $('#toast').textContent=message;$('#toast').hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>$('#toast').hidden=true,5000); }
async function api(path, data) {
  const res=await fetch(path,data===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(data)});
  const body=await res.json();if(!res.ok) throw new Error(body.error || 'Ошибка сервера');return body;
}
function action(fn) { return async e => {try {await fn(e);}catch(err){toast(err.message || 'Не удалось связаться с сервером');}}; }
function badge(n){ return `<span class="status s${n}">${statuses[n]}</span>`; }
function base(){ const u=new URL($('#baseUrl').value.trim());if(!['http:','https:'].includes(u.protocol)||u.username||u.password||u.search||u.hash)throw new Error('Укажите адрес вида http://192.168.1.10:8000');return u.href.replace(/\/$/,''); }
function qr(id){return `/api/qr?id=${id}&base=${encodeURIComponent(base())}`;}
function baseHint(){try{const host=new URL(base()).hostname;$('#baseHint').textContent=['localhost','127.0.0.1','[::1]'].includes(host)?'Этот адрес работает только на компьютере. Для телефона укажите IP компьютера.':'Проверьте этот адрес в браузере телефона перед печатью.';localStorage.setItem('geotrace-base',base());}catch{$('#baseHint').textContent='Введите полный адрес приложения: http://IP:8000';}}
function render(){
  const counts=[samples.length,samples.filter(s=>s.status===0).length,samples.filter(s=>s.status>=2&&s.status<=3).length,samples.filter(s=>s.status===4).length];
  $('#stats').innerHTML=['Всего проб','Ожидают отбора','В лаборатории','Результаты готовы'].map((title,i)=>`<div class="stat"><span>${title}</span><i>${['▦','⌖','⚗','✓'][i]}</i><b>${counts[i].toString().padStart(2,'0')}</b></div>`).join('');
  const search=$('#search').value.toLowerCase();const filter=$('#statusFilter').value;
  const batch=$('#batchFilter').value;
  filteredSamples=samples.filter(s=>(filter===''||s.status===Number(filter))&&(!batch||s.batch_id===Number(batch))&&[s.code,s.site,s.profile,s.point].join(' ').toLowerCase().includes(search));
  const pages=Math.max(1,Math.ceil(filteredSamples.length/100));pageIndex=Math.min(pageIndex,pages-1);
  const visible=filteredSamples.slice(pageIndex*100,(pageIndex+1)*100);
  $('#pageInfo').textContent=`Страница ${pageIndex+1} из ${pages} · Найдено: ${filteredSamples.length}`;
  $('#prevPage').disabled=pageIndex===0;$('#nextPage').disabled=pageIndex>=pages-1;
  $('#count').textContent=samples.length;$('#demo').hidden=!!samples.length;
  $('#rows').innerHTML=visible.map(s=>`<tr><td><a href="/?sample=${s.id}" data-open="${s.id}"><strong>${esc(s.code)}</strong></a><small>Точка ${esc(s.point)}</small></td><td>${esc(s.site)}<small>${esc(s.profile)}</small></td><td>${esc(s.material)}</td><td>${badge(s.status)}</td><td><button class="row-open" data-open="${s.id}" aria-label="Открыть ${esc(s.code)}">→</button></td></tr>`).join('');
  $('#empty').hidden=visible.length>0;$('#empty').textContent=samples.length?'По вашему запросу ничего не найдено.':'Проб пока нет. Добавьте первую или загрузите учебный набор.';
}
async function refresh(){
  const data=await Promise.all([api('/api/samples'),api('/api/batches')]);samples=data[0];
  const selected=$('#batchFilter').value;
  $('#batchFilter').innerHTML='<option value="">Все серии и одиночные пробы</option>'+data[1].map(b=>`<option value="${b.id}">Серия №${b.id} · ${b.count} проб · ${esc(b.spec.site)}</option>`).join('');
  $('#batchFilter').value=selected;render();
}
function date(v){return new Date(v).toLocaleString('ru-RU');}
async function openSample(id){
  const s=await api(`/api/samples/${id}`);current=s;
  const fields=[['Участок',s.site],['Профиль / точка',`${s.profile} / ${s.point}`],['Материал',s.material],['Исполнитель',s.collector||'Не указан'],['Координаты WGS84',s.latitude===null?'Не указаны':`${s.latitude}, ${s.longitude}`],['Создана',date(s.created_at)]];
  $('#detail').innerHTML=`<div class="dialog-head"><div><div class="eyebrow">ПАСПОРТ ПРОБЫ</div><h2>${esc(s.code)}</h2></div><button class="icon close" aria-label="Закрыть">×</button></div><div class="sample-hero"><img src="${esc(qr(s.id))}" alt="QR-код ${esc(s.code)}"><div>${badge(s.status)}<p>Постоянная ссылка на карточку.<br>Сканируйте камерой телефона.</p><button class="secondary" id="printOne">Печать этикетки</button></div></div><div class="timeline">${statuses.map((name,i)=>`<div class="step ${i<=s.status?'done':''}">${name}</div>`).join('')}</div><dl class="detail-grid">${fields.map(([k,v])=>`<div><dt>${k}</dt><dd>${esc(v)}</dd></div>`).join('')}</dl>${s.notes?`<p class="muted">${esc(s.notes)}</p>`:''}<h2 style="margin-top:24px">Результаты анализа</h2>${s.results.length?`<div class="table-wrap"><table class="results"><thead><tr><th>Элемент</th><th>Значение</th><th>Единицы</th><th>Метод</th></tr></thead><tbody>${s.results.map(r=>`<tr><td>${esc(r.element)}</td><td>${r.qualifier==='<'?'&lt; ':''}${esc(r.value)}</td><td>${esc(r.unit)}</td><td>${esc(r.method)}</td></tr>`).join('')}</tbody></table></div>`:`<p class="muted">Результаты ещё не внесены. Отсутствие результата не означает нулевую концентрацию.</p>`}
  ${s.status===3?`<form id="resultForm" class="result-form"><b>Добавить результат</b><div class="form-grid"><label>Элемент / показатель<input name="element" placeholder="Cu" required maxlength="30"></label><label>Концентрация<input name="value" type="number" min="0" step="any" required placeholder="42.5"></label><label>Единицы<select name="unit"><option>мг/кг</option><option>г/т</option><option>%</option><option>мг/л</option></select></label><label>Значение<select name="qualifier"><option value="=">Измеренное</option><option value="<">Ниже предела обнаружения</option></select></label><label class="wide">Метод анализа<input name="method" placeholder="Например, ICP-MS" required maxlength="100"></label></div><div class="actions"><button class="primary">Сохранить результат</button></div></form>`:''}
  <details style="margin-top:24px"><summary>История движения пробы (${s.events.length})</summary><ul class="history">${s.events.map(e=>`<li>${esc(date(e.at))} · ${statuses[e.status]}</li>`).join('')}</ul></details><div class="actions">${s.status<4?`<button id="advance" class="primary">${['Отметить отбор','Передать в лабораторию','Начать анализ','Завершить анализ'][s.status]} →</button>`:`<span class="muted">✓ Анализ завершён, результаты сохранены</span>`}</div>`;
  if(!$('#detailDialog').open)$('#detailDialog').showModal();
  history.replaceState(null,'',`/?sample=${s.id}`);
  $('#printOne').onclick=action(()=>printLabels([s]));
  if($('#advance'))$('#advance').onclick=action(async()=>{await api(`/api/samples/${s.id}/status`,{status:s.status+1});await refresh();await openSample(s.id);toast('Статус обновлён');});
  if($('#resultForm'))$('#resultForm').onsubmit=action(async e=>{e.preventDefault();await api(`/api/samples/${s.id}/results`,Object.fromEntries(new FormData(e.target)));await openSample(s.id);toast('Результат сохранён');});
}
async function printLabels(list){
  if(!list.length){toast('Сначала добавьте пробы');return;}
  const area=$('#printArea');area.innerHTML=list.map(s=>`<article class="print-label"><img src="${esc(qr(s.id))}" alt="QR"><div><b>${esc(s.code)}</b><p>${esc(s.site)}</p><small>${esc(s.profile)} · ${esc(s.point)}</small><small>${esc(s.material)}</small><small>GeoTrace · учебная проба</small></div></article>`).join('');
  await Promise.all([...area.querySelectorAll('img')].map(img=>img.decode()));
  const opened=[...document.querySelectorAll('dialog[open]')];const url=location.href;opened.forEach(d=>d.close());window.print();opened.forEach(d=>d.showModal());history.replaceState(null,'',url);
}
$('#statusFilter').insertAdjacentHTML('beforeend',statuses.map((s,i)=>`<option value="${i}">${s}</option>`).join(''));
$('#search').oninput=()=>{pageIndex=0;render();};$('#statusFilter').onchange=$('#batchFilter').onchange=()=>{pageIndex=0;render();};
$('#prevPage').onclick=()=>{pageIndex--;render();$('.panel .table-wrap').scrollTop=0;};$('#nextPage').onclick=()=>{pageIndex++;render();$('.panel .table-wrap').scrollTop=0;};
$('#baseUrl').value=localStorage.getItem('geotrace-base')||location.origin;baseHint();$('#baseUrl').onchange=baseHint;
$('#newSample').onclick=()=>{$('#createForm').reset();$('#createDialog').showModal();};
$('#createForm').onsubmit=action(async e=>{e.preventDefault();const button=e.target.querySelector('[type="submit"]');button.disabled=true;try{const s=await api('/api/samples',Object.fromEntries(new FormData(e.target)));$('#createDialog').close();await refresh();await openSample(s.id);toast('Проба создана. Номер назначен автоматически.');}finally{button.disabled=false;}});
$('#demo').onclick=action(async()=>{await api('/api/demo',{});await refresh();toast('Добавлено 8 вымышленных учебных проб');});
$('#labels').onclick=()=>{
  if(!filteredSamples.length){toast('В выборке нет проб');return;}
  $('#labelCount').textContent=`В выборке: ${filteredSamples.length} проб.`;
  $('#labelStart').max=filteredSamples.length;$('#labelStart').value=1;$('#labelLimit').value=Math.min(100,filteredSamples.length);
  $('#labelsDialog').showModal();
};
$('#labelsForm').onsubmit=action(async e=>{
  e.preventDefault();const start=Number($('#labelStart').value),limit=Number($('#labelLimit').value);
  if(!Number.isInteger(start)||start<1||start>filteredSamples.length||!Number.isInteger(limit)||limit<1||limit>100)throw new Error('Проверьте диапазон печати');
  await printLabels([...filteredSamples].sort((a,b)=>a.id-b.id).slice(start-1,start-1+limit));
});
$('#downloadBatch').onclick=action(async()=>{
  const id=$('#batchFilter').value;if(!id)throw new Error('Выберите серию в фильтре реестра перед скачиванием');
  const button=$('#downloadBatch');button.disabled=true;const original=button.textContent;button.textContent='Готовим архив…';
  try{
    const res=await fetch(`/api/batches/${id}/qr.zip?base=${encodeURIComponent(base())}`);
    if(!res.ok){const data=await res.json();throw new Error(data.error||'Ошибка скачивания');}
    const blob=await res.blob();const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download=`GeoTrace-batch-${id}.zip`;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),60000);toast('Архив готов');
  }finally{button.disabled=false;button.textContent=original;}
});
function batchPreview(){
  const f=$('#batchForm'),n=Number(f.elements.profiles.value)*Number(f.elements.per_profile.value);
  $('#batchPreview').textContent=Number.isInteger(n)&&n>0&&n<=10000?`Будет создано ${n.toLocaleString('ru-RU')} проб. Номера проб назначит база; номера точек начинаются заново в каждом профиле.`:'Укажите параметры: всего от 1 до 10 000 проб.';
}
$('#batchForm').oninput=batchPreview;
$('#newBatch').onclick=()=>{
  $('#batchForm').reset();batchKey=Array.from(crypto.getRandomValues(new Uint8Array(16)),b=>b.toString(16).padStart(2,'0')).join('');batchPreview();$('#batchDialog').showModal();
};
$('#batchForm').onsubmit=action(async e=>{
  e.preventDefault();const button=e.target.querySelector('[type="submit"]');button.disabled=true;button.textContent='Создаём серию…';
  try{
    const result=await api('/api/batches',{...Object.fromEntries(new FormData(e.target)),request_key:batchKey});
    $('#batchDialog').close();await refresh();$('#batchFilter').value=String(result.id);$('#search').value='';$('#statusFilter').value='';pageIndex=0;render();
    toast(`Создана серия №${result.id}: ${result.count} проб (${result.first_code} — ${result.last_code})`);
  }finally{button.disabled=false;button.textContent='Создать серию';}
});
$('#registry').onclick=()=>{if($('#detailDialog').open)$('#detailDialog').close();history.replaceState(null,'','/');};
document.addEventListener('click',action(async e=>{const close=e.target.closest('.close');if(close){close.closest('dialog').close();return;}const open=e.target.closest('[data-open]');if(open){e.preventDefault();await openSample(open.dataset.open);}}));
$('#detailDialog').addEventListener('close',()=>{if(!$('#detailDialog').open)history.replaceState(null,'','/');});
(async()=>{try{await refresh();const id=new URLSearchParams(location.search).get('sample');if(id)await openSample(id);}catch(e){toast(e.message);}})();
$('#fieldbook').onclick=()=>{
  if(!filteredSamples.length){toast('В выборке нет проб');return;}
  $('#bookCount').textContent=`В выборке ${filteredSamples.length} проб. Позиции в книжке отсчитываются по профилям и точкам.`;
  $('#bookStart').max=filteredSamples.length;$('#bookStart').value=1;$('#bookLimit').value=Math.min(100,filteredSamples.length);
  $('#bookPreview').hidden=true;$('#printBook').disabled=true;$('#bookSummary').textContent='';$('#bookDialog').showModal();
};
$('#bookForm').oninput=()=>{$('#printBook').disabled=true;$('#bookSummary').textContent='Сформируйте предпросмотр с новыми параметрами.';};
$('#bookForm').onsubmit=action(async e=>{
  e.preventDefault();const start=Number($('#bookStart').value),count=Number($('#bookLimit').value);
  if(!Number.isInteger(start)||start<1||start>filteredSamples.length||!Number.isInteger(count)||count<1||count>100)throw new Error('Проверьте диапазон книжки: от 1 до 100 проб');
  const button=e.target.querySelector('[type="submit"]');button.disabled=true;$('#printBook').disabled=true;$('#bookSummary').textContent='Готовим страницы и QR-коды…';
  try{
    const list=GeoBooklet.ordered(filteredSamples).slice(start-1,start-1+count);
    const mode=$('#bookMode').value;
    const result=GeoBooklet.build(list,{perPage:$('#bookPerPage').value,mode,base:base(),date:new Date().toLocaleDateString('ru-RU')});
    const frame=$('#bookPreview');
    await new Promise((resolve,reject)=>{frame.onload=resolve;frame.onerror=()=>reject(new Error('Не удалось загрузить предпросмотр'));frame.srcdoc=result.html;});
    await Promise.all([...frame.contentDocument.images].map(img=>img.decode()));
    await frame.contentDocument.fonts.ready;
    frame.hidden=false;
    $('#bookSummary').textContent=`Проб: ${list.length} · Страниц A5: ${result.pages} (включая обложку и заметки)${mode==='booklet'?` · Тетрадей: ${result.signatures} · Листов A4: ${result.pages/4}`:''}. Перед печатью проверьте читаемость QR и адрес сервера.`;
    $('#printBook').disabled=false;
  }finally{button.disabled=false;}
});
$('#printBook').onclick=action(()=>{
  if($('#printBook').disabled)return;
  $('#bookPreview').contentWindow.focus();$('#bookPreview').contentWindow.print();
});
