/* Physical A5 pages and duplex A4 booklet imposition; also testable in Node. */
(function (root) {
  const escape = v => String(v ?? '').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
  function ordered(samples) {
    const compare=new Intl.Collator('ru',{numeric:true}).compare;
    return [...samples].sort((a,b)=>compare(a.site,b.site)||compare(a.profile,b.profile)||compare(a.point,b.point)||a.id-b.id);
  }
  function impose(count) {
    if(!Number.isInteger(count)||count<4||count%4)throw new Error('Число страниц тетради должно быть кратно 4');
    const sides=[];
    for(let sheet=0;sheet<count/4;sheet++) {
      sides.push([count-1-2*sheet,2*sheet]);
      sides.push([2*sheet+1,count-2-2*sheet]);
    }
    return sides;
  }
  function build(samples, options) {
    if(!samples.length||samples.length>100)throw new Error('Выберите от 1 до 100 проб для одной книжки');
    const perPage=Number(options.perPage);
    if(![1,2].includes(perPage))throw new Error('Выберите 1 или 2 пробы на странице');
    if(!['a5','booklet'].includes(options.mode))throw new Error('Неизвестный формат');
    const base=new URL(options.base);
    if(!['http:','https:'].includes(base.protocol)||base.username||base.password||base.search||base.hash)throw new Error('Проверьте адрес QR');
    const list=ordered(samples),groups=[];
    for(const s of list) {
      const last=groups[groups.length-1];
      if(!last||last.site!==s.site||last.profile!==s.profile)groups.push({site:s.site,profile:s.profile,samples:[s]});
      else last.samples.push(s);
    }
    const pageBodies=[];
    pageBodies.push(`<div class="cover"><div class="book-brand">GEOTRACE / ПОЛЕВАЯ ДОКУМЕНТАЦИЯ</div><h1>Геохимическая<br>полевая книжка</h1><p class="cover-sub">Отбор проб · Маршруты · Наблюдения</p><div class="cover-data"><p>Участок: ${escape([...new Set(list.map(s=>s.site))].join('; '))}</p><p>Профилей: ${groups.length} · Проб: ${list.length}</p><p>Составлена: ${escape(options.date||'')}</p></div><div class="write-line">Исполнитель / группа</div><div class="write-line">Период работ</div><div class="write-line">Номер книжки</div><p class="cover-help">QR-коды открывают карточки проб. Записи на бумаге внесите в электронный реестр после маршрута. Ссылка требует доступного сервера; бумажная книжка работает без связи.</p></div>`);
    for(const group of groups)for(let start=0;start<group.samples.length;start+=perPage) {
      const cards=group.samples.slice(start,start+perPage).map(s=>{
        const target=base.href.replace(/\/$/,'');
        const img=`/api/qr?id=${s.id}&base=${encodeURIComponent(target)}`;
        return `<article class="sample-card" data-sample="${s.id}"><div class="sample-top"><div><h2>${escape(s.code)}</h2><p>Точка: ${escape(s.point)} · ${escape(s.material)}</p><p>Исполнитель: ${escape(s.collector||'________________')}</p><p>WGS84: ${s.latitude==null?'________________________':escape(s.latitude+', '+s.longitude)}</p></div><img src="${escape(img)}" alt="QR ${escape(s.code)}"></div><div class="write-line">Дата / время отбора</div><div class="write-line">Глубина / горизонт / масса</div><div class="write-line">Фактические координаты / точность GPS</div><div class="write-line">Описание, условия отбора, замечания</div><div class="write-line"></div>${perPage===1?'<div class="extra-lines">'+Array(9).fill('<div class="write-line"></div>').join('')+'</div>':''}</article>`;
      }).join('');
      pageBodies.push(`<div class="book-header"><strong>${escape(group.site)}</strong><span>${escape(group.profile)}</span></div><div class="cards cards-${perPage}">${cards}</div>`);
    }
    const notes=`<div class="book-header"><strong>Для заметок</strong><span>GeoTrace</span></div><div class="notes-lines">${Array(21).fill('<div class="write-line"></div>').join('')}</div>`;
    pageBodies.push(notes);
    const contentPages=pageBodies.length;
    while(pageBodies.length%4)pageBodies.push(notes);
    const pages=pageBodies.map((body,i)=>`<section class="book-page" data-page="${i+1}">${body}<div class="book-footer"><span>GeoTrace · Тетрадь ${Math.floor(i/16)+1}</span><span>${i+1} / ${pageBodies.length}</span></div></section>`);
    const signatures=[];
    for(let start=0;start<pages.length;start+=16)signatures.push(pages.slice(start,start+16));
    let markup;
    if(options.mode==='booklet')markup=signatures.map((signature,si)=>impose(signature.length).map((pair,i)=>`<div class="sheet-side" data-signature="${si+1}" data-side="${i+1}" data-pages="${pair.map(n=>si*16+n+1).join(',')}">${pair.map(n=>signature[n]).join('')}</div>`).join('')).join('');
    else markup=pages.join('');
    return {contentPages,pages:pages.length,signatures:signatures.length,sides:options.mode==='booklet'?pages.length/2:pages.length,
      html:`<!doctype html><html lang="ru"><head><meta charset="utf-8"><title>GeoTrace — полевая книжка</title><link rel="stylesheet" href="/booklet.css"><style>@page{size:${options.mode==='booklet'?'A4 landscape':'A5'};margin:0}</style></head><body class="${options.mode}">${markup}</body></html>`};
  }
  const api={ordered,impose,build};
  if(typeof module==='object'&&module.exports)module.exports=api;
  else root.GeoBooklet=api;
})(typeof globalThis!=='undefined'?globalThis:this);
