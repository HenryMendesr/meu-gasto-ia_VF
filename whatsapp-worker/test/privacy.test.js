import test from "node:test";
import assert from "node:assert/strict";

import { hmacHex, maskPhone, normalizePhone, verifyMetaSignature } from "../src/privacy.js";

test("normaliza e mascara telefone sem expor o número", () => {
  assert.equal(normalizePhone("+55 (41) 99999-1234"), "5541999991234");
  assert.equal(maskPhone("5541999991234"), "(**) *****-1234");
});

test("hash do telefone é estável e não contém o telefone", async () => {
  const value = await hmacHex("segredo-de-teste", "5541999991234");
  assert.equal(value.length, 64);
  assert.equal(value.includes("999991234"), false);
  assert.equal(value, await hmacHex("segredo-de-teste", "5541999991234"));
});

test("valida assinatura oficial do webhook", async () => {
  const body = JSON.stringify({ object: "whatsapp_business_account" });
  const signature = await hmacHex("app-secret", body);
  assert.equal(await verifyMetaSignature("app-secret", body, `sha256=${signature}`), true);
  assert.equal(await verifyMetaSignature("app-secret", body + "x", `sha256=${signature}`), false);
});
