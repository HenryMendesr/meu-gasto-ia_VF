(() => {
  const dialog = document.querySelector('#investorEducation');
  const body = document.querySelector('#educationBody');
  const errorBox = document.querySelector('#educationError');
  const nav = dialog.querySelector('nav');
  const panel = document.querySelector('#investmentsPanel');
  const profiles = {
    conservative: ['Conservador', 'Você prioriza segurança, previsibilidade e acesso ao dinheiro. Comece entendendo liquidez, reserva de emergência e risco de crédito antes de comparar taxas.'],
    moderate: ['Moderado', 'Você busca um equilíbrio entre segurança e crescimento, e aceita alguma oscilação. Separe o dinheiro de curto prazo dos objetivos que podem esperar e entenda os riscos de cada produto.'],
    aggressive: ['Arrojado', 'Você aceita oscilações e tem um horizonte mais longo para buscar crescimento. Isso não elimina riscos: diversificação, reserva de emergência e limites de exposição continuam importantes.'],
  };
  const questions = [
    ['goal', 'Qual é o principal objetivo desse dinheiro?', ['Montar uma reserva para imprevistos', 'Realizar uma compra ou um projeto', 'Construir patrimônio no longo prazo']],
    ['horizon', 'Quando você pretende usar esse dinheiro?', ['Em até 1 ano', 'Entre 1 e 5 anos', 'Daqui a mais de 5 anos']],
    ['liquidity', 'Você pode precisar resgatar antes do prazo?', ['Sim, preciso ter acesso a qualquer momento', 'Talvez precise de uma parte', 'Posso deixar esse valor até o vencimento']],
    ['loss', 'Como reagiria se o investimento caísse 10%?', ['Ficaria desconfortável e buscaria sair', 'Reavaliaria antes de decidir', 'Aceitaria a oscilação dentro do meu plano']],
    ['knowledge', 'Qual é sua experiência com investimentos?', ['Estou aprendendo sobre juros e riscos', 'Já conheço renda fixa e suas condições', 'Já investi em produtos com oscilações']],
  ];
  const lessons = {
    cdb: ['Você empresta dinheiro a um banco e recebe juros em troca.', 'Pode pagar uma taxa fixa, uma parte do CDI ou inflação mais juros. Os juros se acumulam sobre o saldo quando reinvestidos.', 'O risco depende do banco emissor. Há cobertura do FGC dentro dos limites e condições: até R$ 250 mil por CPF/CNPJ por instituição ou conglomerado, incluindo juros, com teto global de R$ 1 milhão a cada 4 anos.', 'Alguns têm liquidez diária; outros só permitem resgate no vencimento. Confira a oferta.', 'IR regressivo sobre os rendimentos e IOF em resgates antes de 30 dias.'],
    lci: ['Você aplica em um título bancário ligado ao financiamento imobiliário.', 'A remuneração pode ser prefixada, ligada ao CDI ou à inflação. Compare o rendimento líquido e a carência.', 'Risco do banco emissor, com FGC nos mesmos limites dos CDBs. A garantia não significa acesso imediato ao dinheiro.', 'Pode haver carência e bloqueio até o vencimento. Não presuma liquidez diária.', 'Rendimentos isentos de IR para pessoa física nas regras consideradas nesta simulação.'],
    lca: ['Você aplica em um título bancário ligado ao financiamento do agronegócio.', 'O banco paga juros conforme a taxa contratada. O retorno depende do indexador, do prazo e das condições da emissão.', 'Risco do banco emissor, com FGC nos mesmos limites dos CDBs. Leia as condições da instituição.', 'Pode haver carência e resgate apenas no vencimento.', 'Rendimentos isentos de IR para pessoa física nas regras consideradas nesta simulação.'],
    treasury_fixed: ['Você empresta ao Governo Federal e contrata uma taxa de juros.', 'A taxa prefixada permite projetar o valor bruto ao vencimento. A inflação pode reduzir seu poder de compra.', 'Risco soberano, sem FGC. O preço pode cair se você vender antes do vencimento.', 'Há recompra conforme as regras e horários do Tesouro, pelo preço de mercado do momento.', 'IR regressivo e IOF antes de 30 dias. Pode haver custódia e outras taxas.'],
    treasury_selic: ['É um título público que acompanha a taxa Selic.', 'O saldo acompanha a Selic ao longo do tempo. A taxa futura pode mudar; o simulador usa a referência que você informar.', 'Risco soberano, sem FGC. Costuma oscilar menos que outros títulos públicos, mas não é livre de oscilação.', 'Resgate conforme as regras e horários do Tesouro. O valor de venda depende do mercado.', 'IR regressivo e IOF antes de 30 dias. Pode haver custódia e outras taxas.'],
    treasury_ipca: ['É um título público com rendimento ligado à inflação mais uma taxa real.', 'Combina a variação do IPCA com juros contratados. A projeção depende da inflação futura e de manter o título até o vencimento.', 'Risco soberano, sem FGC. Pode oscilar bastante antes do vencimento, especialmente em prazos longos.', 'Venda antecipada pelo preço de mercado, que pode ser inferior ao valor aplicado.', 'IR regressivo sobre o ganho nominal, incluindo a correção pela inflação. Pode haver custódia.'],
    debenture: ['Você empresta dinheiro a uma empresa para financiar suas atividades.', 'A empresa paga a remuneração prevista na escritura. Pode haver juros periódicos e amortizações, conforme a emissão.', 'Há risco de inadimplência da empresa e de perda do capital. Não tem FGC. Uma taxa alta pode refletir maior risco.', 'A venda antecipada depende de comprador e do preço de mercado. Pode ser difícil sair.', 'Na debênture comum, há IR regressivo sobre os rendimentos e pode haver IOF em prazo inferior a 30 dias.'],
    incentivized: ['É uma debênture elegível a incentivo fiscal, normalmente ligada a projetos de infraestrutura.', 'O retorno segue as condições da emissão, frequentemente inflação mais juros. Confira pagamentos periódicos e amortizações.', 'Risco da empresa e do projeto, sem FGC. A isenção de imposto não torna o investimento mais seguro.', 'Em geral exige planejamento até o vencimento. Venda antecipada pode ter pouca liquidez e perda de valor.', 'Isenção de IR para pessoa física quando a emissão atende aos requisitos legais do incentivo.'],
  };
  let view = '', saving = false, promptShown = false, preferencesReady = false, quizStep = 0, answers = {};
  let returnFocus = null;
  const state = () => ACCOUNT_PREFERENCES.investment_education;
  const error = message => {errorBox.textContent = message; errorBox.hidden = !message;};
  function updateBanner() {
    const label = profiles[state()?.profile]?.[0];
    document.querySelector('#educationBannerText').textContent = label ? `Seu perfil inicial: ${label.toLowerCase()}. Explore as opções e simule seus próximos passos.` : 'Entenda seu perfil, conheça as opções e veja como seu dinheiro pode crescer.';
  }
  async function save(value) {
    if (!canWrite) throw Error(localOnlyMessage());
    const result = await saveTrustPreferences({investment_education: value});
    portfolio.preferences = {...portfolio.preferences, investment_education: result.preferences.investment_education};
    updateBanner();
  }
  async function action(task) {
    if (saving) return;
    saving = true; error(''); dialog.setAttribute('aria-busy', 'true');
    dialog.querySelectorAll('button').forEach(button => button.disabled = true);
    try {await task();} catch (e) {error(e.message);} finally {
      saving = false; dialog.removeAttribute('aria-busy');
      dialog.querySelectorAll('button').forEach(button => button.disabled = false);
    }
  }
  function open(next = 'profile') {
    if (!dialog.open) {returnFocus = document.activeElement; dialog.showModal(); document.body.classList.add('education-open');}
    render(next);
  }
  function close() {
    if (saving) return;
    if (view === 'welcome' && !state()) {action(async () => {await save({experience: 'skipped'}); dialog.close();});}
    else dialog.close();
  }
  dialog.addEventListener('close', () => {document.body.classList.remove('education-open'); returnFocus?.focus({preventScroll: true});});
  dialog.addEventListener('cancel', event => {event.preventDefault(); close();});
  document.querySelector('#closeEducation').onclick = close;
  // Avoid accidental dismissal while answering questions or entering a simulation.
  function render(next) {
    view = next; error(''); nav.hidden = next === 'welcome';
    const titles = {welcome: 'Você já sabe investir?', profile: 'Seu jeito de investir', quiz: 'Vamos conhecer seu perfil', guide: 'Conheça os investimentos', simulator: 'Veja seu dinheiro no futuro'};
    document.querySelector('#educationTitle').textContent = titles[next];
    nav.querySelectorAll('button').forEach(button => {
      const active = button.dataset.educationView === next || (next === 'quiz' && button.dataset.educationView === 'profile');
      button.setAttribute('aria-current', active ? 'page' : 'false');
    });
    if (next === 'welcome') {
      body.innerHTML = '<div class="education-intro"><span class="education-symbol" aria-hidden="true">↗</span><h3>Um primeiro passo para investir com confiança.</h3><p>Se estiver começando, algumas perguntas ajudam você a entender seu perfil. Depois, conheça os investimentos e faça suas próprias simulações.</p><div class="education-choices"><button class="save" data-experience="beginner" type="button"><strong>Estou começando</strong><small>Quero descobrir meu perfil</small></button><button class="secondary" data-experience="experienced" type="button"><strong>Já tenho experiência</strong><small>Quero ir para minha carteira</small></button></div><button type="button" class="text-button" data-experience="skipped">Agora não</button><p class="quote-meta">Você pode voltar pelo botão Meu perfil e guia de investimentos.</p></div>';
    } else if (next === 'profile') {
      const profile = profiles[state()?.profile];
      body.innerHTML = `<div class="education-intro"><span class="eyebrow">${profile ? 'Seu perfil inicial' : 'Autoconhecimento antes da taxa'}</span><h3>${profile ? profile[0] : 'Qual é o seu jeito de investir?'}</h3><p>${profile ? profile[1] : 'Responda cinco perguntas sobre seus objetivos, prazo e relação com o risco. Você pode refazer quando sua situação mudar.'}</p><p class="education-note">Orientação educativa inicial. Este questionário não substitui uma avaliação completa de adequação ao seu perfil nem recomenda um produto específico.</p><div class="actions"><button class="save" type="button" data-start-quiz>${profile ? 'Refazer perguntas' : 'Descobrir meu perfil'}</button><button class="secondary" type="button" data-education-view="guide">Conhecer investimentos →</button></div></div>`;
    } else if (next === 'quiz') renderQuiz();
    else if (next === 'guide') renderGuide();
    else if (next === 'simulator') renderSimulator();
    body.scrollTop = 0;
    // Keep screen-reader and keyboard focus with the newly displayed content.
    const heading = body.querySelector('h3,legend');
    if (heading) {heading.tabIndex = -1; heading.focus({preventScroll: true});}
  }
  function startQuiz() {quizStep = 0; answers = {...(state()?.answers || {})}; render('quiz');}
  function renderQuiz() {
    const [key, title, options] = questions[quizStep];
    body.innerHTML = `<form id="educationQuiz"><div class="education-progress"><span>Pergunta ${quizStep + 1} de ${questions.length}</span><progress value="${quizStep + 1}" max="5" aria-label="Progresso do questionário"></progress></div><fieldset><legend>${title}</legend><div class="education-options">${options.map((text, index) => `<label><input type="radio" name="answer" value="${index}" required ${answers[key] === index ? 'checked' : ''}><span>${text}</span></label>`).join('')}</div></fieldset><div class="education-step-actions"><button type="button" class="secondary" data-quiz-back>${quizStep ? '← Voltar' : 'Cancelar'}</button><button type="submit" class="save">${quizStep === 4 ? 'Ver meu perfil' : 'Continuar →'}</button></div></form>`;
    body.querySelector('[data-quiz-back]').onclick = () => {
      const checked = body.querySelector('input:checked'); if (checked) answers[key] = Number(checked.value);
      if (quizStep) {quizStep--; render('quiz');} else render('profile');
    };
    body.querySelector('form').onsubmit = event => {
      event.preventDefault(); answers[key] = Number(new FormData(event.target).get('answer'));
      if (quizStep < 4) {quizStep++; render('quiz');}
      else action(async () => {await save({experience: state()?.experience === 'experienced' ? 'experienced' : 'beginner', answers}); render('profile');});
    };
  }
  function renderGuide() {
    body.innerHTML = `<p class="education-lead">O melhor ponto de partida é entender como funciona. Compare prazo, risco e rendimento líquido antes de decidir.</p><p class="education-note">São modalidades existentes no Brasil. As taxas e a disponibilidade variam por instituição e emissão; este guia não lista ofertas à venda.</p><div class="education-lessons">${Object.entries(InvestmentSimulator.products).map(([key, product]) => {
      const lesson = lessons[key];
      return `<details class="education-lesson"><summary><span><strong>${product.name}</strong><small>${lesson[0]}</small></span><span aria-hidden="true">＋</span></summary><div class="education-lesson-body"><dl>${['Como ganha dinheiro', 'Riscos e garantias', 'Quando posso resgatar?', 'Impostos'].map((label, i) => `<div><dt>${label}</dt><dd>${lesson[i+1]}</dd></div>`).join('')}</dl><button class="secondary" type="button" data-simulate-product="${key}">Simular ${product.name} →</button></div></details>`;
    }).join('')}</div><p class="quote-meta">Juros compostos são juros sobre o saldo que já inclui rendimentos anteriores. Aportes aumentam o capital; não são lucro. Regras tributárias podem mudar.</p>`;
  }
  function renderSimulator(product = 'cdb') {
    body.innerHTML = `<p class="education-lead">Escolha uma modalidade e use a taxa da oferta que você encontrou para explorar um cenário.</p><form id="educationSimulation" class="education-sim-form"><label class="education-wide">Investimento<select name="product">${Object.entries(InvestmentSimulator.products).map(([key, p]) => `<option value="${key}" ${key === product ? 'selected' : ''}>${p.name}</option>`).join('')}</select></label><label>Rentabilidade<select name="mode"></select></label><label><span id="simulationRateLabel">Taxa ao ano (%)</span><input name="rate" type="text" inputmode="decimal" value="12" required maxlength="8"></label><label id="simulationReferenceField" hidden><span id="simulationReferenceLabel">Índice de referência ao ano (%)</span><input name="reference" type="text" inputmode="decimal" maxlength="8"></label><label>Valor inicial (R$)<input name="initial" type="text" inputmode="decimal" value="1.000,00" maxlength="18" required data-simulation-money></label><label>Aporte mensal (R$)<input name="monthly" type="text" inputmode="decimal" value="200,00" maxlength="18" required data-simulation-money></label><label>Prazo<input name="duration" type="number" min="1" max="600" step="1" value="36" required></label><label>Unidade do prazo<select name="unit"><option value="months">Meses</option><option value="years">Anos</option></select></label><p id="simulationProductNote" class="education-wide quote-meta"></p><div class="education-wide"><button type="submit" class="save">Calcular simulação →</button></div></form><div id="simulationResult" hidden></div><p class="education-note">Simulação educativa para pessoa física, sem garantia de retorno. Taxas digitadas por você; não são cotações ou ofertas atuais. Nenhum valor é aplicado ou retirado da sua carteira.</p>`;
    const form = body.querySelector('form');
    form.elements.product.onchange = () => setModes();
    form.elements.mode.onchange = () => setRateFields(true);
    form.elements.unit.onchange = () => {form.elements.duration.max = form.elements.unit.value === 'years' ? '50' : '600';};
    form.querySelectorAll('[data-simulation-money]').forEach(input => input.addEventListener('input', () => maskMoney(input)));
    form.addEventListener('input', () => {body.querySelector('#simulationResult').hidden = true; error('');});
    form.addEventListener('change', () => {body.querySelector('#simulationResult').hidden = true; error('');});
    function setModes() {
      const previous = form.elements.mode.value;
      const product = InvestmentSimulator.products[form.elements.product.value];
      const names = {fixed: 'Prefixada', cdi: 'Percentual do CDI', ipca: 'IPCA + juros', selic: 'Selic de referência'};
      form.elements.mode.innerHTML = product.modes.map(mode => `<option value="${mode}">${names[mode]}</option>`).join('');
      if (product.modes.includes(previous)) form.elements.mode.value = previous;
      setRateFields(true);
      document.querySelector('#simulationProductNote').textContent = product.exempt ? 'Cenário de isenção de IR para pessoa física, sujeito às condições legais da emissão. Confira a carência e o vencimento do produto.' : 'Estimativa de IR regressivo e IOF calculada separadamente por aporte. Confira o vencimento e as condições da oferta.';
    }
    function setRateFields(reset) {
      const mode = form.elements.mode.value, indexed = ['cdi', 'ipca'].includes(mode);
      document.querySelector('#simulationRateLabel').textContent = mode === 'cdi' ? 'Percentual do CDI (%)' : mode === 'ipca' ? 'Juros acima do IPCA (% ao ano)' : mode === 'selic' ? 'Selic estimada (% ao ano)' : 'Taxa prefixada (% ao ano)';
      document.querySelector('#simulationReferenceField').hidden = !indexed;
      document.querySelector('#simulationReferenceLabel').textContent = mode === 'cdi' ? 'CDI estimado (% ao ano)' : 'IPCA estimado (% ao ano)';
      form.elements.reference.disabled = !indexed; form.elements.reference.required = indexed;
      if (reset) {form.elements.rate.value = mode === 'cdi' ? '100' : ''; form.elements.reference.value = '';}
    }
    setModes();
    form.onsubmit = event => {
      event.preventDefault(); error('');
      const decimal = value => /^\d+(?:[.,]\d+)?$/.test(value.trim()) ? Number(value.trim().replace(',', '.')) : NaN;
      try {
        const result = InvestmentSimulator.calculate({product: form.elements.product.value, mode: form.elements.mode.value, initial: moneyValue(form.elements.initial.value), monthly: moneyValue(form.elements.monthly.value), rate: decimal(form.elements.rate.value), reference: form.elements.reference.disabled ? 0 : decimal(form.elements.reference.value), months: Number(form.elements.duration.value) * (form.elements.unit.value === 'years' ? 12 : 1), startDate: localDateValue()});
        renderSimulationResult(result, form.elements.product.value, form.elements.mode.value);
      } catch (e) {error(e.message);}
    };
  }
  function renderSimulationResult(result, product, mode) {
    const output = body.querySelector('#simulationResult');
    const money = value => brl(value);
    const chartTop = Math.max(result.gross, result.invested, 1);
    const coords = key => result.points.map((p, i) => `${60 + i / result.month * 580},${210 - p[key] / chartTop * 160}`).join(' ');
    const gross = coords('gross'), invested = coords('invested');
    const indexed = mode !== 'fixed';
    output.innerHTML = `<div class="simulation-heading"><span class="eyebrow">${InvestmentSimulator.products[product].name} · ${result.month} meses</span><h3>Seu cenário estimado</h3><p>Taxa bruta equivalente: ${percent(result.annualRate)} ao ano${indexed ? ' com os índices informados constantes' : ''}.</p></div><div class="simulation-totals"><div class="simulation-total"><small>Total líquido estimado</small><strong>${money(result.net)}</strong><span>Após impostos estimados, antes de taxas</span></div><div><small>Dinheiro que você aportou</small><strong>${money(result.invested)}</strong></div><div><small>Rendimento bruto</small><strong>${money(result.gain)}</strong></div><div><small>IR + IOF estimados</small><strong>${money(result.tax)}</strong></div><div><small>Total bruto</small><strong>${money(result.gross)}</strong></div><div><small>Rendimento líquido estimado</small><strong>${money(result.net - result.invested)}</strong></div></div><figure class="simulation-chart"><figcaption>Evolução do patrimônio <span><i class="chart-gross"></i> Total bruto <i class="chart-invested"></i> Aportes</span></figcaption><svg viewBox="0 0 680 250" role="img" aria-label="Evolução estimada: ${money(result.invested)} em aportes e ${money(result.gross)} de total bruto ao fim de ${result.month} meses. Consulte os valores na tabela mensal abaixo."><line x1="60" y1="210" x2="640" y2="210" stroke="currentColor" opacity=".2"/><text x="60" y="28" fill="currentColor" font-size="12">${money(chartTop)}</text><polyline points="${invested}" fill="none" stroke="#a4b2cc" stroke-width="2" stroke-dasharray="5 5"/><polyline points="${gross}" fill="none" stroke="#75e0b2" stroke-width="3"/><text x="60" y="237" fill="currentColor" font-size="12">Hoje</text><text x="640" y="237" text-anchor="end" fill="currentColor" font-size="12">${result.month} meses</text></svg></figure><details class="simulation-table"><summary>Ver evolução mês a mês</summary><div class="scroll"><table><caption>Projeção de aportes e rendimentos por mês</caption><thead><tr><th>Mês</th><th>Aportado</th><th>Total bruto</th><th>Impostos estimados</th><th>Total líquido</th></tr></thead><tbody>${result.points.map(p => `<tr><td>${p.month}</td><td>${money(p.invested)}</td><td>${money(p.gross)}</td><td>${money(p.tax)}</td><td>${money(p.net)}</td></tr>`).join('')}</tbody></table></div></details><div class="education-note"><strong>Como calculamos</strong><p>Juros compostos desde hoje, proporcionais aos dias corridos (ano de 365 dias). Aporte ao fim de cada mês; o último ainda não rende. Cada aporte tem seu próprio prazo para IR e IOF. A taxa informada é mantida em todas as aplicações.</p><p>${mode === 'cdi' ? 'CDI convertido para taxa diária em base de 252 dias úteis, com aplicação do percentual contratado e conversão para projeção em dias corridos. ' : mode === 'ipca' ? 'IPCA e juros reais são compostos por multiplicação, não por soma. ' : ''}${indexed ? 'CDI, Selic e inflação futuros são incertos: esta simulação mantém as referências constantes. ' : ''}Não inclui custódia, tarifas, pagamentos periódicos de juros, amortizações ou oscilação do preço na venda antecipada. Valores nominais, sem descontar a inflação.</p><p>Aportes mensais representam novas aplicações: taxas, disponibilidade, aplicação mínima, carência e vencimento precisam ser conferidos na instituição. A projeção não garante resgate na data escolhida.</p></div>`;
    output.hidden = false;
    output.tabIndex = -1; output.focus({preventScroll: true}); output.scrollIntoView({behavior: 'smooth', block: 'start'});
  }
  dialog.addEventListener('click', event => {
    const viewButton = event.target.closest('[data-education-view]');
    const choice = event.target.closest('[data-experience]');
    const simulate = event.target.closest('[data-simulate-product]');
    if (saving) return;
    if (viewButton) render(viewButton.dataset.educationView);
    if (event.target.closest('[data-start-quiz]')) startQuiz();
    if (simulate) {render('simulator'); renderSimulator(simulate.dataset.simulateProduct); body.querySelector('select').focus();}
    if (choice) action(async () => {
      await save({experience: choice.dataset.experience});
      if (choice.dataset.experience === 'beginner') startQuiz(); else dialog.close();
    });
  });
  document.querySelector('#openInvestorGuide').onclick = () => open('profile');
  document.querySelector('#openInvestmentSimulator').onclick = () => open('simulator');
  function onPanel() {
    updateBanner();
    if (!panel.hidden && !promptShown && preferencesReady && canWrite && !state()) {promptShown = true; open('welcome');}
  }
  new MutationObserver(onPanel).observe(panel, {attributes: true, attributeFilter: ['hidden']});
  document.addEventListener('bootstrap-loaded', () => {preferencesReady = true; onPanel();});
  document.addEventListener('insights-updated', () => queueMicrotask(updateBanner));
  onPanel();
})();
