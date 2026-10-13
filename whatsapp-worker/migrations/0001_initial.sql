PRAGMA foreign_keys = ON;

CREATE TABLE users (
  id TEXT PRIMARY KEY,
  phone_hash TEXT NOT NULL UNIQUE,
  masked_phone TEXT NOT NULL,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending', 'active', 'blocked')),
  consented_at TEXT,
  created_at TEXT NOT NULL,
  last_seen_at TEXT NOT NULL
);

CREATE TABLE expenses (
  id TEXT PRIMARY KEY,
  user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
  source_message_id TEXT NOT NULL UNIQUE,
  amount_cents INTEGER NOT NULL CHECK (amount_cents > 0),
  merchant TEXT NOT NULL,
  category TEXT NOT NULL,
  payment TEXT NOT NULL,
  description TEXT NOT NULL DEFAULT '',
  occurred_on TEXT NOT NULL,
  created_at TEXT NOT NULL
);

CREATE INDEX expenses_user_date_idx ON expenses(user_id, occurred_on);

CREATE TABLE admin_audit (
  id TEXT PRIMARY KEY,
  action TEXT NOT NULL,
  target_user_id TEXT NOT NULL,
  created_at TEXT NOT NULL
);

-- A auditoria registra somente a ação e o identificador interno.
-- Valores, locais, categorias, telefones completos e mensagens são proibidos aqui.
