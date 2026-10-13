import test from "node:test";
import assert from "node:assert/strict";

import worker, { adminRoute, handleWebhook } from "../src/index.js";

test("health check não expõe dados", async () => {
  const response = await worker.fetch(new Request("https://example.test/health"), {});
  assert.equal(response.status, 200);
  assert.deepEqual(await response.json(), { ok: true, service: "meu-gasto-ia-whatsapp" });
});

test("painel administrativo não contém campos financeiros", async () => {
  const response = await worker.fetch(new Request("https://example.test/admin"), {});
  const html = await response.text();
  assert.equal(response.status, 200);
  assert.match(html, /Gerencie contas sem visualizar gastos/i);
  assert.equal(/amount_cents|merchant|category|description/.test(html), false);
});

test("verificação do webhook exige token correto", async () => {
  const env = { META_VERIFY_TOKEN: "correto" };
  const accepted = await handleWebhook(
    new Request("https://example.test/webhook?hub.mode=subscribe&hub.verify_token=correto&hub.challenge=123"), env
  );
  assert.equal(accepted.status, 200);
  assert.equal(await accepted.text(), "123");
  const rejected = await handleWebhook(
    new Request("https://example.test/webhook?hub.mode=subscribe&hub.verify_token=errado&hub.challenge=123"), env
  );
  assert.equal(rejected.status, 403);
});

test("admin lista apenas metadados da conta", async () => {
  const statements = [];
  const env = {
    ADMIN_API_TOKEN: "admin-secret",
    DB: {
      prepare(sql) {
        statements.push(sql);
        return { async all() { return { results: [{ id: "u1", masked_phone: "(**) *****-1234", status: "active" }] }; } };
      },
    },
  };
  const request = new Request("https://example.test/admin/users", { headers: { authorization: "Bearer admin-secret" } });
  const response = await adminRoute(request, env, "/admin/users");
  const body = await response.json();
  assert.equal(response.status, 200);
  assert.equal(body.users[0].masked_phone, "(**) *****-1234");
  assert.equal(statements.some((sql) => /expenses|amount|merchant|category|description/i.test(sql)), false);
});

test("admin sem credencial não acessa contas", async () => {
  const response = await adminRoute(new Request("https://example.test/admin/users"), { ADMIN_API_TOKEN: "secret" }, "/admin/users");
  assert.equal(response.status, 401);
});
