const PAYMENT_ALIASES = new Map([
  ["pix", "Pix"],
  ["credito", "Crédito"],
  ["cartao", "Crédito"],
  ["debito", "Débito"],
  ["dinheiro", "Dinheiro"],
  ["transferencia", "Transferência"],
  ["voucher", "Voucher"],
  ["vale", "Voucher"],
  ["vr", "Voucher"],
  ["va", "Voucher"],
]);

const CATEGORY_RULES = [
  ["Transporte", ["gasolina", "posto", "uber", "99", "estacionamento", "onibus", "metro", "carro"]],
  ["Mercado", ["mercado", "supermercado", "feira", "acougue"]],
  ["Alimentação", ["almoco", "jantar", "restaurante", "ifood", "lanche", "comida", "padaria"]],
  ["Saúde", ["farmacia", "remedio", "dentista", "consulta", "medico"]],
  ["Moradia", ["aluguel", "condominio"]],
  ["Contas", ["luz", "agua", "internet", "telefone", "seguro"]],
  ["Educação", ["faculdade", "escola", "curso", "livro"]],
  ["Lazer", ["cinema", "festa", "bar", "jogo", "recreacao"]],
  ["Compras", ["roupa", "calcado", "shopping"]],
  ["Assinaturas", ["netflix", "spotify", "assinatura"]],
  ["Viagem", ["hotel", "passagem", "viagem"]],
  ["Presentes", ["presente"]],
];

export function normalizeText(value) {
  return value.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase().trim();
}

export function parseAmount(value) {
  let normalized = value.replace(/r\$/gi, "").replace(/\s/g, "");
  if (normalized.includes(",")) normalized = normalized.replace(/\./g, "").replace(",", ".");
  const amount = Number(normalized);
  if (!Number.isFinite(amount) || amount <= 0 || amount > 10_000_000) return null;
  return Math.round(amount * 100);
}

export function categorize(description) {
  const text = normalizeText(description);
  for (const [category, words] of CATEGORY_RULES) {
    if (words.some((word) => text.includes(word))) return category;
  }
  return "Outros";
}

export function parseExpenseMessage(message) {
  const trimmed = message.trim().replace(/\s+/g, " ");
  const firstSpace = trimmed.indexOf(" ");
  if (firstSpace < 1) return { ok: false, error: "Envie valor, local e pagamento. Ex.: 71 gasolina crédito" };
  const amountCents = parseAmount(trimmed.slice(0, firstSpace));
  if (!amountCents) return { ok: false, error: "Não entendi o valor. Ex.: 71,50 gasolina crédito" };

  const parts = trimmed.slice(firstSpace + 1).split(" ");
  const paymentKey = normalizeText(parts.at(-1));
  const payment = PAYMENT_ALIASES.get(paymentKey);
  if (!payment) return { ok: false, error: "Informe o pagamento no final: pix, crédito, débito, dinheiro ou voucher" };
  parts.pop();
  const merchant = parts.join(" ").trim();
  if (!merchant) return { ok: false, error: "Informe onde ou com o que você gastou" };

  return {
    ok: true,
    expense: {
      amountCents,
      merchant,
      category: categorize(merchant),
      payment,
      description: merchant,
    },
  };
}

export function commandOf(message) {
  const text = normalizeText(message);
  if (["aceito", "concordo"].includes(text)) return "consent";
  if (["ajuda", "menu", "oi", "ola"].includes(text)) return "help";
  if (["saldo", "resumo"].includes(text)) return "summary";
  if (text === "apagar historico") return "request_delete_history";
  if (text === "confirmar apagar historico") return "delete_history";
  if (text === "apagar perfil") return "request_delete_profile";
  if (text === "confirmar apagar perfil") return "delete_profile";
  return "expense";
}
