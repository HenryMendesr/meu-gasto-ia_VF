// Valores monetários em centavos; aceita também valores colados com vírgula.
function moneyValue(value){return Number(String(value||'').replace(/\./g,'').replace(',','.'))||0}
function moneyText(value){return Number(value).toLocaleString('pt-BR',{minimumFractionDigits:2,maximumFractionDigits:2})}
function maskMoney(input){
 const digits=input.value.replace(/\D/g,'');
 input.value=digits?moneyText(Number(digits)/100):'';
 input.setSelectionRange(input.value.length,input.value.length);
}
const financeForm=document.querySelector('#expenseForm');
financeForm.querySelectorAll('[data-money]').forEach(input=>input.addEventListener('input',()=>maskMoney(input)));
function calculateInstallments(principal,count,payment,rate){
 if(!(principal>0)||!Number.isInteger(count)||count<2||count>120||!Number.isFinite(rate)||rate<0||rate>1)return null;
 if(!payment)payment=Math.round((rate?principal*rate/(1-Math.pow(1+rate,-count)):principal/count)*100)/100;
 let balance=principal;const parts=[];
 for(let number=1;number<=count;number++){
  const interest=Math.round((balance*rate+Number.EPSILON)*100)/100;
  const amount=number===count?Math.round((balance+interest)*100)/100:payment;
  const amortization=Math.round((amount-interest)*100)/100;
  if(amortization<=0||(number<count&&amortization>=balance))return null;
  balance=Math.round((balance-amortization)*100)/100;
  parts.push({amount,interest,amortization,balance});
 }
 return parts;
}
function inferInstallmentCount(principal,payment,rate){
 if(!(principal>0)||!(payment>0)||!Number.isFinite(rate)||rate<0||rate>1)return null;
 let balance=principal;
 for(let n=1;n<=120;n++){
  const interest=Math.round(balance*rate*100)/100;
  if(payment<=interest)return null;
  balance=Math.round((balance+interest-payment)*100)/100;
  if(balance<=n*0.005)return n>=2?n:null;
 }
 return null;
}
function updateCreditOptions(event){
 const f=financeForm,e=f.elements,kind=e.financing_kind.value;
 const credit=(e.payment.value==='Crédito'||kind!=='purchase')&&!editingExpenseId;
 const parcelled=credit&&e.installment.value==='true';
 document.querySelector('#expenseAmountLabel').textContent=parcelled?'Valor financiado, sem juros (R$)':'Valor (R$)';
 document.querySelector('#creditOptions').hidden=!credit;
 document.querySelector('#installmentFields').hidden=!parcelled;
 document.querySelector('#installmentFields').querySelectorAll('input').forEach(input=>{input.disabled=!parcelled;input.required=parcelled});
 const scheduling=['Pix','Transferência'].includes(e.payment.value)&&!parcelled&&!editingExpense?.installment_group;
 document.querySelector('#scheduleOptions').hidden=!scheduling;
 const scheduled=scheduling&&e.scheduled.checked;
 e.scheduled.disabled=!scheduling;e.scheduled_date.disabled=!scheduled;e.scheduled_date.required=scheduled;
 document.querySelector('#scheduleDateField').hidden=!scheduled;
 if(!parcelled)return;
 const principal=moneyValue(e.amount.value),rate=Number(e.interest_rate.value.replace(',','.'))/100;
 let count=Number(e.installment_count.value),payment=moneyValue(e.installment_amount.value);
 const source=event?.target;
 if(source===e.installment_amount&&payment||source===e.installment_count&&!e.installment_count.value){
  const inferred=inferInstallmentCount(principal,payment,rate);
  e.installment_count.value=inferred||'';count=inferred;
 }else if(source!==e.installment_amount||!payment){
  const computed=calculateInstallments(principal,count,0,rate);
  if(computed){payment=computed[0].amount;e.installment_amount.value=moneyText(payment)}
 }
 const parts=calculateInstallments(principal,count,payment,rate),preview=document.querySelector('#installmentPreview');
 e.installment_amount.setCustomValidity(parts?'':'Revise o valor, a quantidade e a taxa: as parcelas precisam reduzir a dívida em até 120 meses.');
 if(!parts){preview.textContent='Informe valor, taxa mensal e parcelas válidas. A parcela deve cobrir os juros e reduzir a dívida.';return}
 if(!e.first_charge_date.value){preview.textContent='Informe a data da primeira cobrança para estimar a antecipação.';return}
 const total=parts.reduce((sum,p)=>sum+p.amount,0),last=parts.at(-1).amount;
 const firstDate=new Date(e.first_charge_date.value+'T00:00:00'),today=new Date();today.setHours(0,0,0,0);
 const discount=(p,i)=>{const due=new Date(firstDate),day=due.getDate();due.setDate(1);due.setMonth(due.getMonth()+i);const lastDay=new Date(due.getFullYear(),due.getMonth()+1,0).getDate();due.setDate(Math.min(day,lastDay));return p.amount/Math.pow(1+rate,Math.max(0,(due-today)/86400000/30.4375))};
 const discountedLast=discount(parts.at(-1),count-1),settlement=parts.reduce((sum,p,i)=>sum+discount(p,i),0);
 preview.innerHTML=`<strong>${count-1}× ${brl(payment)} e última de ${brl(last)}</strong><span>Total com juros: ${brl(total)} · Juros: ${brl(total-principal)}</span><span>Primeira parcela: ${brl(parts[0].amortization)} reduz a dívida e ${brl(parts[0].interest)} paga juros.</span><span>Para antecipar a última parcela hoje: <b>${brl(discountedLast)}</b> · Economia estimada: ${brl(last-discountedLast)}</span><span>Para quitar todas hoje: <b>${brl(settlement)}</b></span><small>Estimativa com parcelas mensais fixas (Tabela Price), desconto pelo prazo até as datas previstas, sem tarifas ou seguros. Confira o valor de quitação com o credor.</small>`;
}
['payment','financing_kind','installment','amount','installment_count','installment_amount','interest_rate','first_charge_date','scheduled'].forEach(name=>financeForm.elements[name].addEventListener('input',updateCreditOptions));
financeForm.elements.date.addEventListener('change',()=>{if(!financeForm.elements.first_charge_date.value)financeForm.elements.first_charge_date.value=financeForm.elements.date.value});
function expensePayload(){
 const payload=Object.fromEntries(new FormData(financeForm));
 payload.amount=moneyValue(payload.amount);
 if(payload.installment_amount)payload.installment_amount=moneyValue(payload.installment_amount);
 const enabled=!document.querySelector('#installmentFields').hidden;
 payload.installment=enabled;payload.scheduled=financeForm.elements.scheduled.checked&&!financeForm.elements.scheduled.disabled;
 return payload;
}
function renderDebtEstimates(){
 const container=document.querySelector('#debtEstimates');if(!container)return;
 const groups=new Map(),today=new Date();today.setHours(0,0,0,0);
 DATA.filter(x=>x.installment_group&&new Date(x.date+'T00:00:00')>=today).forEach(item=>{if(!groups.has(item.installment_group))groups.set(item.installment_group,[]);groups.get(item.installment_group).push(item)});
 container.innerHTML=[...groups.values()].map(items=>{
  items.sort((a,b)=>a.date.localeCompare(b.date));const first=items[0],last=items.at(-1),rate=Number(first.finance?.interest_rate||0)/100;
  const presentValue=item=>item.amount/Math.pow(1+rate,Math.max(0,(new Date(item.date+'T00:00:00')-today)/86400000/30.4375));
  const total=items.reduce((s,x)=>s+x.amount,0),settlement=items.reduce((s,x)=>s+presentValue(x),0);
  return `<div class="debt-estimate"><strong>${esc(first.where)} · ${items.length} parcela(s) futura(s)</strong><span>Taxa: ${(rate*100).toLocaleString('pt-BR')}% ao mês · Total previsto: ${brl(total)}</span><span>Antecipar a última: <b>${brl(presentValue(last))}</b> · Quitar as futuras: <b>${brl(settlement)}</b></span><small>Economia estimada: ${brl(total-settlement)}. Desconto proporcional ao prazo, sem tarifas; confirme com o credor. Não inclui parcelas vencidas.</small></div>`;
 }).join('');
}
