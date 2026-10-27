"""Gera a interface web usando os dados do banco local."""

import json
import os
from pathlib import Path

try:
    from src.investments import portfolio
    from src import runtime_storage as storage
except ImportError:
    from investments import portfolio
    import runtime_storage as storage


ROOT = Path(__file__).resolve().parents[1]
OUTPUT = ROOT / "templates/index.html"
CATEGORIES = [
    "Alimentação", "Mercado", "Transporte", "Moradia", "Saúde", "Educação",
    "Lazer", "Compras", "Assinaturas", "Contas", "Viagem", "Presentes", "Outros",
]


def read_expenses() -> list[dict]:
    return storage.read_expenses()


def read_incomes() -> tuple[dict[str, float], dict[str, float], dict]:
    data = storage.read_incomes()
    cash = {month: values["cash"] for month, values in data.items()}
    voucher = {month: values["voucher"] for month, values in data.items()}
    return cash, voucher, data


def read_budgets() -> dict[str, dict[str, float]]:
    return storage.read_budgets()


expenses = read_expenses()
months = sorted({item["date"][:7] for item in expenses}, reverse=True)

initial_income, initial_voucher, initial_income_details = read_incomes()
initial_income_entries = storage.read_income_entries()
initial_budgets = read_budgets()
initial_investments = portfolio()
if os.environ.get("SANITIZE_BUILD") == "1":
    expenses, months, initial_income, initial_voucher, initial_income_details, initial_income_entries, initial_budgets = [], [], {}, {}, {}, [], {}
    initial_investments = {"investments": [], "history": [], "updated_at": None, "summary": {"amount_applied": 0, "current_value": 0, "profit_loss": 0, "return_percent": 0}}

template = r'''<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
  <meta name="color-scheme" content="light">
  <meta name="theme-color" content="#080a0c">
  <meta name="apple-mobile-web-app-capable" content="yes">
  <meta name="apple-mobile-web-app-status-bar-style" content="default">
  <meta name="apple-mobile-web-app-title" content="Minha Carteira">
  <link rel="manifest" href="/manifest.webmanifest">
  <link rel="icon" href="/icons/icon-192.png">
  <link rel="apple-touch-icon" href="/icons/apple-touch-icon.png">
  <title>Minha Carteira</title>
  <style>/* Component layouts are assembled below. */</style>
  <link rel="stylesheet" href="/app.css?v=16">
</head>
<body><a class="skip-link" href="#mainContent">Ir para o conteúdo</a><div class="ambient ambient-one" aria-hidden="true"></div><div class="ambient ambient-two" aria-hidden="true"></div><div id="offlineNotice" class="offline-notice" hidden>Você está sem conexão. Consultas e alterações ficam disponíveis quando o servidor voltar.</div><main id="mainContent" class="shell">
  <header class="top"><div class="brand"><img class="mark" src="/icons/icon-192.png" alt=""><div><span class="brand-kicker">FINANÇAS PESSOAIS</span><h1>Minha Carteira</h1></div></div><div class="top-context"><span id="welcomeMessage">Resumo financeiro</span><strong id="todayLabel"></strong></div><div class="top-actions"><span class="online-chip"><i></i> Online</span><div id="userBadge" class="user-badge" hidden></div><button id="installApp" class="install-button" type="button" hidden>Instalar app</button><form class="logout" method="post" action="/logout"><button type="submit" aria-label="Sair da conta">Sair <svg aria-hidden="true" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"><path d="M9 5H5v14h4M10 12h11M17 8l4 4-4 4"/></svg></button></form></div></header>
  <nav class="tabs" aria-label="Navegação principal"><button class="tab active" data-panel="dashboardPanel"><span class="tab-icon" aria-hidden="true">⌁</span><span>Visão geral</span></button><button class="tab" data-panel="entryPanel"><span class="tab-icon" aria-hidden="true">＋</span><span>Lançar</span></button></nav>
  <div class="sidebar-note"><strong>Um passo de cada vez.</strong>Organize o presente.<br>Construa seu próximo capítulo.</div>
  <div id="dashboardPanel" class="panel" role="region" aria-label="Visão geral">
    <div class="dashboard-heading"><div class="hero-copy"><span class="eyebrow">Seu panorama financeiro</span><h2>Seu dinheiro, com clareza.</h2><p>Veja o que entrou, o que saiu e o que você pode planejar.</p><div class="hero-actions"><button class="hero-primary" type="button" data-open-panel="entryPanel"><span>＋</span> Registrar gasto</button><button type="button" data-open-panel="budgetsPanel">Planejar limites <span>→</span></button><button type="button" data-open-panel="investmentsPanel">Ver investimentos <span>→</span></button></div></div><div class="period-control"><span>Explore seu mês</span><div id="filters" class="controls"><select id="month" class="field month" aria-label="Mês"></select><select id="category" class="field" aria-label="Categoria"><option value="">Todas</option></select></div></div></div>
    <div id="storageStatus" class="storage-status">Verificando conexão com o aplicativo...</div>
    <section class="money-overview">
      <div class="available-balance"><span class="eyebrow">Disponível agora</span><strong id="balance">—</strong><small>Seu saldo depois dos gastos do mês</small><div class="balance-context"><span>Total gasto no mês</span><b id="totalSpent">—</b></div></div>
      <div class="money-lanes"><div class="money-lane salary-lane"><div class="lane-heading"><span>Salário e dinheiro</span><b>Conta principal</b></div><div><span><small>Recebido</small><strong id="income">—</strong></span><span><small>Gasto</small><strong id="spent">—</strong></span><span><small>Lançamentos</small><strong id="count">—</strong></span></div></div><div class="money-lane voucher-lane"><div class="lane-heading"><span>Voucher</span><b>Saldo separado</b></div><div><span><small>Crédito</small><strong id="voucherIncome">—</strong></span><span><small>Usado</small><strong id="voucherSpent">—</strong></span><span><small>Disponível</small><strong id="voucherBalance">—</strong><em id="voucherCount">—</em></span></div></div></div>
    </section>
    <section class="dashboard-visuals">
      <div class="limit-overview"><div class="detail-heading"><div><h3>Limites do mês</h3></div><button class="text-button" type="button" data-open-panel="budgetsPanel">Ajustar limites</button></div><div class="limit-hero"><strong id="budgetRemainingSummary">—</strong><span>disponíveis nos limites definidos</span></div><div class="limit-summary"><span><small>Limite total</small><b id="budgetTotalSummary">—</b></span><span><small>Utilizado</small><b id="budgetUsedSummary">—</b></span><span><small>Situação</small><b id="budgetRiskSummary">—</b></span></div><div id="budgetAlerts" class="alerts"></div><div id="budgetList" class="budget-list"></div></div>
      <div class="spending-chart"><div class="detail-heading"><div><h3>Gastos por categoria</h3></div><b id="monthComparison">—</b></div><div class="ring-wrap"><div id="ring" class="ring"><div class="ring-center"><strong id="ringTotal">—</strong><span class="sub">gastos</span></div></div><div id="legend" class="legend"></div></div></div>
    </section>
    <div class="dashboard-details">
      <details class="focus-panel"><summary><div><span class="eyebrow">Detalhes financeiros</span><strong>Renda, voucher e parcelas futuras</strong></div><span class="summary-toggle" aria-hidden="true"></span></summary><div class="focus-content"><div class="focus-content-inner"><section class="finance-details"><div class="detail-heading"><h3>Ajustar renda do mês</h3></div><div class="income-form"><label>Renda em dinheiro<div class="money-input"><span>R$</span><input id="incomeInput" type="number" min="0" step="0.01"></div></label><label>Dia de recebimento<input id="paydayInput" type="number" min="1" max="31" placeholder="Dia"></label><label class="source-field">Origem da renda<input id="incomeSourceInput" maxlength="100" placeholder="Empresa ou pagador"></label><label>Crédito do voucher<div class="money-input"><span>R$</span><input id="voucherInput" type="number" min="0" step="0.01"></div></label></div><div class="income-actions"><button id="saveIncomeButton" class="save" type="button">Salvar renda</button><div id="incomeMessage" class="message" hidden></div></div></section><div class="detail-columns"><section class="flow-section"><div class="section-title"><h3>Entradas identificadas</h3><strong id="incomeEntriesTotal">R$ 0,00</strong></div><div id="incomeEntryBars" class="bars"></div></section><section class="flow-section"><div class="section-title"><h3>Próximas parcelas</h3><span>Compromissos previstos</span></div><div id="upcomingInstallments" class="upcoming-list"></div><div id="debtEstimates" class="debt-estimates"></div></section></div></div></div></details>
      <details class="focus-panel"><summary><div><span class="eyebrow">Movimentações</span><strong>Categorias e lista de gastos</strong></div><span class="summary-toggle" aria-hidden="true"></span></summary><div class="focus-content"><div class="focus-content-inner"><div class="detail-columns"><section class="flow-section"><div class="section-title"><h3>Gastos em dinheiro</h3></div><div id="bars" class="bars"></div></section><section class="flow-section"><div class="section-title"><h3>Uso do voucher</h3></div><div id="voucherBars" class="bars"></div></section></div><section class="table-card"><div class="table-head"><div><span class="eyebrow">Movimentações</span><h3>Histórico de gastos</h3></div><input id="search" class="field search" placeholder="Buscar gasto..."></div><div class="scroll"><table><thead><tr><th>Data</th><th>Onde</th><th>Categoria</th><th>Pagamento</th><th>Descrição</th><th style="text-align:right">Valor</th><th>Ações</th></tr></thead><tbody id="rows"></tbody></table><div id="empty" class="empty" hidden>Nenhum gasto encontrado.</div></div></section></div></div></details>
    </div>
  </div>
  <div id="entryPanel" class="panel" role="region" aria-label="Lançamentos" hidden><header class="section-heading entry-heading"><div><span class="eyebrow">Movimentações</span><h2>Cada movimento conta.</h2><p>Registre seus gastos ou traga seu extrato para cá.</p></div><div class="entry-switcher" role="tablist" aria-label="Forma de lançamento"><button class="active" type="button" role="tab" aria-selected="true" data-entry-view="manual">Manual</button><button type="button" role="tab" aria-selected="false" data-entry-view="statement"><span>⇧</span> Importar extrato</button></div></header><section class="card entry" data-entry-content="manual"><span class="eyebrow">Lançamento manual</span><h2>Novo gasto</h2><form id="expenseForm" class="entry-grid">
    <label>Data<input name="date" type="date" required></label><label><span id="expenseAmountLabel">Valor (R$)</span><input name="amount" type="text" inputmode="decimal" data-money placeholder="0,00" maxlength="18" required><small>Digite os centavos: 12345 vira 123,45.</small></label>
    <label class="wide">Onde foi gasto<input name="where" maxlength="100" placeholder="Ex.: Posto, mercado, restaurante" required></label>
    <label>Categoria<select name="category" required><option>Alimentação</option><option>Mercado</option><option>Transporte</option><option>Moradia</option><option>Saúde</option><option>Educação</option><option>Lazer</option><option>Compras</option><option>Assinaturas</option><option>Contas</option><option>Viagem</option><option>Presentes</option><option>Outros</option></select></label>
    <label>Pagamento<select name="payment" required><option>Pix</option><option>Crédito</option><option>Débito</option><option>Dinheiro</option><option>Transferência</option><option>Voucher</option><option>Não informado</option></select></label>
    <div class="wide debt-entry-link"><input type="hidden" name="financing_kind" value="purchase"><span>Empréstimo ou financiamento?</span> <button class="text-button" type="button" data-open-panel="debtsPanel">Abrir Dívidas →</button></div>
    <div id="scheduleOptions" class="wide" hidden><label class="schedule-toggle"><input name="scheduled" type="checkbox" value="true"> Agendar Pix ou transferência</label><label id="scheduleDateField" hidden>Data prevista<input name="scheduled_date" type="date"></label><small>Registra um compromisso futuro no app. O pagamento deve ser agendado no seu banco.</small></div>
    <div id="creditOptions" class="credit-options wide" hidden><label>Pagamento parcelado?<select name="installment"><option value="false">Não</option><option value="true">Sim</option></select></label><div id="installmentFields" class="installment-fields" hidden><label>Quantidade<input name="installment_count" type="number" min="2" max="120" value="2"></label><label>Valor de cada parcela<input name="installment_amount" type="text" inputmode="decimal" data-money placeholder="0,00" maxlength="18"></label><label>Juros por mês (%)<input name="interest_rate" type="text" inputmode="decimal" value="0" pattern="[0-9]+([.,][0-9]+)?" maxlength="10"></label><label>Primeira cobrança<input name="first_charge_date" type="date"></label><div id="installmentPreview" class="installment-preview" aria-live="polite"></div></div></div>
    <label class="wide">Descrição<input name="description" maxlength="200" placeholder="Opcional"></label><button class="save" type="submit">Salvar gasto</button><div id="formMessage" class="message" hidden></div>
  </form></section></div>
  <div class="foot">Seus dados financeiros são privados e separados por conta</div>
  <div id="updateBanner" class="update-banner" hidden><span>Uma nova versão do aplicativo está pronta.</span><button id="applyUpdate" type="button">Atualizar</button></div>
</main><script>
let DATA=__DATA__;
const DEFAULT_INCOME=__INCOME__;
const DEFAULT_VOUCHER=__VOUCHER__;
const INCOME_DETAILS=__INCOME_DETAILS__;
let INCOME_ENTRIES=__INCOME_ENTRIES__;
const BUDGETS=__BUDGETS__;
let ALL_CATEGORIES=__CATEGORIES__;
const COLORS=['#8de0b4','#a7bce8','#bba9e9','#e49aa6','#e9c47c','#80c2cd','#a3adcf','#9bc7b4','#c4a4c7','#9faebf'];
const brl=v=>v.toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const date=v=>new Date(v+'T12:00:00').toLocaleDateString('pt-BR');
const esc=value=>String(value??'').replace(/[&<>'"]/g,char=>({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char]));
const monthLabel=v=>{const [y,m]=v.split('-');return new Date(+y,+m-1,1).toLocaleDateString('pt-BR',{month:'long',year:'numeric'}).replace(/^./,x=>x.toUpperCase())};
const previousMonth=v=>{const [y,m]=v.split('-').map(Number),d=new Date(y,m-2,1);return `${d.getFullYear()}-${String(d.getMonth()+1).padStart(2,'0')}`};
const incomeByMonth={...DEFAULT_INCOME},incomeDetails={...INCOME_DETAILS};
const voucherByMonth={...DEFAULT_VOUCHER};
let canWrite=false;
const month=document.querySelector('#month'),category=document.querySelector('#category'),search=document.querySelector('#search'),incomeInput=document.querySelector('#incomeInput'),voucherInput=document.querySelector('#voucherInput'),paydayInput=document.querySelector('#paydayInput'),incomeSourceInput=document.querySelector('#incomeSourceInput');
function populateFilters(){const selected=month.value;month.innerHTML='';const months=[...new Set([...DATA.map(x=>x.date.slice(0,7)),...Object.keys(BUDGETS),new Date().toISOString().slice(0,7)])].sort().reverse();months.forEach(m=>month.add(new Option(monthLabel(m),m)));if(months.includes(selected))month.value=selected;category.innerHTML='<option value="">Todas</option>';ALL_CATEGORIES.slice().sort((a,b)=>a.localeCompare(b,'pt-BR')).forEach(c=>category.add(new Option(c,c)))}populateFilters();
function filtered(){const q=search.value.trim().toLocaleLowerCase('pt-BR');return DATA.filter(x=>x.date.startsWith(month.value)&&(!category.value||x.category===category.value)&&(!q||Object.values(x).join(' ').toLocaleLowerCase('pt-BR').includes(q)))}
function render(){const all=DATA.filter(x=>x.date.startsWith(month.value));const cash=all.filter(x=>x.payment!=='Voucher'),voucher=all.filter(x=>x.payment==='Voucher');const view=filtered();const spent=cash.reduce((s,x)=>s+x.amount,0),voucherSpent=voucher.reduce((s,x)=>s+x.amount,0);const income=+(incomeByMonth[month.value]||0),voucherIncome=+(voucherByMonth[month.value]||0);const balance=income-spent,voucherBalance=voucherIncome-voucherSpent;
 const currentSpent=spent+voucherSpent;document.querySelector('#totalSpent').textContent=brl(currentSpent);document.querySelector('#income').textContent=brl(income);incomeInput.value=income||'';paydayInput.value=incomeDetails[month.value]?.payday||'';incomeSourceInput.value=incomeDetails[month.value]?.source||'';document.querySelector('#spent').textContent=brl(spent);document.querySelector('#count').textContent=`${cash.length} lançamento${cash.length===1?'':'s'}`;const b=document.querySelector('#balance');b.textContent=brl(balance);b.className=balance>=0?'positive':'negative';document.querySelector('#voucherIncome').textContent=brl(voucherIncome);voucherInput.value=voucherIncome||'';document.querySelector('#voucherSpent').textContent=brl(voucherSpent);document.querySelector('#voucherCount').textContent=`${voucher.length} lançamento${voucher.length===1?'':'s'}`;const vb=document.querySelector('#voucherBalance');vb.textContent=brl(voucherBalance);vb.className=voucherBalance>=0?'positive':'negative';
 const priorSpent=DATA.filter(x=>x.date.startsWith(previousMonth(month.value))).reduce((sum,x)=>sum+x.amount,0),comparison=document.querySelector('#monthComparison');if(!priorSpent){comparison.textContent='Sem histórico';comparison.className=''}else{const change=(currentSpent-priorSpent)/priorSpent*100;comparison.textContent=`${Math.abs(change).toFixed(0)}% ${change<=0?'menos':'mais'}`;comparison.className=change<=0?'positive':'negative'}
 const sums={};cash.forEach(x=>sums[x.category]=(sums[x.category]||0)+x.amount);const list=Object.entries(sums).sort((a,b)=>b[1]-a[1]);const max=list[0]?.[1]||1;document.querySelector('#bars').innerHTML=list.map(([c,v])=>`<div><div class="bar-head"><span>${esc(c)}</span><strong>${brl(v)}</strong></div><div class="track"><div class="fill" style="width:${v/max*100}%"></div></div></div>`).join('');
 let at=0;const stops=list.map(([c,v],i)=>{const start=at;at+=v/spent*100;return `${COLORS[i%COLORS.length]} ${start}% ${at}%`});document.querySelector('#ring').style.background=spent?`conic-gradient(${stops.join(',')})`:'#27322b';document.querySelector('#ringTotal').textContent=brl(spent);document.querySelector('#legend').innerHTML=list.slice(0,8).map(([c,v],i)=>`<div class="legend-row"><span><i class="dot" style="background:${COLORS[i%COLORS.length]}"></i>${esc(c)}</span><strong>${(v/spent*100).toFixed(0)}%</strong></div>`).join('');
 const voucherSums={};voucher.forEach(x=>voucherSums[x.category]=(voucherSums[x.category]||0)+x.amount);const voucherList=Object.entries(voucherSums).sort((a,b)=>b[1]-a[1]),voucherMax=voucherList[0]?.[1]||1;document.querySelector('#voucherBars').innerHTML=voucherList.length?voucherList.map(([c,v])=>`<div><div class="bar-head"><span>${esc(c)}</span><strong>${brl(v)}</strong></div><div class="track"><div class="fill" style="width:${v/voucherMax*100}%;background:linear-gradient(90deg,#7656d6,#315cfd)"></div></div></div>`).join(''):'<div class="empty">Nenhum gasto com voucher neste mês.</div>';
 const entrySums={};INCOME_ENTRIES.filter(x=>x.date.startsWith(month.value)).forEach(x=>entrySums[x.category]=(entrySums[x.category]||0)+x.amount);const entryList=Object.entries(entrySums).sort((a,b)=>b[1]-a[1]),entryTotal=entryList.reduce((s,[,v])=>s+v,0),entryMax=entryList[0]?.[1]||1;document.querySelector('#incomeEntriesTotal').textContent=brl(entryTotal);document.querySelector('#incomeEntryBars').innerHTML=entryList.length?entryList.map(([c,v])=>`<div><div class="bar-head"><span>${esc(c)}</span><strong>${brl(v)}</strong></div><div class="track"><div class="fill income-fill" style="width:${v/entryMax*100}%"></div></div></div>`).join(''):'<div class="empty">Nenhuma entrada importada neste mês.</div>';
 const future=DATA.filter(x=>x.installment_group&&x.date.slice(0,7)>month.value).sort((a,b)=>a.date.localeCompare(b.date)).slice(0,6);document.querySelector('#upcomingInstallments').innerHTML=future.length?future.map(x=>`<div><span><strong>${esc(x.where)}</strong><small>${esc(x.description)}</small></span><span>${monthLabel(x.date.slice(0,7))}<strong>${brl(x.amount)}</strong></span></div>`).join(''):'<div class="empty">Nenhuma parcela futura cadastrada.</div>';
 const totalByCategory={};all.forEach(x=>totalByCategory[x.category]=(totalByCategory[x.category]||0)+x.amount);const monthBudgets=BUDGETS[month.value]||{};const alerts=[];document.querySelector('#budgetList').innerHTML=ALL_CATEGORIES.map(c=>{const used=totalByCategory[c]||0,limit=monthBudgets[c]||0,remaining=limit-used,pct=limit?remaining/limit*100:null;let status='Defina um limite para acompanhar',level='';if(limit){if(remaining<0){status=`Limite ultrapassado em ${brl(-remaining)}`;level='over'}else if(pct<=5){status=`Restam ${brl(remaining)} — até 5% do limite`;level='critical'}else if(pct<=10){status=`Restam ${brl(remaining)} — até 10% do limite`;level='critical'}else if(pct<=20){status=`Restam ${brl(remaining)} — até 20% do limite`;level='warning'}else status=`Restam ${brl(remaining)} (${pct.toFixed(0)}%)`;if(level)alerts.push({category:c,status,level})}return `<div class="budget-row"><strong>${c}</strong><span>Usado: ${brl(used)}</span><input type="number" min="0" step="0.01" value="${limit||''}" placeholder="Máximo" data-budget-category="${c}"><div class="budget-status ${level}">${status}</div></div>`}).join('');document.querySelector('#budgetAlerts').innerHTML=alerts.map(a=>`<div class="alert ${a.level}">⚠ ${a.category}: ${a.status}</div>`).join('');
 document.querySelector('#rows').innerHTML=view.sort((a,b)=>b.date.localeCompare(a.date)).map(x=>`<tr><td>${date(x.date)}</td><td><strong>${esc(x.where)}</strong></td><td><span class="pill">${esc(x.category)}</span></td><td>${esc(x.payment)}${x.finance?.scheduled_date?'<small> · Agendado no app</small>':''}</td><td>${esc(x.description)}</td><td class="money">${brl(x.amount)}</td><td><div class="row-actions"><button data-edit-expense="${x.id}" class="text-button">${x.finance?.debt_entry?'Ver dívida':'Editar'}</button><button data-delete-expense="${x.id}" class="text-button danger-text">Excluir</button></div></td></tr>`).join('');document.querySelector('#empty').hidden=!!view.length;
}
[month,category].forEach(el=>el.addEventListener('change',render));search.addEventListener('input',render);
const storageStatus=document.querySelector('#storageStatus'),incomeMessage=document.querySelector('#incomeMessage'),saveIncomeButton=document.querySelector('#saveIncomeButton');
function localOnlyMessage(){return 'Sem conexão com o servidor do aplicativo. Confira se ele está aberto e se este dispositivo está conectado à sua rede privada.'}
async function loadBootstrap(){const response=await fetch('/api/bootstrap',{cache:'no-store'});if(response.status===401){location.href='/login';return}const result=await response.json();if(!response.ok)throw new Error(result.error||'Não foi possível carregar os dados');DATA=result.expenses||[];INCOME_ENTRIES=result.income_entries||[];Object.keys(incomeByMonth).forEach(k=>delete incomeByMonth[k]);Object.keys(voucherByMonth).forEach(k=>delete voucherByMonth[k]);Object.keys(incomeDetails).forEach(k=>delete incomeDetails[k]);Object.keys(BUDGETS).forEach(k=>delete BUDGETS[k]);Object.entries(result.incomes||{}).forEach(([k,v])=>{incomeByMonth[k]=v.cash;voucherByMonth[k]=v.voucher;incomeDetails[k]=v});Object.assign(BUDGETS,result.budgets||{});if(result.categories)ALL_CATEGORIES=result.categories;portfolio=result.portfolio||portfolio;const userBadge=document.querySelector('#userBadge');if(result.user?.name){userBadge.textContent=result.user.name;userBadge.hidden=false}populateFilters();refreshCategoryOptions();render();renderDebtEstimates();renderBudgetPanel();renderInvestments();renderDebtsPanel()}
async function checkStorage(){try{const response=await fetch('/api/health',{cache:'no-store'});if(response.status===401){location.href='/login';return}const result=await response.json();if(!response.ok||!result.ok)throw new Error();canWrite=true;storageStatus.textContent='Conectado';storageStatus.classList.remove('readonly');await loadBootstrap()}catch(error){canWrite=false;storageStatus.textContent=localOnlyMessage();storageStatus.classList.add('readonly')}}
async function persistIncome(){incomeMessage.hidden=true;if(!canWrite){incomeMessage.textContent=localOnlyMessage();incomeMessage.className='message error';incomeMessage.hidden=false;return}saveIncomeButton.disabled=true;const payload={month:month.value,cash:Math.max(0,+incomeInput.value||0),voucher:Math.max(0,+voucherInput.value||0),payday:paydayInput.value?+paydayInput.value:null,source:incomeSourceInput.value.trim()};try{const response=await fetch('/api/incomes',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),result=await response.json();if(!response.ok)throw new Error(result.error||'Não foi possível salvar os valores');incomeByMonth[month.value]=payload.cash;voucherByMonth[month.value]=payload.voucher;incomeDetails[month.value]=payload;incomeMessage.textContent='Renda e recebimento salvos.';incomeMessage.className='message ok';incomeMessage.hidden=false;render()}catch(error){incomeMessage.textContent=error.message||'Não foi possível salvar os valores.';incomeMessage.className='message error';incomeMessage.hidden=false}finally{saveIncomeButton.disabled=false}}
saveIncomeButton.addEventListener('click',persistIncome);render();
document.querySelector('#budgetList').addEventListener('change',async event=>{const input=event.target.closest('[data-budget-category]');if(!input)return;if(!canWrite){alert(localOnlyMessage());render();return}input.disabled=true;try{const payload={month:month.value,category:input.dataset.budgetCategory,limit:Math.max(0,+input.value||0)},response=await fetch('/api/budgets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}),result=await response.json();if(!response.ok)throw new Error(result.error||'Não foi possível salvar o limite');BUDGETS[month.value]??={};BUDGETS[month.value][payload.category]=payload.limit;render()}catch(error){alert(error.message||'Não foi possível salvar o limite.');input.disabled=false}});
document.querySelectorAll('.tab').forEach(tab=>tab.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(x=>{const active=x===tab;x.classList.toggle('active',active);x.setAttribute('aria-current',active?'page':'false')});document.querySelectorAll('.panel').forEach(x=>x.hidden=x.id!==tab.dataset.panel);document.querySelector('#filters').hidden=tab.dataset.panel!=='dashboardPanel';document.querySelector('#quickExpense').hidden=tab.dataset.panel!=='dashboardPanel';scrollTo({top:0,behavior:'smooth'})}));
const form=document.querySelector('#expenseForm'),message=document.querySelector('#formMessage'),creditOptions=document.querySelector('#creditOptions'),installmentFields=document.querySelector('#installmentFields');let editingExpenseId=null,editingExpense=null;form.date.value=new Date().toISOString().slice(0,10);form.first_charge_date.value=form.date.value;
__EXPENSE_FINANCE_JS__
updateCreditOptions();
async function sendExpense(payload){return fetch(editingExpenseId?`/api/expenses/${editingExpenseId}`:'/api/expenses',{method:editingExpenseId?'PUT':'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)})}
form.addEventListener('submit',async event=>{event.preventDefault();const button=form.querySelector('button');button.disabled=true;message.hidden=true;if(!canWrite){message.textContent=localOnlyMessage();message.className='message error';message.hidden=false;button.disabled=false;return}try{const payload=expensePayload();if(editingExpense?.installment_group)payload.scope=confirm('Aplicar a alteração a todas as parcelas desta compra?')?'all':'single';let response=await sendExpense(payload),result=await response.json();if(response.status===409&&result.code==='duplicate'){if(!confirm(`${result.error}. Deseja lançar mesmo assim?`)){button.disabled=false;return}payload.allow_duplicate=true;response=await sendExpense(payload);result=await response.json()}if(!response.ok)throw new Error(result.error||'Não foi possível salvar');await loadBootstrap();form.reset();form.date.value=new Date().toISOString().slice(0,10);form.first_charge_date.value=form.date.value;editingExpenseId=null;editingExpense=null;button.textContent='Salvar gasto';updateCreditOptions();message.textContent=result.installment_group?`${result.ids.length} parcelas criadas e distribuídas nos próximos meses.`:'Gasto salvo. Painel e limites atualizados.';message.className='message ok';message.hidden=false;button.disabled=false}catch(error){message.textContent=error.message||'Não foi possível salvar o gasto.';message.className='message error';message.hidden=false;button.disabled=false}});
document.querySelector('#rows').addEventListener('click',async event=>{const edit=event.target.closest('[data-edit-expense]'),remove=event.target.closest('[data-delete-expense]');if(edit){const item=DATA.find(x=>String(x.id)===edit.dataset.editExpense);if(!item)return;if(item.finance?.debt_entry){document.querySelector('[data-panel="debtsPanel"]').click();debtFilter.value=item.installment_group;renderDebtsPanel();return}editingExpenseId=item.id;editingExpense=item;Object.entries({date:item.date,amount:item.amount,where:item.where,category:item.category,payment:item.payment,description:item.description.replace(/ · Parcela \d+\/\d+$/,'')}).forEach(([key,value])=>form.elements[key].value=key==='amount'?moneyText(value):value);form.elements.financing_kind.value=item.finance?.financing_kind||'purchase';form.elements.scheduled.checked=!!item.finance?.scheduled_date;form.elements.scheduled_date.value=item.finance?.scheduled_date||'';document.querySelector('[data-panel="entryPanel"]').click();form.querySelector('.save').textContent=item.installment_group?'Salvar parcela':'Salvar alterações';updateCreditOptions();form.scrollIntoView({behavior:'smooth'})}if(remove){const item=DATA.find(x=>String(x.id)===remove.dataset.deleteExpense);if(!confirm(item?.finance?.debt_entry?'Excluir este compromisso e todas as parcelas dele?':'Excluir este gasto?'))return;const scope=item?.finance?.debt_entry?'all':item?.installment_group&&confirm('Excluir também todas as outras parcelas desta compra?')?'all':'single',response=await fetch(`/api/expenses/${remove.dataset.deleteExpense}?scope=${scope}`,{method:'DELETE'}),result=await response.json();if(!response.ok)return alert(result.error||'Não foi possível excluir');await loadBootstrap()}});
const now=new Date();document.querySelector('#todayLabel').textContent=new Intl.DateTimeFormat('pt-BR',{weekday:'long',day:'2-digit',month:'long'}).format(now);
</script></body></html>'''

safe_data = json.dumps(expenses, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
html = template.replace("__DATA__", safe_data).replace(
    "__INCOME__", json.dumps(initial_income, separators=(",", ":"))
).replace("__VOUCHER__", json.dumps(initial_voucher, separators=(",", ":")))
html = html.replace("__INCOME_DETAILS__", json.dumps(initial_income_details, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
html = html.replace("__INCOME_ENTRIES__", json.dumps(initial_income_entries, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/"))
html = html.replace("__BUDGETS__", json.dumps(initial_budgets, ensure_ascii=False, separators=(",", ":"))).replace(
    "__CATEGORIES__", json.dumps(CATEGORIES, ensure_ascii=False, separators=(",", ":"))
)
investment_css = (ROOT / "src/investments_panel.css").read_text(encoding="utf-8")
investment_panel = (ROOT / "src/investments_panel.html").read_text(encoding="utf-8")
investment_js = (ROOT / "src/investments_panel.js").read_text(encoding="utf-8")
statement_css = (ROOT / "src/statement_panel.css").read_text(encoding="utf-8")
statement_panel = (ROOT / "src/statement_panel.html").read_text(encoding="utf-8")
statement_js = (ROOT / "src/statement_panel.js").read_text(encoding="utf-8")
budget_css = (ROOT / "src/budget_panel.css").read_text(encoding="utf-8")
budget_panel = (ROOT / "src/budget_panel.html").read_text(encoding="utf-8")
budget_js = (ROOT / "src/budget_panel.js").read_text(encoding="utf-8")
debt_css = (ROOT / "src/debts_panel.css").read_text(encoding="utf-8")
debt_panel = (ROOT / "src/debts_panel.html").read_text(encoding="utf-8")
debt_js = (ROOT / "src/debts_panel.js").read_text(encoding="utf-8")
pwa_js = (ROOT / "src/pwa.js").read_text(encoding="utf-8")
html = html.replace("</style>", investment_css + "\n" + statement_css + "\n" + budget_css + "\n" + debt_css + "\n  </style>", 1)
html = html.replace(
    '<button class="tab" data-panel="entryPanel"><span class="tab-icon" aria-hidden="true">＋</span><span>Lançar</span></button>',
    '<button class="tab" data-panel="entryPanel"><span class="tab-icon" aria-hidden="true">＋</span><span>Lançar</span></button><button class="tab" data-panel="budgetsPanel"><span class="tab-icon" aria-hidden="true">◌</span><span>Planejar</span></button><button class="tab" data-panel="investmentsPanel"><span class="tab-icon" aria-hidden="true">↗</span><span>Investir</span></button><button class="tab" data-panel="debtsPanel"><span class="tab-icon" aria-hidden="true">◷</span><span>Dívidas</span></button>',
    1,
)
html = html.replace('  <div class="foot">', budget_panel + '\n' + investment_panel + '\n' + debt_panel + '\n  <button id="quickExpense" class="quick-expense" type="button" aria-label="Lançar novo gasto">＋</button>\n  <div class="foot">', 1)
html = html.replace('<section class="card entry" data-entry-content="manual"><span class="eyebrow">Lançamento manual</span>', statement_panel + '<section class="card entry" data-entry-content="manual"><span class="eyebrow">Lançamento manual</span>', 1)
safe_investments = json.dumps(initial_investments, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
html = html.replace("let DATA=", f"const INVESTMENT_DATA={safe_investments};\nlet DATA=", 1)
html = html.replace("__EXPENSE_FINANCE_JS__", (ROOT / "src/expense_finance.js").read_text(encoding="utf-8"))
html = html.replace("</script>", investment_js + "\n" + statement_js + "\n" + budget_js + "\n" + debt_js + "\n" + pwa_js + "\n</script>", 1)
icons = {
    "⌁": '<rect x="3" y="3" width="7" height="7" rx="1.5"/><rect x="14" y="3" width="7" height="7" rx="1.5"/><rect x="3" y="14" width="7" height="7" rx="1.5"/><rect x="14" y="14" width="7" height="7" rx="1.5"/>',
    "＋": '<path d="M12 5v14M5 12h14"/>',
    "◌": '<rect x="4" y="5" width="16" height="16" rx="2"/><path d="M8 3v4M16 3v4M4 11h16M8 15h3M8 18h6"/>',
    "↗": '<path d="M3 17l6-6 4 4 8-10M15 5h6v6M3 21h18"/>',
    "◷": '<rect x="3" y="5" width="18" height="14" rx="3"/><path d="M3 10h18M7 15h4"/>',
}
for glyph, paths in icons.items():
    html = html.replace(f'<span class="tab-icon" aria-hidden="true">{glyph}</span>',
                        f'<span class="tab-icon" aria-hidden="true"><svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round">{paths}</svg></span>')
html = html.replace('class="tab active"', 'class="tab active" aria-current="page"', 1)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(html, encoding="utf-8")
print(f"{OUTPUT} — {len(expenses)} lançamentos — {len(months)} meses")
