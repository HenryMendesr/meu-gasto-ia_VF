const assert = require('node:assert/strict');
const {calculate} = require('../src/investment_simulator.js');
const base = {product:'cdb', mode:'fixed', initial:1000, monthly:0, months:12, rate:12, startDate:'2026-11-05'};
const near = (actual, expected) => assert.ok(Math.abs(actual - expected) < .000001, `${actual} != ${expected}`);

// Effective annual compounding and the 361–720 day tax bracket.
const year = calculate(base);
near(year.gross, 1120); near(year.tax, 21); near(year.net, 1099);
near(calculate({...base, rate:0, monthly:200}).gross, 3400);
near(calculate({...base, product:'lci'}).tax, 0);
near(calculate({...base, product:'lca'}).net, 1120);
near(calculate({...base, product:'incentivized'}).net, 1120);
near(calculate({...base, mode:'ipca', rate:6, reference:4}).gross, 1000 * 1.06 * 1.04);
near(calculate({...base, mode:'cdi', rate:100, reference:12}).gross, 1120);
const daily = Math.pow(1.12, 1/252) - 1;
near(calculate({...base, mode:'cdi', rate:110, reference:12}).gross, 1000 * Math.pow(1 + daily * 1.10, 252));
near(calculate({...base, product:'treasury_selic', mode:'selic'}).gross, 1120);

// Each monthly purchase has its own tax clock; the final purchase earns nothing.
const monthly = calculate({...base, monthly:200});
const lastDate = Date.parse('2027-11-05');
let expectedGross = 1120, expectedTax = 21;
for (let month = 1; month <= 12; month++) {
  const at = new Date(Date.UTC(2026, 10 + month, 5));
  const days = (lastDate - at) / 86400000;
  const gain = 200 * Math.pow(1.12, days / 365) - 200;
  expectedGross += 200 + gain;
  expectedTax += gain * (days <= 180 ? .225 : days <= 360 ? .20 : .175);
}
near(monthly.gross, expectedGross); near(monthly.tax, expectedTax);
assert.ok(monthly.tax > monthly.gain * .175);
near(calculate({...base, initial:0, monthly:200, months:1}).gross, 200);
const february = calculate({...base, startDate:'2027-01-31', months:1});
assert.equal(february.date, '2027-02-28');
near(february.tax, february.gain * .06 + february.gain * .94 * .225);
const clamped = calculate({...base, startDate:'2028-01-31', months:2});
assert.equal(clamped.points[1].date, '2028-02-29');
assert.equal(clamped.points[2].date, '2028-03-31');
assert.equal(calculate({...base, months:600, rate:1}).points.length, 601);

for (const changes of [{rate:NaN},{initial:-1},{monthly:-1},{initial:0,monthly:0},{months:0},{months:601},{months:1.5},{reference:Infinity},{rate:101},{mode:'cdi',rate:301},{product:'unknown'},{product:'treasury_selic',mode:'fixed'},{startDate:'2026-02-30'},{startDate:'invalid'}]) {
  assert.throws(() => calculate({...base,...changes}), Error);
}
console.log('Simulador: juros, aportes, indexadores, impostos e limites validados.');
