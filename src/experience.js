let experienceBills=[],experienceBillsSequence=0;
function renderExperience(){
 const basis=trustInsights?.month===month.value?trustInsights:null,visual=document.querySelector('#homeFlowVisual');
 if(basis){
  const received=basis.accumulated_income,spent=basis.accumulated_expenses,available=basis.accumulated_balance,expected=basis.income.expected,out=basis.projected_expenses,maximum=Math.max(expected,out,1);
  visual.innerHTML=`<div class="glance-metrics"><article class="glance-money"><span class="glance-icon" aria-hidden="true">↙</span><small>Saldo acumulado</small><strong class="${available<0?'negative':''}">${brl(available)}</strong><span>Inclui meses anteriores</span></article><article class="glance-in"><span class="glance-icon" aria-hidden="true">↓</span><small>Já entrou</small><strong>${brl(received)}</strong><span>Acumulado até este mês</span></article><article class="glance-out"><span class="glance-icon" aria-hidden="true">↑</span><small>Já saiu</small><strong>${brl(spent)}</strong><span>Acumulado até este mês</span></article><article class="glance-due"><span class="glance-icon" aria-hidden="true">◷</span><small>Falta pagar</small><strong id="glanceDue">—</strong><span id="glanceDueCount">Conferindo contas e faturas…</span></article></div><div class="glance-plan"><div><span>Previsão ao fim do mês</span><strong class="${basis.projected_balance_with_carry<0?'negative':'positive'}">${brl(basis.projected_balance_with_carry)}</strong></div><div class="glance-bars"><div><span>Ganhos previstos <b>${brl(expected)}</b></span><div class="ex-flow-track"><i style="width:${Math.min(100,Math.max(0,expected)/maximum*100)}%"></i></div></div><div class="is-out"><span>Saídas previstas <b>${brl(out)}</b></span><div class="ex-flow-track"><i style="width:${Math.min(100,Math.max(0,out)/maximum*100)}%"></i></div></div></div></div>`;
 }else visual.innerHTML='<p class="ex-subtle">Carregando o resumo do mês…</p>';

 renderOverviewNumbers();
}
function renderOverviewNumbers(){
 const period=month.value,rows=DATA.filter(e=>e.date.startsWith(period)),fixed=rows.filter(e=>e.finance?.fixed_expense_id);
 const paid=fixed.filter(e=>e.finance.paid).reduce((sum,e)=>sum+e.amount,0),pending=fixed.filter(e=>!e.finance.paid).reduce((sum,e)=>sum+e.amount,0),total=paid+pending;
 const cashDue=rows.filter(e=>e.payment!=='Voucher'&&!e.finance?.paid&&(e.finance?.fixed_expense_id||e.finance?.debt_entry));
 const bills=experienceBills.filter(b=>b.month===period&&b.remaining>0),due=cashDue.reduce((sum,e)=>sum+e.amount,0)+bills.reduce((sum,b)=>sum+b.remaining,0);
 const dueEl=document.querySelector('#glanceDue');if(dueEl){dueEl.textContent=brl(due);document.querySelector('#glanceDueCount').textContent=(cashDue.length+bills.length)+' contas em aberto · dinheiro e cartão'}
 document.querySelector('#homeFixedVisual').innerHTML=`<div class="overview-fixed-total"><small>Total de gastos fixos</small><strong>${brl(total)}</strong><span>${fixed.length} contas no mês · inclui voucher</span></div><div class="overview-fixed-bar" role="img" aria-label="${esc('Fixos pagos: '+brl(paid)+'. Em aberto: '+brl(pending))}"><span style="width:${total?paid/total*100:0}%"></span></div><div class="overview-fixed-legend"><div><small>Pagos</small><strong>${brl(paid)}</strong></div><div><small>Em aberto</small><strong>${brl(pending)}</strong></div></div>`;
 const summary=portfolio.summary||{};
 document.querySelector('#homeInvestmentNumbers').innerHTML=`<div><small>Investimentos + caixa</small><strong>${brl(summary.total_with_cash||0)}</strong></div><div><small>Resultado da carteira</small><strong class="${(summary.profit_loss||0)<0?'negative':'positive'}">${brl(summary.profit_loss||0)}</strong></div>`;
}
async function refreshExperienceBills(){if(!canWrite)return;const sequence=++experienceBillsSequence,period=month.value;try{const data=await trustRequest('/api/cards?month='+period);if(sequence!==experienceBillsSequence||period!==month.value)return;experienceBills=data.invoices;renderOverviewNumbers()}catch{const note=document.querySelector('#glanceDueCount');if(note)note.textContent='Faturas indisponíveis · total parcial'}}
document.addEventListener('finance-updated',()=>{renderExperience();refreshExperienceBills()});
document.addEventListener('insights-updated',renderExperience);
month.addEventListener('change',()=>{experienceBills=[];renderExperience();refreshExperienceBills()});
document.querySelector('.home-summary').hidden=true;
document.body.classList.add('has-daily-workspace');
