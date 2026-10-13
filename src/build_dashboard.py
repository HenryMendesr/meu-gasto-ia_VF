"""Gera um painel HTML autônomo usando os lançamentos da planilha XLSM."""

from collections import defaultdict
from datetime import datetime
from html import escape
import json
from pathlib import Path
from zipfile import ZipFile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
XLSM = ROOT / "excel/Controle_Gastos_Automatico.xlsm"
OUTPUT = ROOT / "web/index.html"
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"


def read_expenses() -> list[dict]:
    with ZipFile(XLSM) as workbook:
        sheet = ET.fromstring(workbook.read("xl/worksheets/sheet1.xml"))

    def value(row: int, column: str) -> str | None:
        cell = sheet.find(f'.//{{{NS}}}c[@r="{column}{row}"]')
        if cell is None:
            return None
        return cell.findtext(f"{{{NS}}}v")

    expenses = []
    for row in range(51, 551):
        date_value = value(row, "A")
        amount_value = value(row, "F")
        if not date_value or not amount_value:
            continue
        expenses.append(
            {
                "date": date_value[:10],
                "where": value(row, "B") or "Não informado",
                "category": value(row, "C") or "Outros",
                "payment": value(row, "D") or "Não informado",
                "description": value(row, "E") or "",
                "amount": round(float(amount_value), 2),
            }
        )
    return expenses


expenses = read_expenses()
months = sorted({item["date"][:7] for item in expenses}, reverse=True)

# Salários identificados no extrato. O usuário pode editar estes valores no painel;
# as alterações ficam salvas apenas no navegador.
initial_income = {"2026-08": 3469.09, "2026-09": 3586.42, "2026-10": 0}

template = r'''<!doctype html>
<html lang="pt-BR">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <meta name="color-scheme" content="light">
  <link rel="icon" href="data:,">
  <title>Meu Gasto IA</title>
  <style>
    :root{--red:#a61f24;--red2:#d24545;--ink:#17202a;--muted:#687281;--bg:#f4f6f8;--card:#fff;--line:#e5e8ec;--yellow:#fff3bf;--green:#18794e;--shadow:0 12px 36px rgba(31,38,46,.08)}
    *{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.45 Inter,Arial,sans-serif}button,input,select{font:inherit}
    .shell{max-width:1220px;margin:auto;padding:28px 22px 56px}.top{display:flex;justify-content:space-between;gap:20px;align-items:center;margin-bottom:24px}.brand{display:flex;align-items:center;gap:14px}.mark{width:46px;height:46px;border-radius:15px;background:linear-gradient(145deg,var(--red2),var(--red));display:grid;place-items:center;color:white;font-size:24px;box-shadow:0 9px 24px rgba(166,31,36,.25)}h1{font-size:25px;margin:0}.sub{color:var(--muted);font-size:13px;margin-top:2px}
    .controls{display:flex;gap:10px;flex-wrap:wrap}.field{background:#fff;border:1px solid var(--line);border-radius:12px;padding:9px 12px;color:var(--ink);min-height:42px}.month{min-width:180px}.tabs{display:flex;gap:7px;margin-bottom:18px}.tab{border:0;border-radius:11px;padding:10px 16px;background:#e8eaed;color:var(--muted);font-weight:750;cursor:pointer}.tab.active{background:var(--red);color:#fff}.panel[hidden]{display:none}.grid{display:grid;grid-template-columns:repeat(3,1fr);gap:15px}.card{background:var(--card);border:1px solid rgba(222,226,231,.9);border-radius:18px;padding:19px;box-shadow:var(--shadow)}.metric small{display:block;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.07em;font-size:10px}.metric strong{display:block;font-size:25px;margin-top:8px}.metric .hint{font-size:12px;color:var(--muted);margin-top:4px}.voucher-card{border-top:3px solid #6f5aa8}.positive{color:var(--green)}.negative{color:var(--red)}
    .main{display:grid;grid-template-columns:1.1fr .9fr;gap:15px;margin-top:15px}.card h2{font-size:15px;margin:0 0 16px}.bars{display:grid;gap:12px}.bar-head{display:flex;justify-content:space-between;gap:12px;font-size:13px}.track{height:9px;background:#f0f1f3;border-radius:99px;overflow:hidden;margin-top:6px}.fill{height:100%;border-radius:99px;background:linear-gradient(90deg,var(--red2),var(--red))}.ring-wrap{display:flex;align-items:center;gap:26px}.ring{width:170px;height:170px;border-radius:50%;display:grid;place-items:center;position:relative}.ring:after{content:"";width:112px;height:112px;background:white;border-radius:50%;position:absolute}.ring-center{z-index:1;text-align:center}.ring-center strong{display:block;font-size:21px}.legend{display:grid;gap:10px;flex:1}.legend-row{display:flex;align-items:center;justify-content:space-between;gap:8px;font-size:12px}.dot{width:9px;height:9px;border-radius:3px;display:inline-block;margin-right:7px}
    .table-card{margin-top:15px;padding:0;overflow:hidden}.table-head{padding:18px 19px;display:flex;justify-content:space-between;align-items:center;gap:12px;border-bottom:1px solid var(--line)}.table-head h2{margin:0}.search{width:min(320px,48vw)}.scroll{overflow:auto;max-height:560px}table{width:100%;border-collapse:collapse;min-width:760px}th{position:sticky;top:0;background:#fafbfc;color:var(--muted);font-size:10px;letter-spacing:.06em;text-transform:uppercase;text-align:left;padding:11px 15px;border-bottom:1px solid var(--line)}td{padding:12px 15px;border-bottom:1px solid #eef0f2;font-size:13px}tbody tr:hover{background:#fffafa}.money{text-align:right;font-weight:750}.pill{display:inline-block;padding:4px 8px;border-radius:99px;background:#f1f2f4;font-size:11px;font-weight:700}.empty{padding:42px;text-align:center;color:var(--muted)}
    .income-edit{display:flex;gap:7px;align-items:center;margin-top:6px}.income-edit input{width:125px;padding:5px 8px;border:1px solid var(--line);border-radius:8px;background:var(--yellow);font-weight:700}.entry{max-width:760px;margin:0 auto}.entry h2{font-size:22px;margin-bottom:5px}.entry-grid{display:grid;grid-template-columns:1fr 1fr;gap:15px;margin-top:24px}.entry label{display:grid;gap:7px;font-weight:700;font-size:12px;color:var(--muted)}.entry label.wide{grid-column:1/-1}.entry input,.entry select{width:100%;background:var(--yellow);border:1px solid #e5d68f;border-radius:11px;padding:12px;color:var(--ink)}.save{grid-column:1/-1;border:0;border-radius:12px;background:var(--red);color:#fff;font-weight:800;padding:13px;cursor:pointer}.save:disabled{opacity:.55}.message{grid-column:1/-1;padding:11px;border-radius:10px;font-weight:700;font-size:13px}.message.ok{background:#e4f4ea;color:var(--green)}.message.error{background:#fde8e8;color:var(--red)}.foot{text-align:center;color:var(--muted);font-size:11px;margin-top:18px}
    @media(max-width:900px){.grid{grid-template-columns:repeat(2,1fr)}.main{grid-template-columns:1fr}.top{align-items:flex-start;flex-direction:column}.controls{width:100%}.month{flex:1}.ring-wrap{justify-content:center}}
    @media(max-width:540px){.shell{padding:20px 13px 44px}.grid{grid-template-columns:1fr 1fr;gap:10px}.card{padding:15px;border-radius:15px}.metric strong{font-size:20px}.ring-wrap{flex-direction:column}.search{width:50vw}h1{font-size:21px}.entry-grid{grid-template-columns:1fr}.entry label.wide,.save{grid-column:auto}}
  </style>
</head>
<body><main class="shell">
  <header class="top"><div class="brand"><div class="mark">↗</div><div><h1>Meu Gasto IA</h1><div class="sub">Seu dinheiro, explicado de forma simples.</div></div></div><div id="filters" class="controls"><select id="month" class="field month"></select><select id="category" class="field"><option value="">Todas as categorias</option></select></div></header>
  <nav class="tabs"><button class="tab active" data-panel="dashboardPanel">Dashboard</button><button class="tab" data-panel="entryPanel">Lançar gasto</button></nav>
  <div id="dashboardPanel" class="panel">
  <section class="grid">
    <article class="card metric"><small>Renda em dinheiro</small><strong id="income">—</strong><div class="income-edit"><span>R$</span><input id="incomeInput" type="number" min="0" step="0.01" aria-label="Renda em dinheiro"></div></article>
    <article class="card metric"><small>Gastos em dinheiro</small><strong id="spent" class="negative">—</strong><div class="hint" id="count">—</div></article>
    <article class="card metric"><small>Saldo em dinheiro</small><strong id="balance">—</strong><div class="hint">Sem considerar o voucher</div></article>
    <article class="card metric voucher-card"><small>Crédito do voucher</small><strong id="voucherIncome">—</strong><div class="income-edit"><span>R$</span><input id="voucherInput" type="number" min="0" step="0.01" aria-label="Crédito do voucher"></div></article>
    <article class="card metric voucher-card"><small>Gastos no voucher</small><strong id="voucherSpent" class="negative">—</strong><div class="hint" id="voucherCount">—</div></article>
    <article class="card metric voucher-card"><small>Saldo do voucher</small><strong id="voucherBalance">—</strong><div class="hint">Separado da renda em dinheiro</div></article>
  </section>
  <section class="main"><article class="card"><h2>Gastos por categoria — dinheiro</h2><div id="bars" class="bars"></div></article><article class="card"><h2>Distribuição dos gastos em dinheiro</h2><div class="ring-wrap"><div id="ring" class="ring"><div class="ring-center"><strong id="ringTotal">—</strong><span class="sub">total</span></div></div><div id="legend" class="legend"></div></div></article></section>
  <section class="card voucher-card" style="margin-top:15px"><h2>Gastos por categoria — voucher</h2><div id="voucherBars" class="bars"></div></section>
  <section class="card table-card"><div class="table-head"><h2>Histórico de gastos</h2><input id="search" class="field search" placeholder="Buscar gasto..."></div><div class="scroll"><table><thead><tr><th>Data</th><th>Onde</th><th>Categoria</th><th>Pagamento</th><th>Descrição</th><th style="text-align:right">Valor</th></tr></thead><tbody id="rows"></tbody></table><div id="empty" class="empty" hidden>Nenhum gasto encontrado.</div></div></section>
  </div>
  <div id="entryPanel" class="panel" hidden><section class="card entry"><h2>Novo gasto</h2><div class="sub">Ao salvar, o lançamento entra no Excel e o dashboard é atualizado.</div><form id="expenseForm" class="entry-grid">
    <label>Data<input name="date" type="date" required></label><label>Valor (R$)<input name="amount" type="number" min="0.01" step="0.01" placeholder="0,00" required></label>
    <label class="wide">Onde foi gasto<input name="where" maxlength="100" placeholder="Ex.: Posto, mercado, restaurante" required></label>
    <label>Categoria<select name="category" required><option>Alimentação</option><option>Mercado</option><option>Transporte</option><option>Moradia</option><option>Saúde</option><option>Educação</option><option>Lazer</option><option>Compras</option><option>Assinaturas</option><option>Contas</option><option>Viagem</option><option>Presentes</option><option>Outros</option></select></label>
    <label>Pagamento<select name="payment" required><option>Pix</option><option>Crédito</option><option>Débito</option><option>Dinheiro</option><option>Transferência</option><option>Voucher</option><option>Não informado</option></select></label>
    <label class="wide">Descrição<input name="description" maxlength="200" placeholder="Opcional"></label><button class="save" type="submit">Salvar no Excel</button><div id="formMessage" class="message" hidden></div>
  </form></section></div>
  <div class="foot">Os lançamentos são gravados em Controle_Gastos_Automatico.xlsm • mantenha o servidor local aberto durante o uso</div>
</main><script>
const DATA=__DATA__;
const DEFAULT_INCOME=__INCOME__;
const COLORS=['#a61f24','#dc555a','#e98972','#f0ad72','#d5a021','#6e9f76','#4f839d','#796a9d','#8a7474','#687281'];
const brl=v=>v.toLocaleString('pt-BR',{style:'currency',currency:'BRL'});
const date=v=>new Date(v+'T12:00:00').toLocaleDateString('pt-BR');
const monthLabel=v=>{const [y,m]=v.split('-');return new Date(+y,+m-1,1).toLocaleDateString('pt-BR',{month:'long',year:'numeric'}).replace(/^./,x=>x.toUpperCase())};
const saved=JSON.parse(localStorage.getItem('meuGastoIncome')||'{}');
const incomeByMonth={...DEFAULT_INCOME,...saved};
const savedVoucher=JSON.parse(localStorage.getItem('meuGastoVoucherIncome')||'{}');
const voucherByMonth={...savedVoucher};
const month=document.querySelector('#month'),category=document.querySelector('#category'),search=document.querySelector('#search'),incomeInput=document.querySelector('#incomeInput'),voucherInput=document.querySelector('#voucherInput');
const months=[...new Set(DATA.map(x=>x.date.slice(0,7)))].sort().reverse();months.forEach(m=>month.add(new Option(monthLabel(m),m)));
const categories=[...new Set(DATA.map(x=>x.category))].sort();categories.forEach(c=>category.add(new Option(c,c)));
function filtered(){const q=search.value.trim().toLocaleLowerCase('pt-BR');return DATA.filter(x=>x.date.startsWith(month.value)&&(!category.value||x.category===category.value)&&(!q||Object.values(x).join(' ').toLocaleLowerCase('pt-BR').includes(q)))}
function render(){const all=DATA.filter(x=>x.date.startsWith(month.value));const cash=all.filter(x=>x.payment!=='Voucher'),voucher=all.filter(x=>x.payment==='Voucher');const view=filtered();const spent=cash.reduce((s,x)=>s+x.amount,0),voucherSpent=voucher.reduce((s,x)=>s+x.amount,0);const income=+(incomeByMonth[month.value]||0),voucherIncome=+(voucherByMonth[month.value]||0);const balance=income-spent,voucherBalance=voucherIncome-voucherSpent;
 document.querySelector('#income').textContent=brl(income);incomeInput.value=income||'';document.querySelector('#spent').textContent=brl(spent);document.querySelector('#count').textContent=`${cash.length} lançamento${cash.length===1?'':'s'}`;const b=document.querySelector('#balance');b.textContent=brl(balance);b.className=balance>=0?'positive':'negative';document.querySelector('#voucherIncome').textContent=brl(voucherIncome);voucherInput.value=voucherIncome||'';document.querySelector('#voucherSpent').textContent=brl(voucherSpent);document.querySelector('#voucherCount').textContent=`${voucher.length} lançamento${voucher.length===1?'':'s'}`;const vb=document.querySelector('#voucherBalance');vb.textContent=brl(voucherBalance);vb.className=voucherBalance>=0?'positive':'negative';
 const sums={};cash.forEach(x=>sums[x.category]=(sums[x.category]||0)+x.amount);const list=Object.entries(sums).sort((a,b)=>b[1]-a[1]);const max=list[0]?.[1]||1;document.querySelector('#bars').innerHTML=list.map(([c,v])=>`<div><div class="bar-head"><span>${c}</span><strong>${brl(v)}</strong></div><div class="track"><div class="fill" style="width:${v/max*100}%"></div></div></div>`).join('');
 let at=0;const stops=list.map(([c,v],i)=>{const start=at;at+=v/spent*100;return `${COLORS[i%COLORS.length]} ${start}% ${at}%`});document.querySelector('#ring').style.background=spent?`conic-gradient(${stops.join(',')})`:'#eef0f2';document.querySelector('#ringTotal').textContent=brl(spent);document.querySelector('#legend').innerHTML=list.slice(0,8).map(([c,v],i)=>`<div class="legend-row"><span><i class="dot" style="background:${COLORS[i%COLORS.length]}"></i>${c}</span><strong>${(v/spent*100).toFixed(0)}%</strong></div>`).join('');
 const voucherSums={};voucher.forEach(x=>voucherSums[x.category]=(voucherSums[x.category]||0)+x.amount);const voucherList=Object.entries(voucherSums).sort((a,b)=>b[1]-a[1]),voucherMax=voucherList[0]?.[1]||1;document.querySelector('#voucherBars').innerHTML=voucherList.length?voucherList.map(([c,v])=>`<div><div class="bar-head"><span>${c}</span><strong>${brl(v)}</strong></div><div class="track"><div class="fill" style="width:${v/voucherMax*100}%;background:#6f5aa8"></div></div></div>`).join(''):'<div class="empty">Nenhum gasto com voucher neste mês.</div>';
 document.querySelector('#rows').innerHTML=view.sort((a,b)=>b.date.localeCompare(a.date)).map(x=>`<tr><td>${date(x.date)}</td><td><strong>${x.where}</strong></td><td><span class="pill">${x.category}</span></td><td>${x.payment}</td><td>${x.description}</td><td class="money">${brl(x.amount)}</td></tr>`).join('');document.querySelector('#empty').hidden=!!view.length;
}
[month,category].forEach(el=>el.addEventListener('change',render));search.addEventListener('input',render);incomeInput.addEventListener('change',()=>{incomeByMonth[month.value]=Math.max(0,+incomeInput.value||0);localStorage.setItem('meuGastoIncome',JSON.stringify(incomeByMonth));render()});voucherInput.addEventListener('change',()=>{voucherByMonth[month.value]=Math.max(0,+voucherInput.value||0);localStorage.setItem('meuGastoVoucherIncome',JSON.stringify(voucherByMonth));render()});render();
document.querySelectorAll('.tab').forEach(tab=>tab.addEventListener('click',()=>{document.querySelectorAll('.tab').forEach(x=>x.classList.toggle('active',x===tab));document.querySelectorAll('.panel').forEach(x=>x.hidden=x.id!==tab.dataset.panel);document.querySelector('#filters').style.visibility=tab.dataset.panel==='dashboardPanel'?'visible':'hidden'}));
const form=document.querySelector('#expenseForm'),message=document.querySelector('#formMessage');form.date.value=new Date().toISOString().slice(0,10);form.addEventListener('submit',async event=>{event.preventDefault();const button=form.querySelector('button');button.disabled=true;message.hidden=true;try{const payload=Object.fromEntries(new FormData(form));payload.amount=Number(payload.amount);const response=await fetch('/api/expenses',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)});const result=await response.json();if(!response.ok)throw new Error(result.error||'Não foi possível salvar');message.textContent='Gasto salvo no Excel. Atualizando o painel...';message.className='message ok';message.hidden=false;setTimeout(()=>location.reload(),700)}catch(error){message.textContent=location.protocol==='file:'?'Abra o painel pelo servidor local para salvar no Excel.':error.message;message.className='message error';message.hidden=false;button.disabled=false}});
</script></body></html>'''

safe_data = json.dumps(expenses, ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")
html = template.replace("__DATA__", safe_data).replace(
    "__INCOME__", json.dumps(initial_income, separators=(",", ":"))
)
OUTPUT.parent.mkdir(parents=True, exist_ok=True)
OUTPUT.write_text(html, encoding="utf-8")
print(f"{OUTPUT} — {len(expenses)} lançamentos — {len(months)} meses")
