import { commandOf, parseExpenseMessage } from "./parser.js";
import { hmacHex, maskPhone, normalizePhone, verifyMetaSignature } from "./privacy.js";
import { ADMIN_PAGE } from "./admin-page.js";

const JSON_HEADERS = { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" };

function json(payload, status = 200) {
  return new Response(JSON.stringify(payload), { status, headers: JSON_HEADERS });
}

function money(cents) {
  return (cents / 100).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
}

function isoNow() {
  return new Date().toISOString();
}

function occurredOn(timestamp) {
  const value = timestamp ? new Date(Number(timestamp) * 1000) : new Date();
  const parts = new Intl.DateTimeFormat("en-CA", {
    timeZone: "America/Sao_Paulo", year: "numeric", month: "2-digit", day: "2-digit",
  }).formatToParts(value);
  const get = (type) => parts.find((part) => part.type === type).value;
  return `${get("year")}-${get("month")}-${get("day")}`;
}

async function sendText(env, to, body) {
  const version = env.META_API_VERSION || "v23.0";
  const response = await fetch(`https://graph.facebook.com/${version}/${env.META_PHONE_NUMBER_ID}/messages`, {
    method: "POST",
    headers: { authorization: `Bearer ${env.META_ACCESS_TOKEN}`, "content-type": "application/json" },
    body: JSON.stringify({ messaging_product: "whatsapp", recipient_type: "individual", to, type: "text", text: { body } }),
  });
  if (!response.ok) throw new Error(`Falha da API da Meta: ${response.status}`);
}

async function findOrCreateUser(env, phone) {
  const phoneHash = await hmacHex(env.PHONE_HASH_SECRET, phone);
  let user = await env.DB.prepare(
    "SELECT id, masked_phone, status, consented_at FROM users WHERE phone_hash = ?"
  ).bind(phoneHash).first();
  const now = isoNow();
  if (!user) {
    user = { id: crypto.randomUUID(), masked_phone: maskPhone(phone), status: "pending", consented_at: null };
    await env.DB.prepare(
      "INSERT INTO users (id, phone_hash, masked_phone, status, created_at, last_seen_at) VALUES (?, ?, ?, 'pending', ?, ?)"
    ).bind(user.id, phoneHash, user.masked_phone, now, now).run();
  } else {
    await env.DB.prepare("UPDATE users SET last_seen_at = ? WHERE id = ?").bind(now, user.id).run();
  }
  return user;
}

async function monthlySummary(env, userId, day) {
  const month = day.slice(0, 7);
  const rows = await env.DB.prepare(
    "SELECT payment, COALESCE(SUM(amount_cents), 0) AS total FROM expenses WHERE user_id = ? AND substr(occurred_on, 1, 7) = ? GROUP BY payment"
  ).bind(userId, month).all();
  let cash = 0;
  let voucher = 0;
  for (const row of rows.results || []) {
    if (row.payment === "Voucher") voucher += Number(row.total);
    else cash += Number(row.total);
  }
  return `📊 Resumo de ${month}\nDinheiro/cartões: ${money(cash)}\nVoucher: ${money(voucher)}`;
}

async function processMessage(env, message) {
  if (message.type !== "text" || !message.text?.body) {
    await sendText(env, message.from, "Por enquanto eu entendo apenas mensagens de texto. Digite AJUDA para ver exemplos.");
    return;
  }
  const phone = normalizePhone(message.from);
  const user = await findOrCreateUser(env, phone);
  const text = message.text.body;
  const command = commandOf(text);

  if (user.status === "blocked") {
    await sendText(env, phone, "Sua conta está bloqueada. Entre em contato com o responsável pelo serviço.");
    return;
  }
  if (user.status === "pending" && command !== "consent") {
    await sendText(env, phone,
      "Bem-vindo ao Meu Gasto IA. Seus gastos são privados e o administrador não visualiza valores, locais ou descrições. " +
      "Para criar sua conta e aceitar o armazenamento dos dados, responda ACEITO."
    );
    return;
  }
  if (command === "consent") {
    if (user.status !== "active") {
      await env.DB.prepare("UPDATE users SET status = 'active', consented_at = ? WHERE id = ?").bind(isoNow(), user.id).run();
    }
    await sendText(env, phone, "✅ Conta ativada. Envie assim:\n71 gasolina crédito\n45 mercado voucher\n\nDigite AJUDA quando precisar.");
    return;
  }
  if (command === "help") {
    await sendText(env, phone,
      "Envie: VALOR + GASTO + PAGAMENTO\n\nExemplos:\n71 gasolina crédito\n45 mercado voucher\n32 almoço pix\n\nComandos: SALDO, APAGAR HISTÓRICO e APAGAR PERFIL."
    );
    return;
  }
  if (command === "summary") {
    await sendText(env, phone, await monthlySummary(env, user.id, occurredOn(message.timestamp)));
    return;
  }
  if (command === "request_delete_history") {
    await sendText(env, phone, "Esta ação apaga todos os seus gastos e não pode ser desfeita. Para continuar, envie: CONFIRMAR APAGAR HISTÓRICO");
    return;
  }
  if (command === "delete_history") {
    await env.DB.prepare("DELETE FROM expenses WHERE user_id = ?").bind(user.id).run();
    await sendText(env, phone, "Seu histórico foi apagado permanentemente.");
    return;
  }
  if (command === "request_delete_profile") {
    await sendText(env, phone, "Esta ação apaga sua conta e todo o histórico. Para continuar, envie: CONFIRMAR APAGAR PERFIL");
    return;
  }
  if (command === "delete_profile") {
    await env.DB.prepare("DELETE FROM users WHERE id = ?").bind(user.id).run();
    await sendText(env, phone, "Sua conta e seu histórico foram apagados permanentemente.");
    return;
  }

  const parsed = parseExpenseMessage(text);
  if (!parsed.ok) {
    await sendText(env, phone, `Não consegui registrar. ${parsed.error}`);
    return;
  }
  const expense = parsed.expense;
  const result = await env.DB.prepare(
    "INSERT OR IGNORE INTO expenses (id, user_id, source_message_id, amount_cents, merchant, category, payment, description, occurred_on, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
  ).bind(
    crypto.randomUUID(), user.id, message.id, expense.amountCents, expense.merchant,
    expense.category, expense.payment, expense.description, occurredOn(message.timestamp), isoNow()
  ).run();
  if (Number(result.meta?.changes || 0) === 0) return;
  await sendText(env, phone,
    `✅ Gasto registrado\n\n${money(expense.amountCents)}\n${expense.merchant}\nCategoria: ${expense.category}\nPagamento: ${expense.payment}`
  );
}

function isAdmin(request, env) {
  const header = request.headers.get("authorization") || "";
  return Boolean(env.ADMIN_API_TOKEN) && header === `Bearer ${env.ADMIN_API_TOKEN}`;
}

async function adminRoute(request, env, path) {
  if (!isAdmin(request, env)) return json({ ok: false, error: "Não autorizado" }, 401);
  if (request.method === "GET" && path === "/admin/users") {
    const users = await env.DB.prepare(
      "SELECT id, masked_phone, status, created_at, last_seen_at FROM users ORDER BY created_at DESC LIMIT 200"
    ).all();
    return json({ ok: true, users: users.results || [] });
  }
  const match = path.match(/^\/admin\/users\/([a-f0-9-]+)(?:\/(history|block|unblock))?$/i);
  if (!match) return json({ ok: false, error: "Rota não encontrada" }, 404);
  const [, userId, action] = match;
  const now = isoNow();
  if (action === "block" && request.method === "POST") {
    await env.DB.prepare("UPDATE users SET status = 'blocked' WHERE id = ?").bind(userId).run();
  } else if (action === "unblock" && request.method === "POST") {
    await env.DB.prepare("UPDATE users SET status = 'active' WHERE id = ?").bind(userId).run();
  } else if (action === "history" && request.method === "DELETE") {
    if (request.headers.get("x-confirm-delete") !== userId) return json({ ok: false, error: "Confirmação inválida" }, 409);
    await env.DB.prepare("DELETE FROM expenses WHERE user_id = ?").bind(userId).run();
  } else if (!action && request.method === "DELETE") {
    if (request.headers.get("x-confirm-delete") !== userId) return json({ ok: false, error: "Confirmação inválida" }, 409);
    await env.DB.prepare("DELETE FROM users WHERE id = ?").bind(userId).run();
  } else {
    return json({ ok: false, error: "Operação inválida" }, 405);
  }
  await env.DB.prepare("INSERT INTO admin_audit (id, action, target_user_id, created_at) VALUES (?, ?, ?, ?)")
    .bind(crypto.randomUUID(), action || "delete_profile", userId, now).run();
  return json({ ok: true });
}

async function handleWebhook(request, env) {
  if (request.method === "GET") {
    const url = new URL(request.url);
    if (url.searchParams.get("hub.mode") === "subscribe" && url.searchParams.get("hub.verify_token") === env.META_VERIFY_TOKEN) {
      return new Response(url.searchParams.get("hub.challenge") || "", { status: 200 });
    }
    return new Response("Verificação recusada", { status: 403 });
  }
  const rawBody = await request.text();
  const valid = await verifyMetaSignature(env.META_APP_SECRET, rawBody, request.headers.get("x-hub-signature-256"));
  if (!valid) return new Response("Assinatura inválida", { status: 401 });
  const payload = JSON.parse(rawBody);
  const messages = [];
  for (const entry of payload.entry || []) {
    for (const change of entry.changes || []) messages.push(...(change.value?.messages || []));
  }
  for (const message of messages) await processMessage(env, message);
  return json({ ok: true });
}

export default {
  async fetch(request, env) {
    const path = new URL(request.url).pathname;
    try {
      if (path === "/health") return json({ ok: true, service: "meu-gasto-ia-whatsapp" });
      if (path === "/webhook") return await handleWebhook(request, env);
      if (path === "/admin") return new Response(ADMIN_PAGE, {
        headers: {
          "content-type": "text/html; charset=utf-8",
          "cache-control": "no-store",
          "content-security-policy": "default-src 'self'; script-src 'unsafe-inline'; style-src 'unsafe-inline'; connect-src 'self'; frame-ancestors 'none'",
        },
      });
      if (path.startsWith("/admin/")) return await adminRoute(request, env, path);
      return json({ ok: false, error: "Rota não encontrada" }, 404);
    } catch (error) {
      return json({ ok: false, error: "Erro interno" }, 500);
    }
  },
};

export { adminRoute, handleWebhook, processMessage };
