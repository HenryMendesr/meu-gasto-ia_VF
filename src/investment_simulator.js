// Pure calculations shared by the interface and the numerical regression checks.
const InvestmentSimulator = (() => {
  const products = {
    cdb: {name: 'CDB', modes: ['fixed', 'cdi', 'ipca'], exempt: false},
    lci: {name: 'LCI', modes: ['fixed', 'cdi', 'ipca'], exempt: true},
    lca: {name: 'LCA', modes: ['fixed', 'cdi', 'ipca'], exempt: true},
    treasury_fixed: {name: 'Tesouro Prefixado', modes: ['fixed'], exempt: false},
    treasury_selic: {name: 'Tesouro Selic', modes: ['selic'], exempt: false},
    treasury_ipca: {name: 'Tesouro IPCA+', modes: ['ipca'], exempt: false},
    debenture: {name: 'Debênture comum', modes: ['fixed', 'cdi', 'ipca'], exempt: false},
    incentivized: {name: 'Debênture incentivada', modes: ['fixed', 'ipca'], exempt: true},
  };
  const iofRates = [100,96,93,90,86,83,80,76,73,70,66,63,60,56,53,50,46,43,40,36,33,30,26,23,20,16,13,10,6,3];
  function monthDate(start, offset) {
    const first = new Date(Date.UTC(start.getUTCFullYear(), start.getUTCMonth() + offset, 1));
    const last = new Date(Date.UTC(first.getUTCFullYear(), first.getUTCMonth() + 1, 0)).getUTCDate();
    first.setUTCDate(Math.min(start.getUTCDate(), last));
    return first;
  }
  function calculate(input) {
    const {product, mode, initial, monthly, months, rate, reference = 0, startDate} = input;
    const selected = products[product];
    if (!selected || !selected.modes.includes(mode)) throw Error('Escolha um investimento e uma rentabilidade compatível.');
    if (![initial, monthly, rate, reference].every(Number.isFinite) || initial < 0 || monthly < 0 || initial > 100000000 || monthly > 10000000 || initial + monthly <= 0)
      throw Error('Informe valores válidos: até R$ 100 milhões iniciais e R$ 10 milhões mensais.');
    if (!Number.isInteger(months) || months < 1 || months > 600) throw Error('Escolha um prazo de 1 a 600 meses (50 anos).');
    if (rate < 0 || rate > (mode === 'cdi' ? 300 : 100) || reference < 0 || reference > 100)
      throw Error('Informe taxas entre 0 e 100%; para o percentual do CDI, até 300%.');
    const start = new Date(startDate + 'T00:00:00Z');
    if (!/^\d{4}-\d{2}-\d{2}$/.test(startDate) || !Number.isFinite(start.getTime()) || start.toISOString().slice(0,10) !== startDate || start.getUTCFullYear() < 1900 || start.getUTCFullYear() > 2200)
      throw Error('Data inicial inválida.');
    // CDI participation applies to the equivalent daily rate (252 business days).
    const annualFactor = mode === 'cdi' ? (1 + ((1 + reference / 100) ** (1 / 252) - 1) * rate / 100) ** 252
      : mode === 'ipca' ? (1 + reference / 100) * (1 + rate / 100) : 1 + rate / 100;
    const lots = [{amount: initial, date: start}];
    const points = [{month: 0, date: startDate, invested: initial, gross: initial, net: initial, tax: 0, gain: 0}];
    for (let month = 1; month <= months; month++) {
      const at = monthDate(start, month);
      // Contributions arrive at the end of each month, including the last month.
      lots.push({amount: monthly, date: at});
      let gross = 0, tax = 0;
      for (const lot of lots) {
        const days = Math.round((at - lot.date) / 86400000);
        const balance = lot.amount * annualFactor ** (days / 365);
        const gain = Math.max(0, balance - lot.amount);
        const iof = selected.exempt || days >= 30 ? 0 : gain * iofRates[days] / 100;
        const irRate = days <= 180 ? .225 : days <= 360 ? .20 : days <= 720 ? .175 : .15;
        tax += selected.exempt ? 0 : iof + (gain - iof) * irRate;
        gross += balance;
      }
      const invested = initial + monthly * month;
      if (!Number.isFinite(gross) || gross > 1e15) throw Error('O resultado ficou muito alto. Reduza a taxa, os valores ou o prazo.');
      points.push({month, date: at.toISOString().slice(0,10), invested, gross, tax, net: gross - tax, gain: gross - invested});
    }
    return {...points.at(-1), annualRate: (annualFactor - 1) * 100, points};
  }
  return {products, calculate};
})();
if (typeof module !== 'undefined') module.exports = InvestmentSimulator;
