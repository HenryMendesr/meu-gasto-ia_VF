const debtForm=document.querySelector('#debtForm'),debtFilter=document.querySelector('#debtChartFilter');
const debtTypes={loan:['Pessoal','Consignado','Com garantia','Outro empréstimo'],debt:['Cartão de crédito','Cheque especial','Conta em atraso','Acordo / renegociação','Outra dívida'],asset:['Imóvel','Veículo','Outro bem']};
const debtKindNames={loan:'Empréstimo',debt:'Dívida',asset:'Financiamento'};
function localDateValue(){const now=new Date();return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`}
function debtDate(first,index){const value=new Date(first+'T12:00:00'),day=value.getDate();value.setDate(1);value.setMonth(value.getMonth()+index);value.setDate(Math.min(day,new Date(value.getFullYear(),value.getMonth()+1,0).getDate()));return `${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}-${String(value.getDate()).padStart(2,'0')}`}
function debtRound(value){return Math.round((value+Number.EPSILON)*100)/100}
function debtPlan(principal,count,rate,system){
 if(!(principal>0)||principal>10000000||!Number.isInteger(count)||count<1||count>600||!Number.isFinite(rate)||rate<0||rate>1||!['price','sac'].includes(system))return null;
 const fixed=debtRound(rate?principal*rate/(1-Math.pow(1+rate,-count)):principal/count),capital=debtRound(principal/count);
 let balance=principal;const parts=[];
 for(let i=0;i<count;i++){
  const interest=debtRound(balance*rate),amount=i===count-1?debtRound(balance+interest):system==='sac'?debtRound(capital+interest):fixed;
  const amortization=debtRound(amount-interest);
  if(amortization<=0||(i<count-1&&amortization>=balance)||amount>10000000)return null;
  balance=debtRound(balance-amortization);parts.push({amount,interest,amortization,balance});
 }
 return parts;
}
function updateDebtForm(event){
 const e=debtForm.elements,kind=e.financing_kind.value,asset=kind==='asset';
 const types=debtTypes[kind],oldType=e.debt_type.value;
 if([...e.debt_type.options].map(x=>x.value).join('|')!==types.join('|')){e.debt_type.replaceChildren(...types.map(x=>new Option(x,x)));if(types.includes(oldType))e.debt_type.value=oldType}
 document.querySelector('#debtTypeLabel').textContent=asset?'Tipo de bem':kind==='debt'?'Origem da dívida':'Tipo de empréstimo';
 document.querySelector('#debtCreditorLabel').textContent=kind==='debt'?'Credor / empresa':'Banco / credor';
 document.querySelector('#debtAmountLabel').textContent=asset?'Valor financiado, sem juros (R$)':kind==='debt'?'Saldo atual a negociar (R$)':'Valor emprestado / saldo atual (R$)';
 document.querySelectorAll('.debt-asset').forEach(label=>{label.hidden=!asset;const input=label.querySelector('input');input.disabled=!asset;input.required=asset&&input.name!=='down_payment'});
 e.amount.readOnly=asset;e.amortization_system.disabled=!asset;if(!asset)e.amortization_system.value='price';
 if(asset){const principal=moneyValue(e.asset_value.value)-moneyValue(e.down_payment.value);e.amount.value=principal>0?moneyText(principal):''}
 const selectedCategory=e.category.value;
 e.category.replaceChildren(...ALL_CATEGORIES.map(x=>new Option(x,x)));if(ALL_CATEGORIES.includes(selectedCategory))e.category.value=selectedCategory;else e.category.value=asset?'Moradia':'Contas';
 const parts=debtPlan(moneyValue(e.amount.value),Number(e.installment_count.value),Number(e.interest_rate.value.replace(',','.'))/100,e.amortization_system.value),preview=document.querySelector('#debtPreview');
 e.amount.setCustomValidity(parts?'':'Informe um saldo positivo, taxa de 0 a 100% ao mês e de 1 a 600 parcelas que reduzam a dívida.');
 if(!parts){preview.textContent='Preencha o saldo, a taxa mensal e o prazo para ver a simulação.';return null}
 const total=parts.reduce((s,p)=>s+p.amount,0),first=parts[0].amount,last=parts.at(-1).amount;
 preview.innerHTML=`<strong>${parts.length} parcela(s) · ${e.amortization_system.value==='sac'?'De '+brl(first)+' até '+brl(last):'Primeira de '+brl(first)}</strong><span>Principal: ${brl(moneyValue(e.amount.value))} · Juros: ${brl(total-moneyValue(e.amount.value))}</span><span>Total a pagar: <b>${brl(total)}</b></span>${e.first_charge_date.value?`<small>De ${date(e.first_charge_date.value)} a ${date(debtDate(e.first_charge_date.value,parts.length-1))}. As parcelas vão para esses meses automaticamente.</small>`:''}`;
 return parts;
}
debtForm.querySelectorAll('[data-money]').forEach(input=>input.addEventListener('input',()=>maskMoney(input)));
debtForm.addEventListener('input',updateDebtForm);debtForm.addEventListener('change',updateDebtForm);
function resetDebtForm(){document.querySelector('#debtFormMessage').hidden=true;debtForm.reset();debtForm.elements.date.value=localDateValue();debtForm.elements.first_charge_date.value=debtDate(localDateValue(),1);updateDebtForm()}
function debtGroups(){
 const groups=new Map();
 DATA.filter(item=>item.installment_group&&['loan','debt','asset'].includes(item.finance?.financing_kind)).forEach(item=>{if(!groups.has(item.installment_group))groups.set(item.installment_group,[]);groups.get(item.installment_group).push(item)});
 return [...groups.entries()].map(([id,items])=>{items.sort((a,b)=>a.date.localeCompare(b.date)||a.installment_number-b.installment_number);return {id,items,first:items[0],principal:items[0].finance?.principal??items[0].original_total??items.reduce((s,x)=>s+x.amount,0)}});
}
function debtChartData(groups){
 const months=new Map();let principal=0;
 for(const group of groups){
  principal+=group.principal;let balance=group.principal;
  for(const item of group.items){
   const rate=Number(item.finance?.interest_rate||0)/100,interest=item.finance?.interest_part??debtRound(balance*rate),capital=item.finance?.principal_part??Math.max(0,debtRound(item.amount-interest));
   balance=Math.max(0,debtRound(balance-capital));const key=item.date.slice(0,7);
   if(!months.has(key))months.set(key,{month:key,principal:0,interest:0,payments:0});
   const point=months.get(key);point.principal+=capital;point.interest+=interest;point.payments+=item.amount;
  }
 }
 let balance=principal;const sorted=[...months.values()].sort((a,b)=>a.month.localeCompare(b.month));
 for(const point of sorted){balance=Math.max(0,debtRound(balance-point.principal));point.balance=balance}
 return {principal,months:sorted};
}
function drawDebtCharts(groups){
 const {principal,months}=debtChartData(groups),empty=!months.length;
 document.querySelector('#debtChartEmpty').hidden=!empty;document.querySelector('#debtChartContent').hidden=empty;if(empty)return;
 const width=600,height=230,left=70,right=18,top=20,bottom=42,plotW=width-left-right,plotH=height-top-bottom;
 const points=[principal,...months.map(m=>m.balance)],max=Math.max(1,...points),x=i=>left+i/(points.length-1)*plotW,y=v=>top+(1-v/max)*plotH;
 const line=points.map((v,i)=>`${x(i)},${y(v)}`).join(' '),area=`${left},${height-bottom} ${line} ${width-right},${height-bottom}`;
 const labels=[0,.5,1].map(f=>{const py=top+plotH*f;return `<line x1="${left}" y1="${py}" x2="${width-right}" y2="${py}" stroke="#e1e9e3"/><text x="${left-8}" y="${py+4}" text-anchor="end">${esc(brl(max*(1-f)))}</text>`}).join('');
 const marks=points.length>100?[]:points;
 document.querySelector('#debtBalanceChart').innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Saldo projetado de ${esc(brl(principal))} até ${esc(brl(points.at(-1)))}"><title>Saldo devedor projetado após cada mês</title>${labels}<polygon points="${area}" fill="#176b50" opacity=".09"/><polyline points="${line}" fill="none" stroke="#176b50" stroke-width="3"/>${marks.map((v,i)=>`<circle cx="${x(i)}" cy="${y(v)}" r="3" fill="#176b50"><title>${i?monthLabel(months[i-1].month):'Saldo inicial'}: ${brl(v)}</title></circle>`).join('')}<text x="${left}" y="${height-14}">Início</text><text x="${width-right}" y="${height-14}" text-anchor="end">${esc(monthLabel(months.at(-1).month))}</text></svg>`;
 const barWidth=months.length>24?Math.max(600,months.length*30+left+right):600,barMax=Math.max(1,...months.map(m=>m.payments)),slot=(barWidth-left-right)/months.length,bw=Math.min(28,slot*.68),barY=v=>top+(1-v/barMax)*plotH;
 document.querySelector('#debtPaymentChart').innerHTML=`<svg viewBox="0 0 ${barWidth} ${height}" style="width:${barWidth>600?barWidth+'px':'100%'}" role="img" aria-label="Parcelas mensais divididas em principal e juros"><title>Parcelas mensais: principal em verde e juros em dourado</title>${[0,.5,1].map(f=>{const py=top+plotH*f;return `<line x1="${left}" y1="${py}" x2="${barWidth-right}" y2="${py}" stroke="#e1e9e3"/><text x="${left-8}" y="${py+4}" text-anchor="end">${esc(brl(barMax*(1-f)))}</text>`}).join('')}${months.map((m,i)=>{const bx=left+slot*i+(slot-bw)/2,base=height-bottom;return `<g><title>${esc(monthLabel(m.month))}: ${brl(m.payments)} · Principal ${brl(m.principal)} · Juros ${brl(m.interest)}</title><rect x="${bx}" y="${barY(m.principal)}" width="${bw}" height="${m.principal/barMax*plotH}" rx="2" fill="#176b50"/><rect x="${bx}" y="${barY(m.payments)}" width="${bw}" height="${m.interest/barMax*plotH}" rx="2" fill="#e5b366"/>${months.length<=12||i%Math.ceil(months.length/12)===0?`<text x="${bx+bw/2}" y="${base+20}" text-anchor="middle">${m.month.slice(5)}/${m.month.slice(2,4)}</text>`:''}</g>`}).join('')}</svg>`;
 const items=groups.flatMap(g=>g.items).sort((a,b)=>a.date.localeCompare(b.date));
 document.querySelector('#debtScheduleRows').innerHTML=items.map(item=>`<tr><td>${date(item.date)}</td><td>${esc(item.where)}</td><td>${item.finance?.principal_part!=null?brl(item.finance.principal_part):'—'}</td><td>${item.finance?.interest_part!=null?brl(item.finance.interest_part):'—'}</td><td class="money">${brl(item.amount)}</td></tr>`).join('');
}
function renderDebtsPanel(){
 const groups=debtGroups(),selected=debtFilter.value;
 debtFilter.replaceChildren(new Option('Todos os compromissos',''),...groups.map(g=>new Option(`${debtKindNames[g.first.finance.financing_kind]} · ${g.first.where}`,g.id)));
 if(groups.some(g=>g.id===selected))debtFilter.value=selected;
 const visible=groups.filter(g=>!debtFilter.value||g.id===debtFilter.value),principal=visible.reduce((s,g)=>s+g.principal,0),total=visible.reduce((s,g)=>s+g.items.reduce((v,x)=>v+x.amount,0),0);
 document.querySelector('#debtPrincipalTotal').textContent=brl(principal);document.querySelector('#debtInterestTotal').textContent=brl(Math.max(0,total-principal));document.querySelector('#debtPaymentsTotal').textContent=brl(total);
 drawDebtCharts(visible);document.querySelector('#debtContractCount').textContent=`${groups.length} contrato(s)`;
 document.querySelector('#debtContractList').innerHTML=groups.length?groups.map(g=>{const f=g.first.finance,total=g.items.reduce((s,x)=>s+x.amount,0);return `<article class="debt-contract"><div><h4>${esc(debtKindNames[f.financing_kind])} · ${esc(g.first.where)}</h4><p>${esc(f.debt_type||'Contrato cadastrado')} ${f.asset_name?'· '+esc(f.asset_name):''} · ${Number(f.interest_rate||0).toLocaleString('pt-BR')}% ao mês · ${esc((f.amortization_system||'price').toUpperCase())}</p><p>${g.items.length} parcela(s) de ${date(g.first.date)} a ${date(g.items.at(-1).date)} · Total ${brl(total)}</p><p>Principal ${brl(g.principal)} · Juros previstos ${brl(Math.max(0,total-g.principal))}</p></div><div class="debt-contract-actions"><button type="button" class="secondary" data-view-debt="${g.id}">Ver gráfico</button><button type="button" class="danger" data-remove-debt="${g.first.id}">Excluir</button></div></article>`}).join(''):'<div class="empty">Nenhum empréstimo, dívida ou financiamento cadastrado.</div>';
}
debtFilter.addEventListener('change',renderDebtsPanel);
document.querySelector('#newDebtButton').addEventListener('click',()=>{resetDebtForm();debtForm.scrollIntoView({behavior:'smooth',block:'start'});debtForm.elements.financing_kind.focus()});
debtForm.addEventListener('submit',async event=>{
 event.preventDefault();const message=document.querySelector('#debtFormMessage'),button=debtForm.querySelector('[type="submit"]');message.hidden=true;
 if(!canWrite){message.textContent=localOnlyMessage();message.className='message error';message.hidden=false;return}
 if(!updateDebtForm()||!debtForm.reportValidity())return;
 const payload=Object.fromEntries(new FormData(debtForm));payload.amount=moneyValue(payload.amount);payload.asset_value=moneyValue(payload.asset_value);payload.down_payment=moneyValue(payload.down_payment);payload.debt_entry=true;payload.installment=true;payload.amortization_system=debtForm.elements.amortization_system.value;
 button.disabled=true;
 try{
  let response=await fetch('/api/expenses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),result=await response.json();
  if(response.status===409&&result.code==='duplicate'&&confirm(`${result.error}. Cadastrar mesmo assim?`)){payload.allow_duplicate=true;response=await fetch('/api/expenses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});result=await response.json()}
  if(!response.ok)throw new Error(result.error||'Não foi possível salvar o compromisso.');
  await loadBootstrap();debtFilter.value=result.installment_group||'';renderDebtsPanel();resetDebtForm();message.textContent=`Compromisso salvo. ${result.ids?.length||1} parcela(s) no calendário e gráficos atualizados.`;message.className='message ok';message.hidden=false;
 }catch(error){message.textContent=error.message;message.className='message error';message.hidden=false}finally{button.disabled=false}
});
document.querySelector('#debtContractList').addEventListener('click',async event=>{
 const view=event.target.closest('[data-view-debt]'),remove=event.target.closest('[data-remove-debt]');
 if(view){debtFilter.value=view.dataset.viewDebt;renderDebtsPanel();document.querySelector('.debt-analysis').scrollIntoView({behavior:'smooth',block:'start'})}
 if(remove&&confirm('Excluir este compromisso e todas as parcelas dele?')){
  remove.disabled=true;try{const response=await fetch(`/api/expenses/${remove.dataset.removeDebt}?scope=all`,{method:'DELETE'}),result=await response.json();if(!response.ok)throw new Error(result.error||'Não foi possível excluir');await loadBootstrap()}catch(error){alert(error.message);remove.disabled=false}
 }
});
resetDebtForm();renderDebtsPanel();
