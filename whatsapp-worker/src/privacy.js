export function normalizePhone(value) {
  const digits = String(value || "").replace(/\D/g, "");
  if (digits.length < 10 || digits.length > 15) throw new Error("Telefone inválido");
  return digits;
}

export function maskPhone(value) {
  const phone = normalizePhone(value);
  return `(**) *****-${phone.slice(-4)}`;
}

function bytesToHex(buffer) {
  return [...new Uint8Array(buffer)].map((byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function hmacHex(secret, value) {
  const encoder = new TextEncoder();
  const key = await crypto.subtle.importKey(
    "raw", encoder.encode(secret), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]
  );
  return bytesToHex(await crypto.subtle.sign("HMAC", key, encoder.encode(value)));
}

export async function verifyMetaSignature(secret, rawBody, header) {
  if (!secret || !header?.startsWith("sha256=")) return false;
  const expected = await hmacHex(secret, rawBody);
  const received = header.slice(7).toLowerCase();
  if (expected.length !== received.length) return false;
  let mismatch = 0;
  for (let index = 0; index < expected.length; index += 1) {
    mismatch |= expected.charCodeAt(index) ^ received.charCodeAt(index);
  }
  return mismatch === 0;
}
