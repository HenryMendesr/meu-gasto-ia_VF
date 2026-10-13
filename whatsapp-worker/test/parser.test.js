import test from "node:test";
import assert from "node:assert/strict";

import { categorize, commandOf, parseAmount, parseExpenseMessage } from "../src/parser.js";

test("interpreta o formato curto de gasto", () => {
  assert.deepEqual(parseExpenseMessage("71 gasolina crédito"), {
    ok: true,
    expense: {
      amountCents: 7100,
      merchant: "gasolina",
      category: "Transporte",
      payment: "Crédito",
      description: "gasolina",
    },
  });
});

test("aceita centavos, milhar e voucher", () => {
  const result = parseExpenseMessage("1.234,56 supermercado voucher");
  assert.equal(result.ok, true);
  assert.equal(result.expense.amountCents, 123456);
  assert.equal(result.expense.category, "Mercado");
  assert.equal(result.expense.payment, "Voucher");
});

test("recusa mensagem sem pagamento reconhecido", () => {
  const result = parseExpenseMessage("25 almoço cheque");
  assert.equal(result.ok, false);
  assert.match(result.error, /pagamento/i);
});

test("identifica comandos sem depender de acentos", () => {
  assert.equal(commandOf("CONFIRMAR APAGAR HISTÓRICO"), "delete_history");
  assert.equal(commandOf("Olá"), "help");
  assert.equal(commandOf("ACEITO"), "consent");
});

test("categorias desconhecidas ficam em Outros", () => {
  assert.equal(categorize("Loja XYZ"), "Outros");
  assert.equal(parseAmount("R$ 18,90"), 1890);
});
