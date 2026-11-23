const budgetMonth=document.querySelector('#budgetMonth'),limitsList=document.querySelector('#limitsList'),limitsMessage=document.querySelector('#limitsMessage');
const budgetDrafts=new Map();
let budgetSaving=false;
let budgetSaveError='';
const BUDGET_GROUPS=__BUDGET_GROUPS__;
const budgetGroupLabel=id=>BUDGET_GROUPS.find(group=>group.id===id)?.label||id;
const BUDGET_GROUP_IDS=new Set(BUDGET_GROUPS.map(group=>group.id));
const normalizedBudgetCategory=name=>name.normalize('NFD').replace(/[\u0300-\u036f]/g,'').toLowerCase();
function budgetGroupFor(category){return BUDGET_GROUPS.find(group=>[...group.categories,...(group.aliases||[])].some(name=>normalizedBudgetCategory(name)===normalizedBudgetCategory(category)))?.id||'@budget:other'}
const BUDGET_GROUP_ICONS={
 '@budget:fixed':'<path d="m3 11 9-8 9 8M5 10v11h14V10M9 21v-7h6v7"/>',
 '@budget:comfort':'<path d="M4 10h13v5a5 5 0 0 1-5 5H9a5 5 0 0 1-5-5zM17 11h2a3 3 0 0 1 0 6h-2M7 3v3M12 3v3"/>',
 '@budget:leisure':'<circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M2 12h2M20 12h2M5 5l1.5 1.5M17.5 17.5 19 19M5 19l1.5-1.5M17.5 6.5 19 5"/>',
 '@budget:learning':'<path d="M12 6C9 3 5 3 2 4v15c4-1 7 0 10 2 3-2 6-3 10-2V4c-3-1-7-1-10 2ZM12 6v15"/>',
 '@budget:other':'<rect x="3" y="3" width="7" height="7" rx="2"/><rect x="14" y="3" width="7" height="7" rx="2"/><rect x="3" y="14" width="7" height="7" rx="2"/><rect x="14" y="14" width="7" height="7" rx="2"/>'
};
function budgetGroupIcon(id){return `<span class="budget-group-icon" aria-hidden="true"><svg viewBox="0 0 24 24">${BUDGET_GROUP_ICONS[id]||''}</svg></span>`}
const BUDGET_RECOMMENDED=Object.fromEntries(BUDGET_GROUPS.map(group=>[group.id,group.recommended]));
function budgetPlan(){const plan=ACCOUNT_PREFERENCES.budget_plan;return plan&&BUDGET_GROUPS.every(group=>typeof plan[group.id]==='number')?plan:BUDGET_RECOMMENDED}
// A month without saved limits follows the account plan: a share of that month's income per group.
function budgetFollowsPlan(key){return !Object.keys(BUDGETS[key]||{}).length}
function savedBudgetGroups(key){
 if(budgetFollowsPlan(key)){const income=budgetIncomeFor(key),plan=budgetPlan();return Object.fromEntries(BUDGET_GROUPS.map(group=>[group.id,Math.round(income*plan[group.id])/100]))}
 const raw=BUDGETS[key]||{},values=Object.fromEntries(BUDGET_GROUPS.map(group=>[group.id,0]));
 Object.entries(raw).forEach(([name,value])=>{if(!BUDGET_GROUP_IDS.has(name))values[budgetGroupFor(name)]+=+value||0});
 BUDGET_GROUPS.forEach(group=>{if(Object.hasOwn(raw,group.id))values[group.id]=+raw[group.id]||0;values[group.id]=Math.round(values[group.id]*100)/100});return values;
}
const BUDGET_COLORS=['#5aa9ff','#3ddc97','#f5b94a','#a98bff','#8592a4'];
function categoryTotals(monthValue){const totals={};DATA.filter(item=>item.date.startsWith(monthValue)).forEach(item=>totals[budgetGroupFor(item.category)]=(totals[budgetGroupFor(item.category)]||0)+item.amount);return totals}
function budgetLevel(used,limit){if(!limit)return 'unset';const ratio=used/limit;return ratio>1?'over':ratio>=.8?'warning':'safe'}
function budgetIncomeFor(key){const mode=ACCOUNT_PREFERENCES.income_modes?.[key]||'auto',salary=scheduledSalaryBasis(key),declared=+(incomeByMonth[key]||0),imported=INCOME_ENTRIES.filter(x=>x.date.startsWith(key)).reduce((sum,x)=>sum+x.amount,0);return Math.max(0,mode==='scheduled'||mode==='auto'&&salary.active?salary.expected:mode==='declared'||mode==='auto'&&declared>0?declared:imported)}
function budgetValues(key){return {...savedBudgetGroups(key),...budgetDrafts.get(key)}}
function budgetCategories(){return BUDGET_GROUPS.map(group=>group.id)}
function budgetPercent(value){return value.toLocaleString('pt-BR',{maximumFractionDigits:1})+'%'}
function fillBudgetMonths(){
 const selected=budgetMonth.value||month.value;
 const values=new Set([...Object.keys(BUDGETS),...Object.keys(incomeByMonth),...budgetDrafts.keys(),...DATA.map(item=>item.date.slice(0,7)),localDateValue().slice(0,7)]);
 budgetMonth.innerHTML='';[...values].sort().reverse().forEach(value=>budgetMonth.add(new Option(monthLabel(value)+(budgetDrafts.has(value)?' · em edição':''),value)));
 budgetMonth.value=values.has(selected)?selected:[...values].sort().reverse()[0];budgetMonth.disabled=budgetSaving;
}
function paintBudgetPlan(){
 const key=budgetMonth.value,income=budgetIncomeFor(key),follows=budgetFollowsPlan(key),values=budgetValues(key);
 const shares=BUDGET_GROUPS.map((group,index)=>({id:group.id,label:group.label,color:BUDGET_COLORS[index%BUDGET_COLORS.length],recommended:group.recommended,
  pct:income?(+values[group.id]||0)/income*100:budgetPlan()[group.id]}));
 const used=shares.reduce((sum,item)=>sum+item.pct,0),free=Math.max(0,100-used),scale=Math.max(100,used);
 document.querySelector('#budgetPlanBar').innerHTML=shares.filter(item=>item.pct>0).map(item=>`<i style="width:${item.pct/scale*100}%;background:${item.color}" title="${esc(item.label)}: ${budgetPercent(item.pct)}"></i>`).join('')+(free>0?`<i class="budget-plan-free" style="width:${free/scale*100}%" title="Guardar ou investir: ${budgetPercent(free)}"></i>`:'');
 document.querySelector('#budgetPlanBar').setAttribute('aria-label','Plano: '+shares.map(item=>`${item.label} ${budgetPercent(item.pct)}`).join(', ')+`, guardar ou investir ${budgetPercent(free)}`);
 document.querySelector('#budgetPlanLegend').innerHTML=shares.map(item=>`<div><i style="background:${item.color}"></i><span>${esc(item.label)}</span><b>${budgetPercent(item.pct)}</b><small>${Math.abs(item.pct-item.recommended)<.05?'recomendado':'recomendado '+item.recommended+'%'}</small></div>`).join('')+`<div class="budget-plan-save"><i></i><span>Guardar ou investir</span><b>${budgetPercent(free)}</b><small>${used>100?'renda toda comprometida':'o que sobra'}</small></div>`;
 const note=document.querySelector('#budgetPlanNote');
 note.textContent=!income?'Cadastre sua renda em Ganhos e fixos: os limites do plano passam a ser calculados sozinhos todo mês.':follows?`Este mês segue o seu plano, calculado sobre ${brl(income)} de renda. Ajuste os grupos abaixo e salve para mudar o plano de todos os meses.`:'Este mês tem limites próprios, em reais. Os outros meses continuam seguindo o plano.';
 document.querySelector('#budgetPlanFollow').hidden=follows||budgetSaving;
 const recommended=BUDGET_GROUPS.every(group=>Math.abs((income?(+values[group.id]||0)/income*100:budgetPlan()[group.id])-group.recommended)<.05);
 document.querySelector('#budgetPlanReset').disabled=budgetSaving||!income||recommended;
}
function paintBudgetOverview(){
 paintBudgetPlan();
 const key=budgetMonth.value,configured=budgetValues(key),totals=categoryTotals(key),income=budgetIncomeFor(key),categories=budgetCategories(key);
 const total=Object.values(configured).reduce((sum,value)=>sum+(+value||0),0),used=Object.entries(totals).filter(([name])=>configured[name]>0).reduce((sum,[,value])=>sum+value,0);
 document.querySelector('#budgetIncome').textContent=brl(income);
 document.querySelector('#budgetTotal').textContent=brl(total);document.querySelector('#budgetUsed').textContent=brl(used);
 const available=document.querySelector('#budgetAvailable');available.textContent=brl(total-used);available.className=total>=used?'positive':'negative';
 document.querySelector('#budgetAllocationPercent').textContent=income?budgetPercent(total/income*100):brl(total);
 document.querySelector('#budgetDonut span').textContent=income?'da renda planejada':'em limites mensais';
 const note=document.querySelector('#budgetAllocationNote');note.textContent=income?(total>income?`${brl(total-income)} acima da renda. Ajuste as barras para equilibrar.`:`${brl(income-total)} da renda ainda livres para distribuir.`):'Sem renda cadastrada? Você pode ajustar os limites em reais.';note.classList.toggle('negative',income>0&&total>income);
 const unbounded=Object.entries(totals).filter(([name])=>!(configured[name]>0)).reduce((sum,[,value])=>sum+value,0);
 document.querySelector('#budgetUnbounded').textContent=unbounded?`${brl(unbounded)} gastos em grupos sem limite, fora do resumo acima.`:'';
 let cursor=0;const denominator=Math.max(total,income),segments=[],active=categories.filter(name=>configured[name]>0);
 active.forEach(name=>{const start=cursor;cursor+=configured[name]/denominator*100;segments.push(`${BUDGET_COLORS[categories.indexOf(name)%BUDGET_COLORS.length]} ${start}% ${cursor}%`)});
 if(cursor<100)segments.push(`var(--surface) ${cursor}% 100%`);
 const donut=document.querySelector('#budgetDonut');donut.style.background=segments.length?`conic-gradient(${segments.join(',')})`:'var(--surface)';donut.setAttribute('aria-label',`Distribuição dos limites: ${brl(total)}${income?', '+budgetPercent(total/income*100)+' da renda':''}`);
 document.querySelector('#budgetLegend').innerHTML=active.length?active.map(name=>`<div><i style="background:${BUDGET_COLORS[categories.indexOf(name)%BUDGET_COLORS.length]}"></i><span>${esc(budgetGroupLabel(name))}</span><b>${brl(configured[name])}</b></div>`).join(''):'<p class="quiet">Comece arrastando a barra de uma categoria.</p>';
 const count=Object.keys(budgetDrafts.get(key)||{}).length;
 document.querySelector('#budgetDraftHint').textContent=budgetSaveError||'A prévia só vira seu limite ao salvar.';
 document.querySelector('#budgetSavebar').hidden=!count;document.querySelector('#budgetDraftCount').textContent=`${count} ${count===1?'limite ajustado':'limites ajustados'}`;
 document.querySelector('#saveBudgetChanges').textContent=budgetSaving?'Salvando…':'Salvar alterações';
 document.querySelector('#saveBudgetChanges').disabled=budgetSaving;document.querySelector('#discardBudgetChanges').disabled=budgetSaving;
}
function budgetSliderScale(limit,income,spent){
 return income?{max:Math.max(100,Math.ceil(limit/income*100/25)*25),step:0.1,value:limit/income*100}:{max:Math.min(10000000,Math.max(5000,Math.ceil(Math.max(limit,spent)/500)*500)),step:10,value:limit};
}
function paintBudgetRow(row,limit,source){
 const name=row.dataset.budgetCategory,income=budgetIncomeFor(budgetMonth.value),spent=categoryTotals(budgetMonth.value)[name]||0,level=budgetLevel(spent,limit),ratio=limit?spent/limit*100:0;
 row.classList.remove('safe','warning','over','unset');row.classList.add(level);row.classList.toggle('is-edited',Object.hasOwn(budgetDrafts.get(budgetMonth.value)||{},name));
 row.querySelector('[data-usage-label]').textContent=limit?`${budgetPercent(ratio)} do limite já usado`:'Sem limite definido';
 const number=row.querySelector('[data-limit-category]'),percent=document.querySelector('#budgetUnit').value==='percent';
 if(source!==number)number.value=percent?(income?(limit/income*100).toFixed(2):''):limit.toFixed(2);
 const slider=row.querySelector('[data-budget-slider]'),value=income?limit/income*100:limit;
 // Keep the scale stable under the pointer; expand it only for an exact typed value.
 if(value>+slider.max)slider.max=budgetSliderScale(limit,income,spent).max;
 if(source!==slider)slider.value=value;
 slider.style.setProperty('--slider-fill',Math.min(100,value/+slider.max*100)+'%');
 slider.setAttribute('aria-valuetext',`${brl(limit)}${income?', '+budgetPercent(value)+' da renda':''}`);
 row.querySelector('[data-slider-value]').textContent=income?budgetPercent(value)+' da renda':brl(limit);
 row.querySelector('[data-scale-max]').textContent=income?budgetPercent(+slider.max):brl(+slider.max);
 row.querySelector('[data-budget-remaining]').textContent=limit?brl(limit-spent):'—';row.querySelector('[data-budget-remaining]').classList.toggle('negative',limit>0&&spent>limit);
 row.querySelector('.limit-track i').style.width=Math.min(100,Math.max(0,ratio))+'%';
 row.querySelector('[data-budget-status]').textContent=level==='over'?`${brl(spent-limit)} acima do limite`:level==='warning'?'Atenção: perto do limite':limit?'Dentro do limite':'Defina quanto quer gastar';
}
function renderBudgetPanel(){
 fillBudgetMonths();const key=budgetMonth.value,configured=budgetValues(key),income=budgetIncomeFor(key),totals=categoryTotals(key),categories=budgetCategories(key),unit=document.querySelector('#budgetUnit');
 unit.querySelector('[value="percent"]').disabled=!income;if(!income)unit.value='money';else if(!unit.dataset.chosen)unit.value='percent';unit.disabled=budgetSaving;const percent=unit.value==='percent';
 document.querySelector('#budgetEditHint').textContent=income?'O gráfico acompanha seus ajustes. Salve quando estiver do seu jeito.':'Arraste para ajustar em reais. Para usar percentuais, cadastre sua renda em Ganhos e fixos.';
 limitsList.innerHTML=categories.map((name,index)=>{
  const group=BUDGET_GROUPS.find(group=>group.id===name),label=group.label;
  const limit=+configured[name]||0,scale=budgetSliderScale(limit,income,totals[name]||0),color=BUDGET_COLORS[index%BUDGET_COLORS.length];
  return `<article class="limit-row" data-budget-category="${esc(name)}" style="--category-color:${color}"><div class="budget-card-heading"><div class="budget-category"><strong>${budgetGroupIcon(name)}<span>${esc(label)}</span></strong><p class="budget-group-description">${esc(group.description)}</p><span class="budget-recommended">Recomendado: ${group.recommended}% da renda</span><span data-usage-label></span></div><label class="budget-limit-input"><small>${percent?'Limite em %':'Limite em R$'}</small><input aria-label="${percent?'Percentual da renda':'Limite em reais'} para ${esc(label)}" data-limit-category="${esc(name)}" type="number" min="0" max="${percent?10000000/income*100:10000000}" step="0.01" inputmode="decimal" ${budgetSaving?'disabled':''}></label></div><div class="budget-slider-area"><div class="budget-slider-label"><span>${income?'Distribuição da renda':'Seu limite mensal'}</span><output data-slider-value></output></div><input class="budget-slider" data-budget-slider="${esc(name)}" type="range" min="0" max="${scale.max}" step="${scale.step}" value="${scale.value}" aria-label="Ajustar limite de ${esc(label)}" ${budgetSaving?'disabled':''}><div class="budget-slider-scale" aria-hidden="true"><span>${income?'0%':'R$ 0'}</span><span data-scale-max></span></div></div><div class="budget-card-stats"><div><small>Já gastou</small><strong>${brl(totals[name]||0)}</strong></div><div><small>Ainda pode gastar</small><strong data-budget-remaining></strong></div><div class="limit-track" aria-hidden="true"><i></i></div></div><div class="limit-foot"><span data-budget-status></span><details class="budget-actions"><summary>Opções</summary><div><button type="button" class="text-button" data-remove-limit="${esc(name)}" ${budgetSaving?'disabled':''}>Remover limite</button></div></details></div><details class="budget-group-details"><summary>Ver gastos do grupo</summary>${budgetGroupBreakdown(name,key)}</details></article>`;
 }).join('');
 limitsList.querySelectorAll('[data-budget-category]').forEach(row=>paintBudgetRow(row,+configured[row.dataset.budgetCategory]||0));paintBudgetOverview();renderBudgetHistory();renderBudgetCategoryTools();
}
function budgetGroupBreakdown(id,key){
 const names=[...new Set([...ALL_CATEGORIES,...DATA.filter(item=>item.date.startsWith(key)).map(item=>item.category),...Object.keys(BUDGETS[key]||{}).filter(name=>!BUDGET_GROUP_IDS.has(name))])].filter(name=>budgetGroupFor(name)===id);
 const totals={};DATA.filter(item=>item.date.startsWith(key)).forEach(item=>totals[item.category]=(totals[item.category]||0)+item.amount);
 return '<ul>'+names.map(name=>`<li><span>${esc(name)}</span><strong>${brl(totals[name]||0)}</strong></li>`).join('')+'</ul>';
}
function renderBudgetCategoryTools(){
 const custom=ALL_CATEGORIES.filter(name=>!DEFAULT_CATEGORIES.has(name));
 document.querySelector('#budgetCustomCategories').innerHTML=custom.map(name=>`<div><span>${esc(name)} <small>${esc(budgetGroupLabel(budgetGroupFor(name)))}</small></span><button class="text-button" type="button" data-edit-category="${esc(name)}">Renomear</button><button class="text-button danger-text" type="button" data-remove-category="${esc(name)}">Excluir</button></div>`).join('');
}
function renderBudgetHistory(){
 const months=[...new Set([...Object.keys(BUDGETS),...DATA.map(item=>item.date.slice(0,7))])].sort().reverse();document.querySelector('#budgetHistoryList').innerHTML=months.length?months.map(value=>{const limits=savedBudgetGroups(value),spentByCategory=categoryTotals(value),limit=Object.values(limits).reduce((s,v)=>s+(+v||0),0),spent=Object.entries(spentByCategory).filter(([name])=>limits[name]>0).reduce((s,[,v])=>s+v,0);return `<button class="history-month" data-history-month="${value}" ${budgetSaving?'disabled':''}><span>${monthLabel(value)}</span><strong>${brl(limit)}</strong><span>${brl(spent)} gastos</span><b class="${limit-spent>=0?'positive':'negative'}">${brl(limit-spent)}</b></button>`}).join(''):'<div class="empty">O histórico aparecerá depois do primeiro limite.</div>';
}
function previewBudgetLimit(input){
 if(budgetSaving||!input.validity.valid)return;
 const key=budgetMonth.value,row=input.closest('[data-budget-category]'),name=row.dataset.budgetCategory,income=budgetIncomeFor(key),percent=input.matches('[data-budget-slider]')?income>0:document.querySelector('#budgetUnit').value==='percent';
 const value=Math.min(10000000,Math.round(Math.max(0,+input.value||0)*(percent?income/100:1)*100)/100);
 const drafts=budgetDrafts.get(key)||{};
 if(value===(+savedBudgetGroups(key)[name]||0))delete drafts[name];else drafts[name]=value;
 if(Object.keys(drafts).length)budgetDrafts.set(key,drafts);else budgetDrafts.delete(key);
 budgetSaveError='';paintBudgetRow(row,value,input);paintBudgetOverview();limitsMessage.hidden=true;
 const option=budgetMonth.selectedOptions[0];if(option)option.textContent=monthLabel(key)+(budgetDrafts.has(key)?' · em edição':'');
}
limitsList.addEventListener('input',event=>{const input=event.target.closest('[data-limit-category],[data-budget-slider]');if(input)previewBudgetLimit(input)});
document.querySelector('#discardBudgetChanges').addEventListener('click',()=>{budgetDrafts.delete(budgetMonth.value);budgetSaveError='';limitsMessage.hidden=true;renderBudgetPanel()});
document.querySelector('#saveBudgetChanges').addEventListener('click',async()=>{
 if(budgetSaving)return;
 if(!canWrite){budgetSaveError='Sem conexão. Seus ajustes continuam aqui; tente salvar quando a conexão voltar.';paintBudgetOverview();limitsMessage.textContent=localOnlyMessage();limitsMessage.className='message error';limitsMessage.hidden=false;return}
 for(const input of limitsList.querySelectorAll('[data-limit-category]'))if(!input.reportValidity())return;
 const key=budgetMonth.value,changes=Object.entries(budgetDrafts.get(key)||{});if(!changes.length)return;
 budgetSaving=true;budgetSaveError='';renderBudgetPanel();let saved=0;
 try{
  const income=budgetIncomeFor(key);
  if(budgetFollowsPlan(key)&&income>0){
   const values=budgetValues(key),plan=Object.fromEntries(BUDGET_GROUPS.map(group=>[group.id,Math.round((+values[group.id]||0)/income*10000)/100]));
   const response=await fetch('/api/preferences',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({budget_plan:plan})}),result=await response.json();
   if(!response.ok)throw Error(result.error||'Não foi possível salvar o plano.');
   ACCOUNT_PREFERENCES.budget_plan=result.preferences?.budget_plan||plan;saved=changes.length;budgetDrafts.delete(key);
   limitsMessage.textContent='Pronto! Seu plano foi salvo e vale para todos os meses sem limites próprios.';limitsMessage.className='message ok';return;
  }
  for(const [category,limit] of changes){
   const response=await fetch('/api/budgets',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({month:key,category,limit})}),result=await response.json();
   if(!response.ok)throw Error(result.error||'Não foi possível salvar os limites.');
   BUDGETS[key]??={};BUDGETS[key][category]=limit;saved++;
   const drafts=budgetDrafts.get(key);if(drafts){delete drafts[category];if(!Object.keys(drafts).length)budgetDrafts.delete(key)}
  }
  limitsMessage.textContent='Pronto! Seus limites foram salvos.';limitsMessage.className='message ok';
 }catch(error){budgetSaveError='Não foi possível salvar tudo. Os ajustes pendentes foram mantidos. Tente novamente.';limitsMessage.textContent=`${saved?`${saved} limite(s) salvo(s). `:''}${error.message} Seus ajustes pendentes continuam na prévia. Tente salvar novamente.`;limitsMessage.className='message error'}
 finally{budgetSaving=false;render();renderBudgetPanel();limitsMessage.hidden=false;document.querySelector(budgetDrafts.has(key)?'#saveBudgetChanges':'#budgetUnit').focus({preventScroll:true})}
});
window.addEventListener('beforeunload',event=>{if(budgetDrafts.size){event.preventDefault();event.returnValue=''}});
document.querySelector('.budget-page').addEventListener('click',async event=>{if(budgetSaving)return;const limitButton=event.target.closest('[data-remove-limit]'),categoryButton=event.target.closest('[data-remove-category]'),editButton=event.target.closest('[data-edit-category]');if(editButton){const oldName=editButton.dataset.editCategory,newName=prompt('Novo nome da categoria:',oldName)?.trim();if(!newName||newName===oldName)return;const response=await fetch(`/api/categories/${encodeURIComponent(oldName)}`,{method:'PUT',headers:{'Content-Type':'application/json'},body:JSON.stringify({name:newName})}),result=await response.json();if(!response.ok)return alert(result.error||'Não foi possível renomear');ALL_CATEGORIES=ALL_CATEGORIES.map(item=>item===oldName?result.category:item);DATA.forEach(item=>{if(item.category===oldName)item.category=result.category});Object.values(BUDGETS).forEach(values=>{if(Object.hasOwn(values,oldName)){values[result.category]=values[oldName];delete values[oldName]}});for(const drafts of budgetDrafts.values()){if(Object.hasOwn(drafts,oldName)){drafts[result.category]=drafts[oldName];delete drafts[oldName]}}refreshCategoryOptions();render();renderBudgetPanel();return}if(!limitButton&&!categoryButton)return;const name=(limitButton?.dataset.removeLimit||categoryButton?.dataset.removeCategory);if(limitButton){const row=limitButton.closest('[data-budget-category]'),input=row.querySelector('[data-limit-category]');input.value=0;previewBudgetLimit(input);row.querySelector('details').open=false;return}if(!confirm(categoryButton?`Excluir a categoria “${name}”?`:`Remover o limite de “${name}”?`))return;const endpoint=categoryButton?`/api/categories/${encodeURIComponent(name)}`:`/api/budgets/${budgetMonth.value}/${encodeURIComponent(name)}`;const response=await fetch(endpoint,{method:'DELETE'}),result=await response.json();if(!response.ok)return alert(result.error||'Não foi possível excluir');if(categoryButton){ALL_CATEGORIES=ALL_CATEGORIES.filter(item=>item!==name);for(const [key,drafts] of budgetDrafts){delete drafts[name];if(!Object.keys(drafts).length)budgetDrafts.delete(key)}}(categoryButton?Object.values(BUDGETS):[BUDGETS[budgetMonth.value]||{}]).forEach(values=>delete values[name]);render();renderBudgetPanel();refreshCategoryOptions()});
document.querySelector('#budgetHistoryList').addEventListener('click',event=>{const button=event.target.closest('[data-history-month]');if(button){budgetMonth.value=button.dataset.historyMonth;renderBudgetPanel()}});budgetMonth.addEventListener('change',()=>{budgetSaveError='';limitsMessage.hidden=true;renderBudgetPanel()});document.querySelector('#budgetUnit').addEventListener('change',event=>{event.target.dataset.chosen='1';renderBudgetPanel()});
const categoryModal=document.querySelector('#categoryModal'),categoryForm=document.querySelector('#categoryForm');document.querySelector('#newCategoryButton').onclick=()=>{categoryModal.hidden=false;categoryForm.name.focus()};document.querySelector('#closeCategoryModal').onclick=()=>categoryModal.hidden=true;categoryForm.addEventListener('submit',async event=>{event.preventDefault();const name=categoryForm.name.value.trim(),message=document.querySelector('#categoryMessage');try{const response=await fetch('/api/categories',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({name})}),result=await response.json();if(!response.ok)throw new Error(result.error);if(!ALL_CATEGORIES.includes(result.category))ALL_CATEGORIES.push(result.category);categoryModal.hidden=true;categoryForm.reset();refreshCategoryOptions();renderBudgetPanel()}catch(error){message.textContent=error.message;message.className='message error';message.hidden=false}});
const DEFAULT_CATEGORIES=new Set(["Alimentação","Mercado","Transporte","Moradia","Saúde","Educação","Lazer","Compras","Assinaturas","Contas","Viagem","Presentes","Outros"]);
function refreshCategoryOptions(){const selects=[form.elements.category,...document.querySelectorAll('.statement-category')];selects.forEach(select=>{if(!select)return;const current=select.value;select.innerHTML=ALL_CATEGORIES.map(name=>`<option value="${esc(name)}">${esc(name)}</option>`).join('');if(ALL_CATEGORIES.includes(current))select.value=current})}
function renderDashboardBudgets(){
 const totals=categoryTotals(month.value),configured=savedBudgetGroups(month.value),items=Object.entries(configured).filter(([,limit])=>+limit>0).sort((a,b)=>(totals[b[0]]||0)/(+b[1]||1)-(totals[a[0]]||0)/(+a[1]||1));
 const total=items.reduce((sum,[,limit])=>sum+(+limit||0),0),used=items.reduce((sum,[name])=>sum+(totals[name]||0),0),remaining=total-used,risk=items.filter(([name,limit])=>(totals[name]||0)/(+limit||1)>=.8).length;
 document.querySelector('#budgetTotalSummary').textContent=brl(total);document.querySelector('#budgetUsedSummary').textContent=brl(used);const remainingEl=document.querySelector('#budgetRemainingSummary');remainingEl.textContent=total?brl(remaining):'Sem limites';remainingEl.className=remaining>=0?'positive':'negative';document.querySelector('#budgetRiskSummary').textContent=risk?`${risk} ${risk===1?'grupo':'grupos'}`:'Tudo certo';
 document.querySelector('#budgetList').innerHTML=items.length?items.map(([name,rawLimit])=>{const limit=+rawLimit,used=totals[name]||0,remaining=limit-used,level=budgetLevel(used,limit),width=Math.min(used/limit*100,100);return `<div class="dashboard-limit ${level}"><div class="bar-head"><strong>${esc(budgetGroupLabel(name))}</strong><span>${brl(used)} de ${brl(limit)}</span></div><div class="limit-track"><i style="width:${width}%"></i></div><div class="budget-status ${level}">${remaining>=0?`${brl(remaining)} disponíveis`:`${brl(-remaining)} acima do limite`}</div></div>`}).join(''):'<div class="empty">Defina seus limites em Planejamento.</div>';
 document.querySelector('#budgetAlerts').innerHTML=items.filter(([name,limit])=>(totals[name]||0)/limit>=.8).map(([name,limit])=>{const used=totals[name]||0,level=budgetLevel(used,limit);return `<div class="alert ${level}">${esc(budgetGroupLabel(name))}: ${used>limit?`${brl(used-limit)} acima do limite`:`${brl(limit-used)} disponíveis`}</div>`}).join('');
}
const baseRender=render;render=function(){baseRender();renderDashboardBudgets()};
renderDashboardBudgets();
document.querySelector('#quickExpense').addEventListener('click',()=>document.querySelector('[data-panel="entryPanel"]').click());
document.querySelectorAll('[data-open-panel]').forEach(button=>button.addEventListener('click',()=>document.querySelector(`[data-panel="${button.dataset.openPanel}"]`)?.click()));

document.querySelector('#budgetPlanReset').addEventListener('click',()=>{
 if(budgetSaving)return;const key=budgetMonth.value,income=budgetIncomeFor(key);if(!income)return;
 const saved=savedBudgetGroups(key),drafts={};
 BUDGET_GROUPS.forEach(group=>{const value=Math.round(income*group.recommended)/100;if(value!==(+saved[group.id]||0))drafts[group.id]=value});
 if(Object.keys(drafts).length)budgetDrafts.set(key,drafts);else budgetDrafts.delete(key);
 budgetSaveError='';limitsMessage.hidden=true;renderBudgetPanel();
});
document.querySelector('#budgetPlanFollow').addEventListener('click',async()=>{
 const key=budgetMonth.value,names=Object.keys(BUDGETS[key]||{});if(budgetSaving||!names.length)return;
 if(!confirm(`Remover os limites próprios de ${monthLabel(key)} e seguir o plano padrão?`))return;
 if(!canWrite){alert(localOnlyMessage());return}
 budgetSaving=true;renderBudgetPanel();
 try{for(const name of names){const response=await fetch(`/api/budgets/${key}/${encodeURIComponent(name)}`,{method:'DELETE'}),result=await response.json();if(!response.ok)throw Error(result.error||'Não foi possível remover os limites.');delete BUDGETS[key][name]}
  delete BUDGETS[key];budgetDrafts.delete(key);limitsMessage.textContent='Este mês voltou a seguir o plano padrão.';limitsMessage.className='message ok'}
 catch(error){limitsMessage.textContent=error.message;limitsMessage.className='message error'}
 finally{budgetSaving=false;render();renderBudgetPanel();limitsMessage.hidden=false}
});
