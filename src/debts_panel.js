const debtForm=document.querySelector('#debtForm'),debtFilter=document.querySelector('#debtChartFilter');
let editingDebtId=null;
const debtTypes={loan:['Pessoal','Consignado','Com garantia','Outro empréstimo'],debt:['Cartão de crédito','Cheque especial','Conta em atraso','Acordo / renegociação','Outra dívida'],asset:['Imóvel','Veículo','Outro bem']};
const debtKindNames={loan:'Empréstimo',debt:'Dívida',asset:'Financiamento'};
function localDateValue(){const now=new Date();return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,'0')}-${String(now.getDate()).padStart(2,'0')}`}
function debtDate(first,index){const value=new Date(first+'T12:00:00'),day=value.getDate();value.setDate(1);value.setMonth(value.getMonth()+index);value.setDate(Math.min(day,new Date(value.getFullYear(),value.getMonth()+1,0).getDate()));return `${value.getFullYear()}-${String(value.getMonth()+1).padStart(2,'0')}-${String(value.getDate()).padStart(2,'0')}`}
function debtRound(value){return Math.round((value+Number.EPSILON)*100)/100}
function debtPlan(principal,count,rate,system,regular=null){
 if(!(principal>0)||principal>10000000||!Number.isInteger(count)||count<1||count>600||!Number.isFinite(rate)||rate<0||rate>1||!['price','sac'].includes(system))return null;
 const fixed=regular??debtRound(rate?principal*rate/(1-Math.pow(1+rate,-count)):principal/count),capital=debtRound(principal/count);
 let balance=principal;const parts=[];
 for(let i=0;i<count;i++){
  const interest=debtRound(balance*rate),amount=i===count-1?debtRound(balance+interest):system==='sac'?debtRound(capital+interest):fixed;
  const amortization=debtRound(amount-interest);
  if(amortization<=0||(i<count-1&&amortization>=balance)||amount>10000000)return null;
  balance=debtRound(balance-amortization);parts.push({amount,interest,amortization,balance});
 }
 return parts;
}
function inferDebtRate(principal,payment,count){
 if(!(principal>0)||!(payment>0)||!Number.isInteger(count)||count<1||count>600)return null;
 if(Math.abs(payment-principal/count)<=.005)return 0;
 if(payment*count<principal)return null;
 const installment=rate=>principal*rate/(1-Math.pow(1+rate,-count));
 if(payment>installment(1)+.005)return null;
 let low=0,high=1;for(let i=0;i<70;i++){const mid=(low+high)/2;if(installment(mid)<payment)low=mid;else high=mid}
 return (low+high)/2;
}
function updateDebtForm(){
 const e=debtForm.elements,kind=e.financing_kind.value,asset=kind==='asset',automatic=e.calculation_mode.value==='payment';
 const types=debtTypes[kind],oldType=e.debt_type.value;
 if([...e.debt_type.options].map(x=>x.value).join('|')!==types.join('|')){e.debt_type.replaceChildren(...types.map(x=>new Option(x,x)));if(types.includes(oldType))e.debt_type.value=oldType}
 document.querySelector('#debtTypeLabel').textContent=asset?'Tipo de bem':kind==='debt'?'Origem da dívida':'Tipo de empréstimo';
 document.querySelector('#debtCreditorLabel').textContent=kind==='debt'?'Credor / empresa':'Banco / credor';
 document.querySelector('#debtAmountLabel').textContent=asset?'Valor financiado, sem juros (R$)':'Saldo atual sem juros (R$)';
 document.querySelectorAll('.debt-asset').forEach(label=>{label.hidden=!asset;const input=label.querySelector('input');input.disabled=!asset;input.required=asset&&input.name!=='down_payment'});
 e.amount.readOnly=asset;e.amortization_system.disabled=!asset||automatic;if(!asset||automatic)e.amortization_system.value='price';
 if(asset){const principal=moneyValue(e.asset_value.value)-moneyValue(e.down_payment.value);e.amount.value=principal>0?moneyText(principal):''}
 const selectedCategory=e.category.value;e.category.replaceChildren(...ALL_CATEGORIES.map(x=>new Option(x,x)));if(ALL_CATEGORIES.includes(selectedCategory))e.category.value=selectedCategory;else e.category.value=asset?'Moradia':'Contas';
 document.querySelector('#debtPaymentField').hidden=!automatic;e.installment_amount.disabled=!automatic;e.installment_amount.required=automatic;
 e.interest_rate.readOnly=automatic;e.interest_rate.required=!automatic;document.querySelector('#debtRateLabel').textContent=automatic?'Juros estimados ao mês (%)':'Juros ao mês (%)';
 const principal=moneyValue(e.amount.value),count=Number(e.installment_count.value),regular=automatic?moneyValue(e.installment_amount.value):null,rate=automatic?inferDebtRate(principal,regular,count):Number(e.interest_rate.value.replace(',','.'))/100;
 if(automatic)e.interest_rate.value=rate==null?'':(rate*100).toFixed(8).replace(/0+$/,'').replace(/\.$/,'');
 const parts=rate==null?null:debtPlan(principal,count,rate,e.amortization_system.value,regular),preview=document.querySelector('#debtPreview');
 const error=automatic?'Revise o saldo sem juros, o valor da parcela e o prazo. As parcelas devem cobrir o saldo, com juros estimados entre 0 e 100% ao mês.':'Informe um saldo positivo, taxa de 0 a 100% ao mês e de 1 a 600 parcelas que reduzam a dívida.';
 e.amount.setCustomValidity(parts?'':error);e.installment_amount.setCustomValidity(automatic&&!parts?error:'');
 document.querySelector('#debtCalculationHelp').textContent=automatic?'Informe o saldo sem juros e quanto paga por mês, durante quantos meses. A taxa é estimada para parcelas fixas (Price), com pagamentos mensais. Não é o CET e não separa tarifas, seguros ou impostos incluídos na parcela. A última parcela pode ajustar alguns centavos.':'Valores com centavos automáticos: 12345 → 123,45. Use a taxa mensal do contrato. Price mantém as parcelas; SAC reduz as parcelas com o tempo. A entrada já paga não gera outro gasto.';
 if(!parts){preview.textContent=automatic?'Preencha saldo sem juros, valor da parcela e quantidade de meses para estimar os juros.':'Preencha o saldo, a taxa mensal e o prazo para ver a simulação.';return null}
 const total=parts.reduce((sum,p)=>sum+p.amount,0),first=parts[0].amount,last=parts.at(-1).amount;
 preview.innerHTML=`<strong>${parts.length} parcela(s) · ${e.amortization_system.value==='sac'?'De '+brl(first)+' até '+brl(last):'Primeira de '+brl(first)}</strong>${automatic?`<span>Juros estimados: <b>${(rate*100).toLocaleString('pt-BR',{maximumFractionDigits:6})}% ao mês</b></span>`:''}<span>Principal: ${brl(principal)} · Juros: ${brl(total-principal)}</span><span>Total a pagar: <b>${brl(total)}</b></span>${e.first_charge_date.value?`<small>De ${date(e.first_charge_date.value)} a ${date(debtDate(e.first_charge_date.value,parts.length-1))}. As parcelas vão para esses meses automaticamente.</small>`:''}`;
 return parts;
}
debtForm.querySelectorAll('[data-money]').forEach(input=>input.addEventListener('input',()=>maskMoney(input)));
debtForm.addEventListener('input',updateDebtForm);debtForm.addEventListener('change',updateDebtForm);
function resetDebtForm(){editingDebtId=null;document.querySelector('#debtFormMessage').hidden=true;debtForm.reset();debtForm.elements.date.value=localDateValue();debtForm.elements.first_charge_date.value=debtDate(localDateValue(),1);document.querySelector('#debtFormTitle').textContent='Novo compromisso';debtForm.querySelector('[type="submit"]').textContent='Salvar e gerar parcelas';document.querySelector('#cancelDebtEdit').hidden=true;document.querySelector('#debtEditNotice').hidden=true;updateDebtForm()}
function editDebt(groupId){
 const group=debtGroups().find(g=>g.id===groupId);if(!group)return;resetDebtForm();const f=group.first.finance,e=debtForm.elements;
 e.financing_kind.value=f.financing_kind;updateDebtForm();
 const fields={debt_type:f.debt_type||debtTypes[f.financing_kind][0],where:group.first.where,amount:moneyText(group.principal),interest_rate:String(f.interest_rate||0),installment_count:group.items.length,first_charge_date:group.first.date,date:f.contract_date||group.first.date,amortization_system:f.amortization_system||'price',payment:group.first.payment,category:group.first.category,description:group.first.description.replace(/(?:^| · )Parcela \d+\/\d+$/,''),asset_name:f.asset_name||'',asset_value:f.asset_value!=null?moneyText(f.asset_value):'',down_payment:f.down_payment!=null?moneyText(f.down_payment):'',calculation_mode:f.calculation_mode||'rate',installment_amount:moneyText(f.installment_amount||group.first.amount)};
 Object.entries(fields).forEach(([key,value])=>e[key].value=value);editingDebtId=group.first.id;updateDebtForm();document.querySelector('#debtFormTitle').textContent='Editar compromisso';debtForm.querySelector('[type="submit"]').textContent='Salvar alterações';document.querySelector('#cancelDebtEdit').hidden=false;const notice=document.querySelector('#debtEditNotice');notice.textContent=`Ao salvar, as ${group.items.length} parcelas deste cadastro serão substituídas pelo novo calendário, inclusive as de datas passadas. Outros gastos não serão alterados.`;notice.hidden=false;document.querySelector('.debt-form-card').scrollIntoView({behavior:'smooth',block:'start'});e.where.focus({preventScroll:true});
}
document.querySelector('#cancelDebtEdit').addEventListener('click',resetDebtForm);
function debtGroups(){
 const groups=new Map();
 DATA.filter(item=>item.installment_group&&['loan','debt','asset'].includes(item.finance?.financing_kind)).forEach(item=>{if(!groups.has(item.installment_group))groups.set(item.installment_group,[]);groups.get(item.installment_group).push(item)});
 return [...groups.entries()].map(([id,items])=>{items.sort((a,b)=>a.date.localeCompare(b.date)||a.installment_number-b.installment_number);return {id,items,first:items[0],principal:items[0].finance?.principal??items[0].original_total??items.reduce((s,x)=>s+x.amount,0)}});
}
function debtOpenGroup(group){let balance=group.principal;const items=[];for(const item of group.items){const interest=item.finance?.interest_part??debtRound(balance*Number(item.finance?.interest_rate||0)/100),capital=item.finance?.principal_part??Math.max(0,debtRound(item.amount-interest));balance=debtRound(balance-capital);if(!item.finance?.paid)items.push({...item,finance:{...item.finance,principal_part:capital,interest_part:interest}})}return {...group,items,principal:debtRound(items.reduce((sum,item)=>sum+item.finance.principal_part,0))}}
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
 const scheduleItems=groups.flatMap(g=>g.items).sort((a,b)=>a.date.localeCompare(b.date));
 document.querySelector('#debtScheduleRows').innerHTML=scheduleItems.map(item=>`<tr><td>${date(item.date)}</td><td>${esc(item.where)}</td><td>${item.finance?.principal_part!=null?brl(item.finance.principal_part):'—'}</td><td>${item.finance?.interest_part!=null?brl(item.finance.interest_part):'—'}</td><td class="money">${brl(item.amount)}</td><td><span class="payment-status ${item.finance?.paid?'paid':'pending'}">${item.finance?.paid?'Paga em '+date(item.finance.paid_date):item.date<localDateValue()?'Vencida':'Em aberto'}</span></td><td><button type="button" class="secondary payment-button" data-pay-debt="${item.id}">${item.finance?.paid?'Desfazer baixa':'Marcar paga'}</button></td></tr>`).join('');
 document.querySelector('#debtPaymentCards').innerHTML=scheduleItems.map(item=>`<article class="debt-payment-card"><div><strong>${esc(item.where)}</strong><small>Vencimento ${date(item.date)}</small></div><strong>${brl(item.amount)}</strong><span class="payment-status ${item.finance?.paid?'paid':'pending'}">${item.finance?.paid?'Paga em '+date(item.finance.paid_date):item.date<localDateValue()?'Vencida':'Em aberto'}</span><button class="secondary payment-button" type="button" data-pay-debt="${item.id}">${item.finance?.paid?'Desfazer baixa':'Marcar paga'}</button></article>`).join('');
 const {principal,months}=debtChartData(groups.map(debtOpenGroup)),empty=!months.length;
 document.querySelector('#debtChartEmpty').textContent=groups.length?'Todas as parcelas deste filtro foram pagas. Consulte ou desfaça pagamentos no calendário abaixo.':'Cadastre um compromisso para gerar os gráficos automaticamente.';document.querySelector('#debtChartEmpty').hidden=!empty;document.querySelector('#debtChartContent').hidden=empty;if(empty)return;
 const width=600,height=230,left=70,right=18,top=20,bottom=42,plotW=width-left-right,plotH=height-top-bottom;
 const points=[principal,...months.map(m=>m.balance)],max=Math.max(1,...points),x=i=>left+i/(points.length-1)*plotW,y=v=>top+(1-v/max)*plotH;
 const line=points.map((v,i)=>`${x(i)},${y(v)}`).join(' '),area=`${left},${height-bottom} ${line} ${width-right},${height-bottom}`;
 const labels=[0,.5,1].map(f=>{const py=top+plotH*f;return `<line x1="${left}" y1="${py}" x2="${width-right}" y2="${py}" stroke="#e1e9e3"/><text x="${left-8}" y="${py+4}" text-anchor="end">${esc(brl(max*(1-f)))}</text>`}).join('');
 const marks=points.length>100?[]:points;
 document.querySelector('#debtBalanceChart').innerHTML=`<svg viewBox="0 0 ${width} ${height}" role="img" aria-label="Saldo projetado de ${esc(brl(principal))} até ${esc(brl(points.at(-1)))}"><title>Saldo devedor projetado após cada mês</title>${labels}<polygon points="${area}" fill="#176b50" opacity=".09"/><polyline points="${line}" fill="none" stroke="#176b50" stroke-width="3"/>${marks.map((v,i)=>`<circle cx="${x(i)}" cy="${y(v)}" r="3" fill="#176b50"><title>${i?monthLabel(months[i-1].month):'Saldo inicial'}: ${brl(v)}</title></circle>`).join('')}<text x="${left}" y="${height-14}">Início</text><text x="${width-right}" y="${height-14}" text-anchor="end">${esc(monthLabel(months.at(-1).month))}</text></svg>`;
 const barWidth=months.length>24?Math.max(600,months.length*30+left+right):600,barMax=Math.max(1,...months.map(m=>m.payments)),slot=(barWidth-left-right)/months.length,bw=Math.min(28,slot*.68),barY=v=>top+(1-v/barMax)*plotH;
 document.querySelector('#debtPaymentChart').innerHTML=`<svg viewBox="0 0 ${barWidth} ${height}" style="width:${barWidth>600?barWidth+'px':'100%'}" role="img" aria-label="Parcelas mensais divididas em principal e juros"><title>Parcelas mensais: principal em verde e juros em dourado</title>${[0,.5,1].map(f=>{const py=top+plotH*f;return `<line x1="${left}" y1="${py}" x2="${barWidth-right}" y2="${py}" stroke="#e1e9e3"/><text x="${left-8}" y="${py+4}" text-anchor="end">${esc(brl(barMax*(1-f)))}</text>`}).join('')}${months.map((m,i)=>{const bx=left+slot*i+(slot-bw)/2,base=height-bottom;return `<g><title>${esc(monthLabel(m.month))}: ${brl(m.payments)} · Principal ${brl(m.principal)} · Juros ${brl(m.interest)}</title><rect x="${bx}" y="${barY(m.principal)}" width="${bw}" height="${m.principal/barMax*plotH}" rx="2" fill="#176b50"/><rect x="${bx}" y="${barY(m.payments)}" width="${bw}" height="${m.interest/barMax*plotH}" rx="2" fill="#e5b366"/>${months.length<=12||i%Math.ceil(months.length/12)===0?`<text x="${bx+bw/2}" y="${base+20}" text-anchor="middle">${m.month.slice(5)}/${m.month.slice(2,4)}</text>`:''}</g>`}).join('')}</svg>`;

}
function renderDebtsPanel(){
 const groups=debtGroups(),selected=debtFilter.value;
 debtFilter.replaceChildren(new Option('Todos os compromissos',''),...groups.map(g=>new Option(`${debtKindNames[g.first.finance.financing_kind]} · ${g.first.where}`,g.id)));
 if(groups.some(g=>g.id===selected))debtFilter.value=selected;
 const visible=groups.filter(g=>!debtFilter.value||g.id===debtFilter.value),principal=visible.map(debtOpenGroup).reduce((s,g)=>s+g.principal,0),total=visible.reduce((s,g)=>s+g.items.filter(item=>!item.finance?.paid).reduce((v,x)=>v+x.amount,0),0);
 document.querySelector('#debtPrincipalTotal').textContent=brl(principal);document.querySelector('#debtInterestTotal').textContent=brl(Math.max(0,total-principal));document.querySelector('#debtPaymentsTotal').textContent=brl(total);
 const allParts=visible.flatMap(group=>group.items),paidParts=allParts.filter(item=>item.finance?.paid);document.querySelector('#debtPaidSummary').textContent=`${paidParts.length} de ${allParts.length} parcelas pagas · Total pago: ${brl(paidParts.reduce((sum,item)=>sum+item.amount,0))}`;
 drawDebtCharts(visible);document.querySelector('#debtContractCount').textContent=`${groups.length} contrato(s)`;
 document.querySelector('#debtContractList').innerHTML=groups.length?groups.map(g=>{const f=g.first.finance,total=g.items.reduce((s,x)=>s+x.amount,0);return `<article class="debt-contract"><div><h4>${esc(debtKindNames[f.financing_kind])} · ${esc(g.first.where)}</h4><p>${esc(f.debt_type||'Contrato cadastrado')} ${f.asset_name?'· '+esc(f.asset_name):''} · ${Number(f.interest_rate||0).toLocaleString('pt-BR')}% ao mês · ${esc((f.amortization_system||'price').toUpperCase())}</p><p>${g.items.length} parcela(s) de ${date(g.first.date)} a ${date(g.items.at(-1).date)} · Total ${brl(total)}</p><p>Principal ${brl(g.principal)} · Juros previstos ${brl(Math.max(0,total-g.principal))}</p><p>${g.items.filter(item=>item.finance?.paid).length} de ${g.items.length} parcelas pagas · Em aberto: <strong>${brl(g.items.filter(item=>!item.finance?.paid).reduce((sum,item)=>sum+item.amount,0))}</strong></p>${g.items.some(item=>item.finance?.paid)?'<small class="quiet">Desfaça as baixas no calendário para editar ou excluir o contrato.</small>':''}</div><div class="debt-contract-actions"><button type="button" class="secondary" data-edit-debt="${g.id}" ${g.items.some(item=>item.finance?.paid)?'disabled':''}>Editar dívida</button><button type="button" class="secondary" data-view-debt="${g.id}">Ver gráfico</button><button type="button" class="danger" data-remove-debt="${g.first.id}" ${g.items.some(item=>item.finance?.paid)?'disabled':''}>Excluir</button></div></article>`}).join(''):'<div class="empty">Nenhum empréstimo, dívida ou financiamento cadastrado.</div>';
}
debtFilter.addEventListener('change',renderDebtsPanel);
document.querySelector('#newDebtButton').addEventListener('click',()=>{resetDebtForm();debtForm.scrollIntoView({behavior:'smooth',block:'start'});debtForm.elements.financing_kind.focus()});
debtForm.addEventListener('submit',async event=>{
 event.preventDefault();const message=document.querySelector('#debtFormMessage'),button=debtForm.querySelector('[type="submit"]');message.hidden=true;
 if(!canWrite){message.textContent=localOnlyMessage();message.className='message error';message.hidden=false;return}
 if(!updateDebtForm()||!debtForm.reportValidity())return;
 const payload=Object.fromEntries(new FormData(debtForm));payload.amount=moneyValue(payload.amount);payload.asset_value=moneyValue(payload.asset_value);payload.down_payment=moneyValue(payload.down_payment);if(payload.installment_amount)payload.installment_amount=moneyValue(payload.installment_amount);payload.debt_entry=true;payload.installment=true;payload.amortization_system=debtForm.elements.amortization_system.value;
 button.disabled=true;
 try{
  const wasEditing=editingDebtId!=null;
  let response=await fetch(wasEditing?`/api/debts/${editingDebtId}`:'/api/expenses',{method:wasEditing?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),result=await response.json();
  if(!wasEditing&&response.status===409&&result.code==='duplicate'&&confirm(`${result.error}. Cadastrar mesmo assim?`)){payload.allow_duplicate=true;response=await fetch('/api/expenses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});result=await response.json()}
  if(!response.ok)throw new Error(result.error||'Não foi possível salvar o compromisso.');
  await loadBootstrap();debtFilter.value=result.installment_group||'';renderDebtsPanel();resetDebtForm();message.textContent=`${wasEditing?'Compromisso atualizado.':'Compromisso salvo.'} ${result.ids?.length||1} parcela(s) no calendário e gráficos atualizados.`;message.className='message ok';message.hidden=false;
 }catch(error){message.textContent=error.message;message.className='message error';message.hidden=false}finally{button.disabled=false}
});
document.querySelector('#debtContractList').addEventListener('click',async event=>{
 const edit=event.target.closest('[data-edit-debt]'),view=event.target.closest('[data-view-debt]'),remove=event.target.closest('[data-remove-debt]');
 if(edit){editDebt(edit.dataset.editDebt);return}
 if(view){debtFilter.value=view.dataset.viewDebt;renderDebtsPanel();document.querySelector('.debt-analysis').scrollIntoView({behavior:'smooth',block:'start'})}
 if(remove&&confirm('Excluir este compromisso e todas as parcelas dele?')){
  remove.disabled=true;try{const response=await fetch(`/api/expenses/${remove.dataset.removeDebt}?scope=all`,{method:'DELETE'}),result=await response.json();if(!response.ok)throw new Error(result.error||'Não foi possível excluir');await loadBootstrap()}catch(error){alert(error.message);remove.disabled=false}
 }
});
resetDebtForm();renderDebtsPanel();

const debtPaymentModal=document.querySelector('#debtPaymentModal'),debtPaymentForm=document.querySelector('#debtPaymentForm');
async function saveDebtPayment(id,payload){const response=await fetch(`/api/debts/${id}/payment`,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),result=await response.json();if(!response.ok)throw Error(result.error||'Não foi possível atualizar a parcela');await loadBootstrap();document.dispatchEvent(new Event('finance-updated'))}
document.querySelector('.debt-schedule').addEventListener('click',async event=>{const button=event.target.closest('[data-pay-debt]');if(!button)return;const item=DATA.find(entry=>String(entry.id)===button.dataset.payDebt);if(!item)return;if(item.finance?.paid){button.disabled=true;try{await saveDebtPayment(item.id,{paid:false})}catch(error){const message=document.querySelector('#debtStatusMessage');message.textContent=error.message;message.className='message error';message.hidden=false;button.disabled=false}return}debtPaymentForm.elements.id.value=item.id;debtPaymentForm.elements.paid_date.value=localDateValue();debtPaymentForm.elements.paid_date.max=localDateValue();debtPaymentForm.elements.paid_date.min=item.finance?.contract_date||'1900-01-01';document.querySelector('#debtPaymentDescription').textContent=`${item.where} · ${brl(item.amount)} · Vencimento ${date(item.date)}`;document.querySelector('#debtPaymentMessage').hidden=true;debtPaymentModal.hidden=false;debtPaymentForm.elements.paid_date.focus()});
document.querySelector('#closeDebtPayment').addEventListener('click',()=>debtPaymentModal.hidden=true);debtPaymentModal.addEventListener('click',event=>{if(event.target===debtPaymentModal)debtPaymentModal.hidden=true});document.addEventListener('keydown',event=>{if(event.key==='Escape')debtPaymentModal.hidden=true});debtPaymentForm.addEventListener('submit',async event=>{event.preventDefault();const button=debtPaymentForm.querySelector('[type="submit"]'),message=document.querySelector('#debtPaymentMessage');button.disabled=true;try{await saveDebtPayment(debtPaymentForm.elements.id.value,{paid:true,paid_date:debtPaymentForm.elements.paid_date.value});debtPaymentModal.hidden=true}catch(error){message.textContent=error.message;message.hidden=false}finally{button.disabled=false}});
