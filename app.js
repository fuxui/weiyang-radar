'use strict';
const $ = id => document.getElementById(id);
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const safeURL = value => {try {const u=new URL(value);return ['http:','https:'].includes(u.protocol)?esc(u.href):'';}catch{return '';}};
const categories=['前沿科技','商业与创业','股市与公司','加密货币','经济与政策','认知与社会','生活记录','其他'];
const focusCategories=['前沿科技','商业与创业','股市与公司','加密货币'];
const statusNames={pending:'待核实',verified:'人工已核实',disputed:'有争议',rejected:'不采用',draft:'待审核',review:'需要重新审核',approved:'人工审核通过'};
const fields=['customer','pain','payment_evidence','competition','risk','experiment','claim','support','counter','falsifier','notes'];
let data={news:[],research:[],drafts:[],markets:[],sources:[],audit:[],ai:{}}, selected='', draftId='', visible=40;
let researchDirty=false, draftDirty=false;
let focusedNews=new Set();
function notice(message,error=false){$('message').textContent=message;$('message').classList.toggle('error',error);}
async function api(path,body,format='json'){
  let response;
  try{response=await fetch(path,body===undefined?{}:{method:'POST',headers:{'Content-Type':'application/json','X-Radar-Client':'local'},body:JSON.stringify(body)});}
  catch{$('connection').textContent='本地服务未连接';throw Error('无法连接本地服务。请保持启动窗口运行，确认地址和端口后刷新重试；已保存资料仍在本机。');}
  if(!response.ok){const error=await response.json().catch(()=>({}));throw Error(error.error||'本地服务请求失败，请重试或查看启动窗口。');}
  if(format==='text')return response.text();
  try{return await response.json();}catch{throw Error('本地服务响应格式不正确，请查看启动窗口后重试。');}
}
function action(fn){return async event=>{const button=event?.currentTarget;if(button?.tagName==='BUTTON')button.disabled=true;try{await fn(event);}catch(error){notice(error.message,true);}finally{if(button?.tagName==='BUTTON')button.disabled=false;}};}
function selectedNews(){const n=data.news.find(n=>n.id===selected);if(!n)throw Error('请先在新闻页选择一条素材');return n;}
function tab(name){document.querySelectorAll('.tab').forEach(el=>el.hidden=el.id!=='tab-'+name);document.querySelectorAll('nav button').forEach(el=>el.classList.toggle('active',el.dataset.tab===name));}
function showAllNews(ids){focusedNews=new Set(ids);['status-filter','category-filter','language-filter','date-filter'].forEach(id=>$(id).value='all');$('search').value='';visible=40;tab('news');renderNews();}
document.querySelectorAll('nav button').forEach(el=>el.addEventListener('click',()=>tab(el.dataset.tab)));
$('new-category').innerHTML=categories.map(c=>`<option>${esc(c)}</option>`).join('');
$('scores').innerHTML=['需求','变化','可行性','低成本','兴趣'].map((name,i)=>`<label>${name}<input id="score-${i}" type="number" min="0" max="5" value="0"></label>`).join('');
function formatDate(value){if(!value)return '日期未知';const date=new Date(value);return Number.isNaN(+date)?value:date.toLocaleString('zh-CN',{timeZone:'Asia/Shanghai'})+' 北京时间';}
function badge(status){return `<span class="tag ${['disputed','rejected'].includes(status)?'bad':status==='pending'?'warn':''}">${esc(statusNames[status]||status)}</span>`;}
async function load(){data=await api('/api/state');$('connection').textContent='本地已连接 · '+data.news.length+' 条素材';$('ai-status').textContent=data.ai.mode;$('ai').disabled=!data.ai.enabled;renderLists();}
function renderLists(){
  const tested=data.sources.filter(s=>s.last),failed=tested.filter(s=>!s.last.ok).length;
  $('source-summary').textContent='新闻源 '+data.sources.length+' 个 · 中文 '+data.sources.filter(s=>s.language==='zh').length+' 个 · '+(tested.length?'最近记录中成功 '+(tested.length-failed)+' 个'+(failed?'，失败 '+failed+' 个':''):'尚未采集')+'（展开查看）';
  $('sources').innerHTML=data.sources.map(s=>`<div class="source"><b>${esc(s.name)}</b><small>${s.language==='zh'?'中文':'英文'} · ${esc(s.type)}</small><small>${!s.last?'尚未测试':s.last.ok?'读到 '+s.last.items+' 条 · 新增 '+s.last.added+' 条 · 已有 '+(s.last.duplicates??Math.max(0,s.last.items-s.last.added))+' 条':'本源采集失败'}</small>${s.last?.today_items!==undefined?`<small>${esc(s.last.today)} 当天 ${s.last.today_items} 条${s.last.unknown_dates?' · 日期未知 '+s.last.unknown_dates+' 条':''}</small>`:''}<small>${s.last?esc(formatDate(s.last.checked_at)):''}</small>${s.last?.attempts>1?'<small>已自动重试 1 次</small>':''}${s.last?.error?`<small>${esc(s.last.error_summary||'请展开查看失败原因')}</small><details><summary>具体原因</summary><small>${esc(s.last.error)}</small></details>`:''}</div>`).join('');
  const old=$('category-filter').value;const cats=[...new Set([...categories,...data.news.map(n=>n.category)])];$('category-filter').innerHTML='<option value="focus">科技 · 商业 · 币圈</option><option value="all">全部领域</option>'+cats.map(c=>`<option>${esc(c)}</option>`).join('');$('category-filter').value=['all','focus',...cats].includes(old)?old:'focus';
  renderNews();renderOpportunities();renderMarkets();
  $('audit').innerHTML=data.audit.map(a=>`<details class="card"><summary>${esc(a.event)} · ${esc(formatDate(a.at))}</summary><pre>${esc(a.data)}</pre></details>`).join('')||'<div class="empty">尚无操作记录</div>';
  renderDraftOptions();
}
function renderNews(){const query=$('search').value.toLowerCase().trim(),filter=$('status-filter').value,cat=$('category-filter').value,date=$('date-filter').value,language=$('language-filter').value;const shown=data.news.filter(n=>(filter==='all'||n.status===filter)&&(cat==='all'||(cat==='focus'?focusCategories.includes(n.category):n.category===cat))&&(language==='all'||n.language===language)&&(date!=='today'||n.date_status==='today')&&[n.title,n.summary,n.source].join(' ').toLowerCase().includes(query));
  if(date==='all')shown.sort((a,b)=>Number(['today','history'].includes(b.date_status))-Number(['today','history'].includes(a.date_status))||b.published_at.localeCompare(a.published_at));
  if(focusedNews.size)shown.sort((a,b)=>Number(focusedNews.has(b.id))-Number(focusedNews.has(a.id)));
  const todayCount=shown.filter(n=>n.date_status==='today').length;
  $('news-count').textContent=data.today+'（北京时间） · 符合筛选 '+shown.length+' 条，其中今天 '+todayCount+' 条 · 当前显示 '+Math.min(visible,shown.length)+' 条。'+(focusedNews.size?'本次导入或新增素材优先显示，原文日期不变；改变筛选后恢复日期顺序。':date==='priority'?'当天排前，历史资料随后；日期未知或异常的排在最后。':'');
  $('news-list').innerHTML=shown.slice(0,visible).map(n=>`<article class="card ${n.id===selected?'selected':''}"><div class="meta">${badge(n.status)}${n.date_status==='today'?'<span class="tag">今天</span>':n.date_status==='unknown'?'<span class="tag warn">日期待核对</span>':n.date_status==='future'?'<span class="tag warn">来源时间晚于当前</span>':''}${esc(n.category)} · ${esc(n.source)} · ${esc(n.source_type)}</div><h3>${esc(n.title)}</h3><p>${esc(n.summary).slice(0,500)}</p><p class="meta">原文：${esc(n.published_at?formatDate(n.published_at):n.published||'日期未知')}<br>收录：${esc(formatDate(n.saved_at))}</p><button class="secondary select-news" data-id="${esc(n.id)}">${n.id===selected?'正在研究':'选择并研究'}</button> ${safeURL(n.link)?`<a href="${safeURL(n.link)}" target="_blank" rel="noopener noreferrer">原始来源 ↗</a>`:''}</article>`).join('')||'<div class="empty">暂无符合筛选的素材。请联网采集，或切换日期、语言与领域查看历史资料。</div>';
  $('more').hidden=shown.length<=visible;
  document.querySelectorAll('.select-news').forEach(el=>el.onclick=action(()=>selectNews(el.dataset.id)));
}
async function selectNews(id){if((researchDirty||draftDirty)&&!confirm('当前编辑尚未保存，切换素材会放弃这些编辑。继续？'))return;selected=id;draftId='';researchDirty=false;draftDirty=false;const n=selectedNews();$('selected-title').textContent=n.title;$('selected-meta').textContent=n.source+' · '+statusNames[n.status];$('selected-link').hidden=!safeURL(n.link);if(safeURL(n.link))$('selected-link').href=n.link;$('verify-status').value=n.status;$('verify-evidence').value=n.evidence;$('verify-note').value=n.verify_note;document.querySelectorAll('.selection-label').forEach(el=>el.textContent='研究素材：'+n.title);
  const r=data.research.find(r=>r.news_id===id)||{};fields.forEach(k=>$('r-'+k).value=r[k]||'');$('r-budget').value=r.budget||0;$('r-confidence').value=r.confidence??50;[0,1,2,3,4].forEach(i=>$('score-'+i).value=r.scores?.[i]||0);$('claim-state').textContent=r.claim?'已保存判断，置信度 '+r.confidence+'% · '+(r.counter&&r.falsifier?'已有反例与否证条件':'还需补充反例或否证条件'):'尚未建立观点检验';clearDraft();renderNews();renderDraftOptions();notice('已选择：'+n.title);
}
function researchValue(){const n=selectedNews();return {news_id:n.id,...Object.fromEntries(fields.map(k=>[k,$('r-'+k).value])),scores:[0,1,2,3,4].map(i=>Number($('score-'+i).value)),budget:Number($('r-budget').value),confidence:Number($('r-confidence').value)};}
async function saveResearch(){const result=await api('/api/research',researchValue());researchDirty=false;await load();notice('研究已保存 · '+result.score+'/100 · '+result.stage);return result;}
document.querySelectorAll('.save-research').forEach(el=>el.onclick=action(saveResearch));
document.querySelectorAll('[id^="r-"],[id^="score-"]').forEach(el=>el.addEventListener('input',()=>researchDirty=true));
function renderOpportunities(){const filter=$('opportunity-filter').value;const rows=[...data.research].sort((a,b)=>b.score-a.score).filter(r=>filter==='all'||(filter==='ready')===(r.stage==='可做小实验'));
  $('opportunity-list').innerHTML=rows.map(r=>`<article class="card"><span class="tag">${r.score}/100 · ${esc(r.stage)}</span><h3>${esc(data.news.find(n=>n.id===r.news_id)?.title)}</h3><p>客户：${esc(r.customer||'待补充')}<br>预算：${r.budget} 元<br>实验：${esc(r.experiment||'待补充')}</p><button class="secondary select-opportunity" data-id="${esc(r.news_id)}">查看研究</button></article>`).join('')||'<div class="empty">保存一份研究，机会候选就会出现在这里。</div>';
  document.querySelectorAll('.select-opportunity').forEach(el=>el.onclick=action(()=>selectNews(el.dataset.id)));
}
function renderMarkets(){$('market-list').innerHTML=data.markets.slice(0,100).map(m=>`<article class="card"><div class="meta">${esc(m.kind)} · ${m.stale?'<span class="tag warn">旧快照</span>':'<span class="tag">近期快照 / 非实时保证</span>'}</div><h3>${esc(m.symbol)} <span>${esc(m.price)} ${esc(m.currency)}</span></h3><p>观察：${esc(formatDate(m.observed_at))}<br>时间口径：${esc(m.time_basis)}<br>记录：${esc(formatDate(m.fetched_at))}</p><p>${esc(m.note)}</p><a href="${safeURL(m.source)}" target="_blank" rel="noopener noreferrer">数据来源 ↗</a></article>`).join('')||'<div class="empty">还没有市场观察。可记录股票快照，或尝试获取 BTC / ETH。无数据时不会显示模拟价格。</div>';}
function clearDraft(){draftId='';['body','counter','risk','market_time'].forEach(k=>$('d-'+k).value='');$('human').checked=false;draftDirty=false;renderReview(null);}
function renderDraftOptions(){const old=draftId;$('draft-select').innerHTML='<option value="">新草稿</option>'+data.drafts.filter(d=>d.news_id===selected).map(d=>`<option value="${esc(d.id)}">${esc(statusNames[d.status])} · 修订 ${d.revision} · ${esc(d.body.slice(0,26))}</option>`).join('');$('draft-select').value=old;if(old)renderReview(data.drafts.find(d=>d.id===old));}
function renderReview(d){$('draft-status').textContent=d?statusNames[d.status]+' · 修订 '+d.revision:'尚未保存';$('draft-review').innerHTML=d?`<p class="meta">${esc(d.mode)} · 近似 X 长度 ${d.review.weight}/280</p>${d.review.problems.length?'<ul>'+d.review.problems.map(x=>'<li>'+esc(x)+'</li>').join('')+'</ul>':'<p>规则初审未发现阻断项，仍需人工审核。</p>'}<p class="muted">${esc(d.review.note)}</p>`:'<p>保存草稿后查看初审结果。</p>';}
function openDraft(id){const d=data.drafts.find(d=>d.id===id);if(!d)return clearDraft();draftId=id;['body','counter','risk','market_time'].forEach(k=>$('d-'+k).value=d[k]);$('human').checked=false;draftDirty=false;renderDraftOptions();renderReview(d);}
function draftValue(){const n=selectedNews();return {id:draftId,news_id:n.id,...Object.fromEntries(['body','counter','risk','market_time'].map(k=>[k,$('d-'+k).value]))};}
async function saveDraft(){const d=await api('/api/draft',draftValue());draftId=d.id;draftDirty=false;$('human').checked=false;await load();notice('草稿已保存，规则初审已更新。');return d;}
async function copy(value){try{await navigator.clipboard.writeText(value);notice('已复制');}catch{$('prompt-output').hidden=false;$('prompt-output').textContent=value;notice('当前浏览器无法自动复制，文字已显示，请手动复制。');}}
['search','status-filter','category-filter','date-filter','language-filter'].forEach(id=>$(id).addEventListener('input',()=>{focusedNews=new Set();visible=40;renderNews();}));
$('more').onclick=()=>{visible+=40;renderNews();};$('opportunity-filter').onchange=renderOpportunities;
$('refresh').onclick=action(async()=>{notice('正在采集中文科技、商业、币圈与补充来源；临时网络失败会自动重试 1 次…');const result=await api('/api/refresh',{});await load();const ok=result.sources.filter(s=>s.ok),items=ok.reduce((sum,s)=>sum+s.items,0),added=ok.reduce((sum,s)=>sum+s.added,0),duplicates=ok.reduce((sum,s)=>sum+(s.duplicates??s.items-s.added),0),today=ok.reduce((sum,s)=>sum+(s.today_items||0),0);notice('联网采集完成：'+ok.length+'/'+result.sources.length+' 个源成功；读到 '+items+' 条，其中今天 '+today+' 条；新增 '+added+' 条，已有 '+duplicates+' 条。'+(ok.length<result.sources.length?'请展开新闻源查看失败原因。':'')+(added===0&&items>0?'本轮新闻均已入库，没有重复添加。':items===0?'本轮未读到新闻，请查看源卡片。':''));});
$('news-form').onsubmit=action(async e=>{e.preventDefault();const result=await api('/api/news',{title:$('new-title').value,link:$('new-link').value,category:$('new-category').value,published:$('new-published').value,summary:$('new-summary').value});await load();showAllNews([result.id]);await selectNews(result.id);$('news-form').reset();});
$('verify-form').onsubmit=action(async e=>{e.preventDefault();const n=selectedNews();await api('/api/verify',{id:n.id,status:$('verify-status').value,evidence:$('verify-evidence').value,note:$('verify-note').value});await load();$('selected-meta').textContent=selectedNews().source+' · '+statusNames[selectedNews().status];notice('核实记录已保存；关联已审核稿需重新审核。');});
$('market-form').onsubmit=action(async e=>{e.preventDefault();await api('/api/market',{...Object.fromEntries(['symbol','kind','currency','observed_at','source','note'].map(k=>[k,$('m-'+k).value])),price:Number($('m-price').value)});await load();notice('市场观察已保存，保留原始时间与来源。');});
document.querySelectorAll('.crypto').forEach(el=>el.onclick=action(async()=>{notice('正在请求 '+el.dataset.symbol+' 快照…');await api('/api/crypto',{symbol:el.dataset.symbol});await load();notice('快照已保存；接口时间口径见记录。');}));
$('draft-select').onchange=()=>{if(draftDirty&&!confirm('放弃尚未保存的草稿编辑？')){$('draft-select').value=draftId;return;}openDraft($('draft-select').value);};
document.querySelectorAll('[id^="d-"]').forEach(el=>el.addEventListener('input',()=>{draftDirty=true;$('human').checked=false;$('draft-status').textContent='有未保存修改 · 请保存后重新审核';}));
$('save-draft').onclick=action(saveDraft);
$('template').onclick=action(async()=>{selectedNews();if(draftDirty&&!confirm('用新模板替换未保存编辑？'))return;if(researchDirty)await saveResearch();const result=await api('/api/template',{news_id:selected});await load();openDraft(result.id);notice('规则模板已保存。请填完整并运行初审。');});
$('prompt').onclick=action(async()=>{selectedNews();if(researchDirty)await saveResearch();const result=await api('/api/prompt',{news_id:selected});await copy(result.prompt);});
$('ai').onclick=action(async()=>{selectedNews();if(draftDirty&&!confirm('模型将创建新草稿，当前未保存编辑会丢弃。继续？'))return;if(!confirm('将当前素材与已保存的研究笔记发送到 '+data.ai.destination+'\n模型：'+data.ai.model+'。云服务可能计费。继续？'))return;if(researchDirty)await saveResearch();notice('正在请求模型…');const result=await api('/api/ai',{news_id:selected,consent:true});await load();openDraft(result.id);notice('模型草稿已保存，尚未核实或审核。');});
$('approve').onclick=action(async()=>{if(!draftId)throw Error('请先保存草稿');if(draftDirty)throw Error('有未保存修改，请先保存并重新审核');await api('/api/approve',{id:draftId,human:$('human').checked});await load();notice('当前版本已记录人工审核通过，可复制。');});
$('copy-approved').onclick=action(async()=>{if(draftDirty)throw Error('有未保存修改，请先保存并重新审核');await load();const d=data.drafts.find(d=>d.id===draftId);if(!d||d.status!=='approved'||!d.review.ready)throw Error('当前版本尚未审核通过');await copy(d.body);});
$('export-draft').onclick=action(async()=>{
  if(!draftId)throw Error('请先保存或选择一份草稿');
  if(draftDirty)throw Error('有未保存修改，请先保存后再导出');
  const value=await api('/api/draft/export?id='+encodeURIComponent(draftId),undefined,'text');
  const url=URL.createObjectURL(new Blob([value],{type:'text/markdown;charset=utf-8'}));
  const link=document.createElement('a');link.href=url;link.download='weiyang-draft.md';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);
  notice('已导出当前保存草稿，文件含审核状态与来源记录；不会自动发布。');
});
$('legacy-import').onchange=action(async event=>{const file=event.target.files[0];if(!file)return;try{
  if(file.size>1900000)throw Error('文件过大，最多约1.9MB');
  let items;try{items=JSON.parse(await file.text());}catch{throw Error('文件不是有效的 JSON，请选择 V1 导出的新闻/研究库数组。');}
  const result=await api('/api/import-v1',{items});
  if(result.processed===0){notice('文件中没有素材，研究库未改动。');return;}
  await load();showAllNews(result.ids);
  notice('已处理 '+result.processed+' 条：新增 '+result.added+' 条，已有 '+result.duplicates+' 条；补入 '+result.research_added+' 份研究。已切换全部筛选，重复项不会覆盖现有资料；旧核实标记不沿用。');
}finally{event.target.value='';}});
window.addEventListener('beforeunload',event=>{if(researchDirty||draftDirty){event.preventDefault();event.returnValue='';}});
action(async()=>{await load();notice('研究库就绪。先采集新闻，或手动添加一条观察。');})();
