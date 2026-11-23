// Cartões: one block per card with its invoice, spending goal, monthly installment cap and limit.
// Everything is derived from the card purchases, payments and refunds already kept in the account.
const CARD_COLORS=['#5aa9ff','#a98bff','#3ddc97','#f5b94a','#f78fb3','#2dd4bf'];
const cardShift=(key,delta)=>{const [y,m]=key.split('-').map(Number),d=new Date(y,m-1+delta,1);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`};
const cardDue=(key,day)=>{const [y,m]=key.split('-').map(Number),last=new Date(y,m,0).getDate();return `${key}-${String(Math.min(day,last)).padStart(2,'0')}`};
const cardMonthShort=key=>{const [y,m]=key.split('-').map(Number);return new Date(y,m-1,1).toLocaleDateString('pt-BR',{month:'short'}).replace('.','')};
const cardMonthLong=key=>{const [y,m]=key.split('-').map(Number);return new Date(y,m-1,1).toLocaleDateString('pt-BR',{month:'long'})};

// Same split as cards.parts on the server: equal cents, remainder on the last installment.
function cardPurchaseParts(purchase){
  const total=Math.round(purchase.amount*100),count=purchase.installments,regular=Math.floor(total/count);
  return [...Array(count)].map((_,index)=>{const key=cardShift(purchase.first_invoice_month,index);
    return {number:index+1,month:key,date:cardDue(key,purchase.due_day),amount:(index<count-1?regular:total-regular*(count-1))/100,installments:count}});
}
// {cardId: {month: {total, installments, paid, refunds}}}
function cardLedger(){
  const prefs=ACCOUNT_PREFERENCES||{},ledger={};
  const slot=(card,key)=>((ledger[card]??={})[key]??={total:0,installments:0,paid:0,refunds:0,count:0});
  (prefs.card_purchases||[]).forEach(purchase=>cardPurchaseParts(purchase).forEach(part=>{const entry=slot(purchase.card_id,part.date.slice(0,7));entry.total+=part.amount;entry.count++;if(part.installments>1)entry.installments+=part.amount}));
  (prefs.card_payments||[]).filter(item=>!item.reversed).forEach(item=>{const [card,key]=item.invoice_key.split(':');slot(card,key).paid+=item.amount});
  (prefs.card_refunds||[]).filter(item=>!item.reversed).forEach(item=>{const [card,key]=item.invoice_key.split(':');slot(card,key).refunds+=item.amount});
  return ledger;
}
function cardBill(ledger,card,key){const entry=ledger[card]?.[key]||{total:0,installments:0,paid:0,refunds:0,count:0},total=Math.max(0,entry.total-entry.refunds);return {...entry,total,remaining:Math.max(0,total-entry.paid)}}
function cardCommitted(ledger,card){return Object.keys(ledger[card]||{}).reduce((sum,key)=>sum+cardBill(ledger,card,key).remaining,0)}

function cardMeter(label,value,target,emptyText){
  if(!target)return `<div class="card-meter is-unset"><div><span>${label}</span><b>${brl(value)}</b></div><small>${emptyText}</small></div>`;
  const ratio=value/target,level=ratio>1?'over':ratio>=.8?'warn':'ok';
  return `<div class="card-meter is-${level}"><div><span>${label}</span><b>${brl(value)} <em>de ${brl(target)}</em></b></div><div class="card-meter-track"><i style="width:${Math.min(100,ratio*100)}%"></i></div><small>${ratio>1?`${brl(value-target)} acima`:`${brl(target-value)} livres`} · ${Math.round(ratio*100)}%</small></div>`;
}
function cardInstallmentBars(ledger,card,start){
  const keys=[...Array(6)].map((_,i)=>cardShift(start,i)),values=keys.map(key=>cardBill(ledger,card.id,key).installments),cap=+card.installment_cap||0;
  const max=Math.max(cap,...values,1)*1.12,W=300,H=96,P=16,slot=(W-8)/keys.length,bw=Math.min(26,slot*.55),y=v=>H-P-(v/max)*(H-P-12);
  const bars=values.map((value,i)=>{const x=4+slot*i+slot/2,over=cap&&value>cap;return `<rect x="${x-bw/2}" y="${y(value)}" width="${bw}" height="${Math.max(0,y(0)-y(value))}" rx="3" class="${over?'is-over':''}"><title>${cardMonthLong(keys[i])}: ${brl(value)} em parcelas</title></rect><text x="${x}" y="${H-3}" text-anchor="middle">${cardMonthShort(keys[i])}</text>`}).join('');
  const capLine=cap?`<line x1="2" x2="${W-2}" y1="${y(cap)}" y2="${y(cap)}" class="card-cap"/><text x="${W-4}" y="${y(cap)-4}" text-anchor="end" class="card-cap-label">teto ${brl(cap)}</text>`:'';
  return `<svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Parcelas de ${esc(card.name)} nos próximos seis meses">${capLine}${bars}</svg>`;
}

// In the current month each card shows its open invoice: once this month's due date has
// passed, that is next month's. Other months show the invoice that is due in them.
function cardFocusMonth(card,key){const today=localDateValue();return key===today.slice(0,7)&&cardDue(key,card.due_day)<today?cardShift(key,1):key}
function renderCardsOverview(){
  const grid=document.querySelector('#cardsGrid');if(!grid)return;
  const cards=ACCOUNT_PREFERENCES?.credit_cards||[],selected=month.value,current=selected===localDateValue().slice(0,7),ledger=cardLedger();
  const bills=cards.map(card=>cardBill(ledger,card.id,cardFocusMonth(card,selected))),totals={bill:bills.reduce((s,b)=>s+b.total,0),open:bills.reduce((s,b)=>s+b.remaining,0),installments:bills.reduce((s,b)=>s+b.installments,0)};
  const future=cards.reduce((sum,card)=>{const focus=cardFocusMonth(card,selected);return sum+Object.keys(ledger[card.id]||{}).filter(k=>k>focus).reduce((s,k)=>s+cardBill(ledger,card.id,k).remaining,0)},0);
  const key=selected;
  // The invoice list below follows the earliest open invoice shown in the cards.
  const billMonth=document.querySelector('#cardBillMonth'),focusMonths=cards.map(card=>cardFocusMonth(card,selected)).sort(),wanted=focusMonths[0]||selected;
  if(billMonth&&billMonth.value!==wanted&&!billMonth.dataset.touched){billMonth.value=wanted;if(typeof refreshCardBills==='function')refreshCardBills()}
  const limits=cards.filter(card=>card.limit!=null),available=limits.reduce((sum,card)=>sum+(card.limit-cardCommitted(ledger,card.id)),0);
  document.querySelector('#cardsKpis').innerHTML=[
    [current?'Faturas abertas':'Faturas de '+cardMonthLong(key),brl(totals.bill),totals.open?`${brl(totals.open)} a pagar`:totals.bill?'tudo pago':'sem compras'],
    ['Parcelas nessas faturas',brl(totals.installments),'soma das compras parceladas'],
    ['Faturas seguintes',brl(future),'já comprometido em parcelas'],
    ['Limite disponível',limits.length?brl(available):'—',limits.length?`em ${limits.length} ${limits.length===1?'cartão':'cartões'} com limite`:'informe o limite no cadastro']
  ].map(([label,value,note])=>`<div><small>${label}</small><strong>${value}</strong><span>${note}</span></div>`).join('');
  if(!cards.length){grid.innerHTML='<div class="cards-empty"><strong>Nenhum cartão ainda.</strong><span>Cadastre seus cartões com fechamento e vencimento. Depois, ao lançar um gasto no crédito, escolha o cartão e ele aparece aqui.</span><button class="save" type="button" data-cards-add>＋ Cadastrar primeiro cartão</button></div>';return}
  grid.innerHTML=cards.map((card,index)=>{
    const focus=cardFocusMonth(card,selected),bill=bills[index],committed=cardCommitted(ledger,card.id),color=CARD_COLORS[index%CARD_COLORS.length];
    const due=cardDue(focus,card.due_day),status=!bill.total?'Sem compras':bill.remaining===0?'Paga':due<localDateValue()?'Vencida':'Em aberto';
    return `<article class="card-tile" style="--card-color:${color}">
      <div class="card-face"><div><strong>${esc(card.name)}</strong><small>Fecha dia ${card.closing_day||'—'} · vence dia ${card.due_day}</small></div><span class="card-status is-${status==='Vencida'?'bad':status==='Paga'?'good':'idle'}">${status}</span></div>
      <div class="card-bill"><small>${focus!==selected?'Fatura atual · ':'Fatura de '}${cardMonthLong(focus)}</small><strong>${brl(bill.total)}</strong><span>${bill.count} ${bill.count===1?'lançamento':'lançamentos'} · vence ${date(due)}${bill.paid?` · pago ${brl(bill.paid)}`:''}</span></div>
      ${cardMeter('Meta de gasto',bill.total,+card.spending_goal||0,'Sem meta. Defina quanto quer gastar por fatura.')}
      ${cardMeter('Parcelas no mês',bill.installments,+card.installment_cap||0,'Sem teto. Defina até quanto aceita em parcelas.')}
      ${card.limit!=null?cardMeter('Limite usado',committed,+card.limit,''):''}
      <div class="card-chart"><span>Parcelas nos próximos 6 meses</span>${cardInstallmentBars(ledger,card,focus)}</div>
      <div class="card-actions"><button class="secondary" type="button" data-cards-edit="${card.id}">Editar cartão e metas</button><button class="secondary" type="button" data-cards-bill>Ver fatura</button></div>
    </article>`}).join('');
}

function openCardEditor(id){
  const editor=document.querySelector('#cardEditor');editor.open=true;
  if(id){document.querySelector(`#creditCardList [data-edit-card="${CSS.escape(id)}"]`)?.click()}
  else{creditCardForm.reset();creditCardForm.elements.id.value='';document.querySelector('#cancelCreditCardEdit').hidden=true}
  editor.scrollIntoView({behavior:'smooth',block:'start'});setTimeout(()=>creditCardForm.elements.name.focus({preventScroll:true}),300);
}
document.querySelector('#cardsPanel').addEventListener('click',event=>{
  if(event.target.closest('#cardsAddCard,[data-cards-add]'))openCardEditor();
  const edit=event.target.closest('[data-cards-edit]');if(edit)openCardEditor(edit.dataset.cardsEdit);
  if(event.target.closest('[data-cards-bill]'))document.querySelector('.card-bills').scrollIntoView({behavior:'smooth',block:'start'});
  if(event.target.closest('#cardsNewPurchase'))document.querySelector('#newCardPurchase').click();
});

// Registrar: pick the card and see how the purchase fits its goal and installment cap.
function cardMoney(value){const text=String(value||'').trim();if(!text)return 0;return +(text.includes(',')?text.replace(/\./g,'').replace(',','.'):text)||0}
function updateExpenseCardHint(){
  const field=document.querySelector('#expenseCardField'),hint=document.querySelector('#expenseCardHint');if(!field||!hint)return;
  const e=form.elements,credit=e.payment.value==='Crédito',cards=ACCOUNT_PREFERENCES?.credit_cards||[],usable=cards.filter(card=>card.closing_day);
  if(credit&&!editingExpenseId&&!usable.length){field.hidden=false;hint.innerHTML=cards.length?'Informe o dia de fechamento do cartão na aba Cartões para vincular compras.':'Cadastre seus cartões na aba Cartões para separar os gastos de cada um.';hint.className='card-hint';return}
  if(credit&&!editingExpenseId&&usable.length===1&&!e.credit_card_id.value&&!e.credit_card_id.dataset.touched)e.credit_card_id.value=usable[0].id;
  const card=usable.find(item=>item.id===e.credit_card_id.value);
  if(field.hidden||!card){hint.textContent='';hint.className='card-hint';return}
  const total=cardMoney(e.amount.value),count=e.installment?.value==='true'?Math.max(1,+e.installment_count.value||1):1,day=e.date.value||localDateValue();
  const first=cardFirstMonth(card,day)||day.slice(0,7),part=total/count,ledger=cardLedger(),messages=[];let warn=false;
  messages.push(`Entra na fatura de ${cardMonthLong(first)}${count>1?` em ${count}x de ${brl(part)}`:''}.`);
  if(total&&card.spending_goal){const after=cardBill(ledger,card.id,first).total+part;warn||=after>card.spending_goal;messages.push(`Fatura de ${cardMonthLong(first)}: ${brl(after)} de ${brl(card.spending_goal)} da meta.`)}
  if(total&&count>1&&card.installment_cap){
    const peak=[...Array(count)].map((_,i)=>{const key=cardShift(first,i);return {key,value:cardBill(ledger,card.id,key).installments+part}}).sort((a,b)=>b.value-a.value)[0];
    warn||=peak.value>card.installment_cap;
    messages.push(peak.value>card.installment_cap?`Com esta compra, as parcelas chegam a ${brl(peak.value)} em ${cardMonthLong(peak.key)}, acima do teto de ${brl(card.installment_cap)}.`:`Parcelas no mês mais cheio: ${brl(peak.value)} de ${brl(card.installment_cap)}.`);
  }
  hint.textContent=messages.join(' ');hint.className='card-hint'+(warn?' is-warn':'');
}
(function(){
  const field=document.querySelector('#expenseCardField');if(!field)return;
  field.firstChild.textContent='Qual cartão?';
  field.querySelector('small').outerHTML='<small id="expenseCardHint" class="card-hint" aria-live="polite"></small>';
  const select=form.elements.credit_card_id;select.addEventListener('change',()=>{select.dataset.touched='1'});
  ['input','change'].forEach(type=>form.addEventListener(type,()=>queueMicrotask(updateExpenseCardHint)));
  form.addEventListener('reset',()=>{delete select.dataset.touched;setTimeout(updateExpenseCardHint,0)});
  updateExpenseCardHint();
})();

['finance-updated','bootstrap-loaded'].forEach(name=>document.addEventListener(name,()=>queueMicrotask(()=>{renderCardsOverview();updateExpenseCardHint()})));
month.addEventListener('change',()=>{const input=document.querySelector('#cardBillMonth');if(input)delete input.dataset.touched;renderCardsOverview()});
document.querySelector('#cardBillMonth')?.addEventListener('change',event=>{event.target.dataset.touched='1'});
if(typeof renderRecurring==='function'){const baseRecurring=renderRecurring;renderRecurring=function(...args){const result=baseRecurring.apply(this,args);renderCardsOverview();return result}}
renderCardsOverview();
