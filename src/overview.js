// Início: a read-only, chart-first picture of the selected month and the portfolio.
const OV_COLORS=['#3ddc97','#5aa9ff','#f5b94a','#a98bff','#ff6b7a','#2dd4bf','#f78fb3','#c6d36b','#8592a4'];
const OV_CLASS_COLORS={'Renda fixa':'#3ddc97','Ações':'#5aa9ff','Fundos imobiliários':'#f5b94a','ETFs':'#a98bff','Criptomoedas':'#f78fb3','Outros':'#2dd4bf','Caixa':'#8592a4'};
const ovEl=id=>document.getElementById(id);
const ovToday=()=>{const d=new Date();return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}-${String(d.getDate()).padStart(2,'0')}`};
const ovShort=v=>{const a=Math.abs(v),s=v<0?'-':'';if(a>=1e6)return s+'R$ '+(a/1e6).toLocaleString('pt-BR',{maximumFractionDigits:1})+' mi';if(a>=1e4)return s+'R$ '+(a/1e3).toLocaleString('pt-BR',{maximumFractionDigits:1})+' mil';return s+'R$ '+Math.round(a).toLocaleString('pt-BR')};
const ovPct=(v,d=0)=>(v).toLocaleString('pt-BR',{maximumFractionDigits:d,minimumFractionDigits:d})+'%';
const ovMonthName=key=>{const [y,m]=key.split('-').map(Number);const label=new Date(y,m-1,1).toLocaleDateString('pt-BR',{month:'long',year:'numeric'});return label.charAt(0).toUpperCase()+label.slice(1)};
const ovMonthShort=key=>{const [y,m]=key.split('-').map(Number);return new Date(y,m-1,1).toLocaleDateString('pt-BR',{month:'short'}).replace('.','')};
const ovDaysIn=key=>{const [y,m]=key.split('-').map(Number);return new Date(y,m,0).getDate()};
const ovShiftMonth=(key,delta)=>{const [y,m]=key.split('-').map(Number);const d=new Date(y,m-1+delta,1);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`};
const ovIsCash=e=>e.payment!=='Voucher';

function ovMonthIncome(key){
  const declared=+(incomeByMonth[key]||0);
  const entries=INCOME_ENTRIES.filter(x=>x.date.startsWith(key)).reduce((s,x)=>s+x.amount,0);
  return Math.max(declared,entries);
}
function ovMonthNumbers(key){
  const rows=DATA.filter(e=>e.date.startsWith(key)&&ovIsCash(e)),today=ovToday();
  const total=rows.reduce((s,e)=>s+e.amount,0);
  const due=rows.filter(e=>(e.finance?.debt_entry||e.finance?.fixed_expense_id||e.finance?.scheduled_date)&&!e.finance?.paid&&e.date>=today.slice(0,10));
  const dueTotal=due.reduce((s,e)=>s+e.amount,0);
  const basis=typeof trustInsights!=='undefined'&&trustInsights?.month===key?trustInsights:null;
  if(basis){
    const income=+basis.expected_income||+basis.income?.expected||0,projected=+basis.projected_expenses||total;
    const paid=Math.max(0,+basis.actual_expenses||0),pending=Math.max(0,projected-paid);
    return {income,confirmed:+basis.confirmed_income||0,out:projected,paid,pending,balance:income-projected,voucher:+basis.voucher_income||0,voucherSpent:+basis.voucher_expenses||0,dueCount:due.length,rows};
  }
  const income=ovMonthIncome(key);
  return {income,confirmed:income,out:total,paid:total-dueTotal,pending:dueTotal,balance:income-total,voucher:+(voucherByMonth[key]||0),voucherSpent:DATA.filter(e=>e.date.startsWith(key)&&!ovIsCash(e)).reduce((s,e)=>s+e.amount,0),dueCount:due.length,rows};
}

function ovDonut(segments,center,sub){
  const total=segments.reduce((s,x)=>s+x.value,0),r=42,c=2*Math.PI*r;let offset=0;
  const arcs=total>0?segments.map(seg=>{const len=seg.value/total*c,gap=segments.length>1?1.2:0;const out=`<circle r="${r}" cx="50" cy="50" fill="none" stroke="${seg.color}" stroke-width="12" stroke-dasharray="${Math.max(0,len-gap)} ${c}" stroke-dashoffset="${-offset}" transform="rotate(-90 50 50)"><title>${esc(seg.label)}: ${brl(seg.value)}</title></circle>`;offset+=len;return out}).join(''):'';
  return `<svg viewBox="0 0 100 100" role="img" aria-label="${esc(sub)}"><circle r="${r}" cx="50" cy="50" fill="none" stroke="var(--surface-3)" stroke-width="12"/>${arcs}</svg><div class="ov-donut-center"><strong>${center}</strong><span>${esc(sub)}</span></div>`;
}
function ovLegend(segments,total){
  return segments.map(seg=>`<li><i style="background:${seg.color}"></i><span>${esc(seg.label)}</span><b>${brl(seg.value)}</b><em>${total?ovPct(seg.value/total*100):'—'}</em></li>`).join('');
}

function ovCumulative(key,lastDay){
  const days=ovDaysIn(key),byDay=new Array(days+1).fill(0);
  DATA.forEach(e=>{if(e.date.startsWith(key)&&ovIsCash(e)){const d=+e.date.slice(8,10);if(d<=lastDay)byDay[d]+=e.amount}});
  const cum=[0];for(let d=1;d<=days;d++)cum[d]=cum[d-1]+byDay[d];return cum;
}
function ovPaceChart(key,numbers){
  const days=ovDaysIn(key),today=ovToday(),isCurrent=today.startsWith(key),isFuture=key>today.slice(0,7);
  const lastDay=isCurrent?+today.slice(8,10):isFuture?0:days;
  const cum=ovCumulative(key,lastDay),prevKey=ovShiftMonth(key,-1),prevDays=ovDaysIn(prevKey),prev=ovCumulative(prevKey,prevDays);
  const hasPrev=prev[prevDays]>0;
  const limits=typeof savedBudgetGroups==='function'?Object.values(savedBudgetGroups(key)).reduce((s,v)=>s+v,0):0;
  const target=limits||numbers.income||0,spent=cum[lastDay]||0;
  const W=560,H=250,P={l:6,r:6,t:22,b:28},max=Math.max(target,spent,prev[prevDays],numbers.out,1)*1.06;
  const x=d=>P.l+(d/days)*(W-P.l-P.r),y=v=>H-P.b-(v/max)*(H-P.t-P.b);
  const line=(series,last,scale)=>{let p='';for(let d=0;d<=last;d++)p+=(d?'L':'M')+x(d*scale).toFixed(1)+' '+y(series[d]).toFixed(1);return p};
  const path=line(cum,lastDay,1),area=lastDay>0?path+`L${x(lastDay).toFixed(1)} ${y(0)} L${x(0)} ${y(0)}Z`:'';
  const prevPath=hasPrev?`<path d="${line(prev,prevDays,days/prevDays)}" class="ov-prev"/>`:'';
  const goal=target?`<line x1="${P.l}" x2="${W-P.r}" y1="${y(target)}" y2="${y(target)}" class="ov-goal"/><text x="${P.l+2}" y="${y(target)-7}" class="ov-axis ov-goal-label">${limits?'Limite':'Renda'} ${ovShort(target)}</text>`:'';
  const over=target&&spent>target;
  const dot=lastDay>0?`<circle cx="${x(lastDay)}" cy="${y(spent)}" r="5" class="ov-dot"/><text x="${x(lastDay)+(lastDay>days*.75?-10:10)}" y="${y(spent)-10}" text-anchor="${lastDay>days*.75?'end':'start'}" class="ov-dot-label">${ovShort(spent)}</text>`:'';
  const ticks=`<text x="${x(1)}" y="${H-8}" class="ov-axis">dia 1</text><text x="${x(Math.round(days/2))}" y="${H-8}" text-anchor="middle" class="ov-axis">dia ${Math.round(days/2)}</text><text x="${x(days)}" y="${H-8}" text-anchor="end" class="ov-axis">dia ${days}</text>`;
  const color=over?'#ff6b7a':'#3ddc97';
  ovEl('ovPace').innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Gasto acumulado no mês comparado ao mês anterior"><defs><linearGradient id="ovPaceFill" x1="0" x2="0" y1="0" y2="1"><stop offset="0" stop-color="${color}" stop-opacity=".3"/><stop offset="1" stop-color="${color}" stop-opacity="0"/></linearGradient></defs><line x1="${P.l}" x2="${W-P.r}" y1="${y(0)}" y2="${y(0)}" class="ov-base"/>${goal}${prevPath}<path d="${area}" fill="url(#ovPaceFill)"/><path d="${path}" class="ov-line ${over?'is-over':''}"/>${dot}${ticks}</svg><div class="ov-chart-keys"><span><i class="k-now"></i>Este mês</span>${hasPrev?'<span><i class="k-prev"></i>Mês anterior</span>':''}${target?`<span><i class="k-goal"></i>${limits?'Limite total':'Renda'}</span>`:''}</div>`;
  const note=ovEl('ovPaceNote');
  if(lastDay===0){note.textContent='Mês futuro';note.className='ov-pill';return}
  if(hasPrev){const sameDay=prev[Math.min(prevDays,Math.round(lastDay*prevDays/days))],diff=sameDay-spent;
    note.textContent=Math.abs(diff)<1?'igual ao mês anterior':diff>0?`${ovShort(diff)} a menos que mês anterior`:`${ovShort(-diff)} a mais que mês anterior`;note.className='ov-pill '+(diff>=0?'is-good':'is-bad');return}
  if(target){const diff=target-spent;note.textContent=diff>=0?`${ovShort(diff)} até o ${limits?'limite':'fim da renda'}`:`${ovShort(-diff)} acima do ${limits?'limite':'que entrou'}`;note.className='ov-pill '+(diff>=0?'is-good':'is-bad');return}
  note.textContent=ovShort(spent);note.className='ov-pill';
}

function ovLimits(key){
  const box=ovEl('ovLimits');
  if(typeof BUDGET_GROUPS==='undefined'){box.innerHTML='';return}
  const limits=savedBudgetGroups(key),used=categoryTotals(key);
  box.innerHTML=BUDGET_GROUPS.map((g,i)=>{const lim=limits[g.id]||0,u=used[g.id]||0,ratio=lim?u/lim:0,level=!lim?'unset':ratio>1?'over':ratio>=.8?'warn':'ok';
    return `<div class="ov-limit is-${level}"><div class="ov-limit-top"><span>${esc(g.label)}</span><small>${ovShort(u)}${lim?' de '+ovShort(lim):''}</small><b>${lim?ovPct(Math.min(ratio*100,999)):'sem limite'}</b></div><div class="ov-track"><i style="width:${lim?Math.min(100,ratio*100):0}%"></i></div></div>`}).join('');
}

function ovCategories(numbers){
  const sums={};numbers.rows.forEach(e=>sums[e.category]=(sums[e.category]||0)+e.amount);
  let list=Object.entries(sums).sort((a,b)=>b[1]-a[1]).map(([label,value])=>({label,value}));
  if(list.length>6){const rest=list.slice(5).reduce((s,x)=>s+x.value,0);list=[...list.slice(0,5),{label:'Demais',value:rest}]}
  list.forEach((seg,i)=>seg.color=OV_COLORS[i%OV_COLORS.length]);
  const total=list.reduce((s,x)=>s+x.value,0);
  ovEl('ovCatTotal').textContent=brl(total);
  ovEl('ovCatDonut').innerHTML=ovDonut(list,total?ovShort(total):'R$ 0','gastos no mês');
  ovEl('ovCatLegend').innerHTML=list.length?ovLegend(list,total):'<li class="ov-empty">Nenhum gasto neste mês.</li>';
}

function ovHistoryChart(key){
  const keys=[...Array(6)].map((_,i)=>ovShiftMonth(key,i-5));
  const data=keys.map(k=>({k,inc:ovMonthIncome(k),out:DATA.filter(e=>e.date.startsWith(k)&&ovIsCash(e)).reduce((s,e)=>s+e.amount,0)}));
  const W=560,H=210,P={l:8,r:8,t:24,b:26},max=Math.max(1,...data.map(d=>Math.max(d.inc,d.out)))*1.1,slot=(W-P.l-P.r)/data.length,bw=Math.min(22,slot/3.2);
  const y=v=>H-P.b-(v/max)*(H-P.t-P.b);
  const bars=data.map((d,i)=>{const cx=P.l+slot*i+slot/2,net=d.inc-d.out;return `<g class="${d.k===key?'is-current':''}"><rect x="${cx-bw-2}" y="${y(d.inc)}" width="${bw}" height="${Math.max(0,y(0)-y(d.inc))}" rx="4" class="ov-bar-in"><title>Entrou: ${brl(d.inc)}</title></rect><rect x="${cx+2}" y="${y(d.out)}" width="${bw}" height="${Math.max(0,y(0)-y(d.out))}" rx="4" class="ov-bar-out"><title>Saiu: ${brl(d.out)}</title></rect><text x="${cx}" y="${Math.min(y(d.inc),y(d.out))-7}" text-anchor="middle" class="ov-net ${net<0?'is-bad':'is-good'}">${d.inc||d.out?(net<0?'−':'+')+ovShort(Math.abs(net)).replace('R$ ',''):''}</text><text x="${cx}" y="${H-6}" text-anchor="middle" class="ov-axis">${ovMonthShort(d.k)}</text></g>`}).join('');
  ovEl('ovHistory').innerHTML=`<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Entradas e saídas dos últimos seis meses"><line x1="${P.l}" x2="${W-P.r}" y1="${y(0)}" y2="${y(0)}" class="ov-base"/>${bars}</svg>`;
}

function ovInvestments(){
  const summary=portfolio?.summary||{},items=(portfolio?.investments||[]).filter(i=>(+i.current_value||0)>0.004);
  const total=+summary.total_with_cash||0,profit=+summary.profit_loss||0,ret=+summary.return_percent||0;
  ovEl('ovWealth').textContent=brl(total);
  ovEl('ovWealthNote').textContent=`${items.length} ${items.length===1?'ativo':'ativos'} · caixa ${brl(+summary.cash_balance||0)}`;
  const p=ovEl('ovProfit');p.textContent=(profit>0?'+':'')+brl(profit);p.className=profit<0?'is-bad':profit>0?'is-good':'';
  ovEl('ovProfitNote').textContent=`${ret>=0?'+':''}${ovPct(ret,2)} sobre ${brl(+summary.amount_applied||0)} aplicados`;
  ovEl('ovMonthly').textContent=brl(+summary.monthly_estimated_gain||0);
  const byClass={};items.forEach(i=>byClass[i.type]=(byClass[i.type]||0)+(+i.current_value||0));
  if(+summary.cash_balance>0)byClass['Caixa']=+summary.cash_balance;
  const segs=Object.entries(byClass).sort((a,b)=>b[1]-a[1]).map(([label,value],i)=>({label,value,color:OV_CLASS_COLORS[label]||OV_COLORS[i]}));
  const sum=segs.reduce((s,x)=>s+x.value,0);
  ovEl('ovAllocDonut').innerHTML=ovDonut(segs,sum?ovShort(sum):'R$ 0','patrimônio');
  ovEl('ovAllocLegend').innerHTML=segs.length?ovLegend(segs,sum):'<li class="ov-empty">Nenhum investimento cadastrado.</li>';
  const assets=items.map(i=>({label:i.symbol||i.name||i.type,ret:+(i.total_return_percent??i.return_percent??0),value:+i.current_value||0,profit:+(i.total_profit_loss??i.profit_loss??0)})).sort((a,b)=>b.value-a.value).slice(0,6);
  const span=Math.max(1,...assets.map(a=>Math.abs(a.ret)));
  ovEl('ovAssets').innerHTML=assets.length?assets.map(a=>`<div class="ov-asset ${a.ret<0?'is-bad':'is-good'}"><span class="ov-asset-name">${esc(a.label)}</span><div class="ov-diverge"><i style="width:${Math.abs(a.ret)/span*50}%"></i></div><b>${a.ret>=0?'+':''}${ovPct(a.ret,1)}</b><small>${brl(a.value)}</small></div>`).join(''):'<p class="ov-empty">Cadastre investimentos para ver o desempenho.</p>';
}

function ovCommitments(){
  const today=ovToday(),cardNames=Object.fromEntries((ACCOUNT_PREFERENCES?.credit_cards||[]).map(c=>[c.id,c.name]));
  const groupOf=e=>e.installment_group||(e.finance?.card_purchase_id&&e.installment_count>1?'card:'+e.finance.card_purchase_id:null);
  const open=DATA.filter(e=>groupOf(e)&&!e.finance?.paid&&e.date>=today.slice(0,7)+'-01');
  const debts=open.filter(e=>e.finance?.debt_entry),parcels=open.filter(e=>!e.finance?.debt_entry&&e.date>today);
  const group=list=>{const g={};list.forEach(e=>{const k=groupOf(e),card=cardNames[e.finance?.credit_card_id];(g[k]=g[k]||{label:card?`${e.where} · ${card}`:e.where,total:0,count:0,last:e.date}).total+=e.amount;g[k].count++;if(e.date>g[k].last)g[k].last=e.date});return Object.values(g).sort((a,b)=>b.total-a.total)};
  const debtGroups=group(debts),parcelGroups=group(parcels),debtTotal=debtGroups.reduce((s,x)=>s+x.total,0),parcelTotal=parcelGroups.reduce((s,x)=>s+x.total,0),max=Math.max(1,...debtGroups.map(x=>x.total),...parcelGroups.map(x=>x.total));
  const row=(g,cls)=>`<div class="ov-debt ${cls}"><div><span>${esc(g.label)}</span><small>${g.count} ${g.count===1?'parcela':'parcelas'} · até ${new Date(g.last+'T12:00:00').toLocaleDateString('pt-BR',{month:'short',year:'2-digit'}).replace('.','')}</small></div><div class="ov-track"><i style="width:${g.total/max*100}%"></i></div><b>${brl(g.total)}</b></div>`;
  ovEl('ovDebts').innerHTML=(debtGroups.length||parcelGroups.length)?`<div class="ov-debt-kpis"><div><small>Empréstimos e financiamentos</small><strong>${brl(debtTotal)}</strong></div><div><small>Compras parceladas</small><strong>${brl(parcelTotal)}</strong></div></div>${debtGroups.slice(0,3).map(g=>row(g,'is-debt')).join('')}${parcelGroups.slice(0,3).map(g=>row(g,'is-parcel')).join('')}`:'<p class="ov-empty">Nenhuma dívida ou parcela em aberto.</p>';
  const limit=new Date(today+'T12:00:00');limit.setDate(limit.getDate()+30);const end=limit.toISOString().slice(0,10);
  const paidByInvoice={};(ACCOUNT_PREFERENCES?.card_payments||[]).filter(p=>!p.reversed).forEach(p=>paidByInvoice[p.invoice_key]=(paidByInvoice[p.invoice_key]||0)+p.amount);
  const invoices={};DATA.filter(e=>e.finance?.invoice_key&&e.date>=today&&e.date<=end).forEach(e=>{const k=e.finance.invoice_key;(invoices[k]=invoices[k]||{date:e.date,where:'Fatura '+(cardNames[k.split(':')[0]]||'do cartão'),amount:-(paidByInvoice[k]||0),invoice:true}).amount+=e.amount});
  const next=[...DATA.filter(e=>e.date>=today&&e.date<=end&&!e.finance?.paid&&!e.finance?.invoice_key&&(e.installment_group||e.finance?.fixed_expense_id||e.finance?.scheduled_date)),...Object.values(invoices).filter(i=>i.amount>0.004)].sort((a,b)=>a.date.localeCompare(b.date)).slice(0,5);
  ovEl('ovUpcoming').innerHTML=next.length?next.map(e=>{const d=new Date(e.date+'T12:00:00');const days=Math.round((d-new Date(today+'T12:00:00'))/864e5);return `<li><span class="ov-date"><b>${d.getDate()}</b>${d.toLocaleDateString('pt-BR',{month:'short'}).replace('.','')}</span><div><span>${esc(e.where)}</span><small>${days===0?'hoje':days===1?'amanhã':'em '+days+' dias'}${e.invoice?' · cartão':e.installment_number?` · ${e.installment_number}/${e.installment_count}`:''}</small></div><b>${brl(e.amount)}</b></li>`}).join(''):'<li class="ov-empty">Nada vencendo nos próximos 30 dias.</li>';
}

function renderOverview(){
  if(!ovEl('overview')||!month?.value)return;
  try{
    const key=month.value,n=ovMonthNumbers(key),today=ovToday(),isCurrent=today.startsWith(key);
    ovEl('ovMonthTitle').textContent=ovMonthName(key);
    const status=ovEl('ovStatus'),ratio=n.income?n.out/n.income:0;
    if(!n.income&&!n.out){status.textContent='Sem movimentos';status.className='ov-status'}
    else if(n.balance<0){status.textContent='Gastos acima da renda';status.className='ov-status is-bad'}
    else if(ratio>=.9){status.textContent='No limite';status.className='ov-status is-warn'}
    else{status.textContent='No azul';status.className='ov-status is-good'}
    const bal=ovEl('ovBalance');bal.textContent=brl(n.balance);bal.className='ov-big '+(n.balance<0?'is-bad':n.balance>0?'is-good':'');
    const daysLeft=ovDaysIn(key)-+today.slice(8,10);
    ovEl('ovDaysLeft').textContent=isCurrent?(daysLeft?`faltam ${daysLeft} ${daysLeft===1?'dia':'dias'}`:'último dia'):key<today.slice(0,7)?'mês fechado':'previsão';
    const base=Math.max(n.income,n.out,1),seg=(v,cls,label)=>v>0?`<i class="${cls}" style="width:${v/base*100}%" title="${esc(label)}: ${brl(v)}"></i>`:'';
    ovEl('ovBudgetBar').innerHTML=seg(n.paid,'s-paid','Já saiu')+seg(n.pending,'s-pending','Falta pagar')+seg(Math.max(0,n.balance),'s-free','Sobra');
    ovEl('ovBudgetLegend').innerHTML=`<span><i class="s-paid"></i>Já saiu ${n.income?ovPct(n.paid/n.income*100):''}</span><span><i class="s-pending"></i>Falta pagar ${n.income?ovPct(n.pending/n.income*100):''}</span><span><i class="s-free"></i>Sobra ${n.income?ovPct(Math.max(0,n.balance)/n.income*100):''}</span>`;
    ovEl('ovIn').textContent=brl(n.income);
    ovEl('ovInNote').textContent=n.voucher?`+ ${brl(n.voucher)} de voucher`:(n.confirmed<n.income?`${brl(n.confirmed)} confirmado`:'renda do mês');
    ovEl('ovOut').textContent=brl(n.paid);
    ovEl('ovOutNote').textContent=n.income?`${ovPct(n.paid/n.income*100)} da renda`:`${n.rows.length} lançamentos`;
    ovEl('ovDue').textContent=brl(n.pending);
    ovEl('ovDueNote').textContent=n.pending?'contas e parcelas do mês':'tudo pago';
    ovPaceChart(key,n);ovLimits(key);ovCategories(n);ovHistoryChart(key);ovInvestments();ovCommitments();
  }catch(error){console.error('Início',error)}
}
(function(){
  const period=document.querySelector('.global-period'),actions=document.querySelector('.top-actions');
  if(period&&actions){actions.prepend(period);period.classList.add('in-top')}
  const wrap=name=>{const original=window[name];if(typeof original!=='function')return;window[name]=function(...args){const result=original.apply(this,args);renderOverview();return result}};
  ['render','renderInvestments'].forEach(wrap);
  ['finance-updated','insights-updated','bootstrap-loaded'].forEach(name=>document.addEventListener(name,()=>queueMicrotask(renderOverview)));
  month.addEventListener('change',renderOverview);
  renderOverview();
})();
