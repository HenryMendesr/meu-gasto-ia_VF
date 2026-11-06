const suitabilityQuestions=__SUITABILITY_QUESTIONS__;
const suitabilityForm=document.querySelector('#suitabilityForm');
function renderSuitability(){
 const result=portfolio.preferences?.investor_profile,box=document.querySelector('#suitabilityResult');
 if(!result){box.textContent='';document.querySelector('#startSuitability').innerHTML='Descobrir meu perfil de investidor <span aria-hidden="true">→</span>';return}
 const labels={capacity:'Capacidade financeira',knowledge:'Conhecimento e experiência',tolerance:'Tolerância a risco'};
 const age=Date.now()-new Date(result.completed_at).getTime(),review=result.version!==1||!Number.isFinite(age)||age>365*86400000;
 box.innerHTML=`<h4>Seu perfil educativo: ${iEsc(result.profile)}</h4><p>Respondido em ${iEsc(formatStamp(result.completed_at))}. ${review?'Reavalie seu perfil: a análise tem mais de um ano ou mudou de versão.':'Reavalie sempre que sua situação mudar.'}</p><ul>${Object.entries(labels).map(([key,label])=>`<li>${label}: ${iEsc(result.scores?.[key])}/100</li>`).join('')}</ul><p>Índices internos do app; não representam probabilidade de acerto ou retorno.</p><ul>${(result.reasons||[]).map(reason=>`<li>${iEsc(reason)}</li>`).join('')}</ul><p>${iEsc({Conservador:'Priorize preservação e liquidez compatíveis com seu objetivo. Mesmo renda fixa tem riscos.',Moderado:'Você sinaliza espaço para oscilações, respeitando prazos, liquidez e diversificação.',Arrojado:'Você sinaliza capacidade e disposição para perdas relevantes. Isso não torna qualquer produto adequado.'}[result.profile]||'')}</p>`;
 document.querySelector('#startSuitability').textContent='Refazer análise de perfil';
}
function suitabilityProgress(){const count=suitabilityQuestions.filter(q=>suitabilityForm.querySelector(`input[name="${q.id}"]:checked`)).length;document.querySelector('#suitabilityProgress').textContent=`${count} de ${suitabilityQuestions.length} perguntas respondidas`;document.querySelector('#suitabilityMeter').value=count}
document.querySelector('#startSuitability').onclick=()=>{
 const old=portfolio.preferences?.investor_profile,answers=old?.version===1?old.answers||{}:{};
 document.querySelector('#suitabilityQuestions').innerHTML=suitabilityQuestions.map((q,i)=>`<fieldset><legend><small>${iEsc(q.section)} · ${i+1}/${suitabilityQuestions.length}</small><br>${iEsc(q.title)}</legend>${q.options.map((option,value)=>`<label><input type="radio" name="${q.id}" value="${value}" required ${answers[q.id]===value?'checked':''}> <span>${iEsc(option)}</span></label>`).join('')}</fieldset>`).join('');
 suitabilityForm.hidden=false;document.querySelector('#suitabilityConfirm').checked=false;document.querySelector('#suitabilityError').textContent='';suitabilityProgress();suitabilityForm.querySelector('input').focus();
};
suitabilityForm.addEventListener('change',suitabilityProgress);
document.querySelector('#cancelSuitability').onclick=()=>{suitabilityForm.hidden=true;document.querySelector('#startSuitability').focus()};
suitabilityForm.onsubmit=async event=>{event.preventDefault();const button=suitabilityForm.querySelector('[type="submit"]'),error=document.querySelector('#suitabilityError');error.textContent='';if(!canWrite){error.textContent=localOnlyMessage();return}button.disabled=true;try{
 const answers=Object.fromEntries(suitabilityQuestions.map(q=>[q.id,Number(new FormData(suitabilityForm).get(q.id))]));
 const result=await trustRequest('/api/preferences',{investor_profile:{version:1,answers}});
 portfolio.preferences=result.preferences;ACCOUNT_PREFERENCES=result.preferences;suitabilityForm.hidden=true;renderSuitability();document.querySelector('#startSuitability').focus();
 }catch(e){error.textContent=e.message}finally{button.disabled=false}};
document.addEventListener('finance-updated',renderSuitability);
renderSuitability();
