"""Banco de dados local e backups do Minha Carteira."""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import sqlite3
from threading import Lock
try:
    from src.finance_rules import installment_plan, expense_finance, prepare_debt_update, debt_payment_metadata, debt_revision
except ImportError:
    from finance_rules import installment_plan, expense_finance, prepare_debt_update, debt_payment_metadata, debt_revision


ROOT = Path(__file__).resolve().parents[1]
DATABASE = ROOT / "data/meu_gasto.db"
BACKUPS = ROOT / "backups/app"
LOCK = Lock()
CATEGORIES = {
    "Alimentação", "Mercado", "Transporte", "Moradia", "Saúde", "Educação",
    "Lazer", "Compras", "Assinaturas", "Contas", "Viagem", "Presentes", "Outros",
}
PAYMENTS = {"Pix", "Crédito", "Débito", "Dinheiro", "Transferência", "Voucher", "Não informado"}


class DuplicateExpenseError(ValueError):
    pass


def connect() -> sqlite3.Connection:
    DATABASE.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DATABASE, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA journal_mode=WAL")
    return connection


def initialize() -> None:
    first_run = not DATABASE.exists()
    with connect() as db:
        db.executescript("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                expense_date TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                place TEXT NOT NULL,
                category TEXT NOT NULL,
                payment TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                installment_group TEXT,
                installment_number INTEGER,
                installment_count INTEGER,
                original_total REAL,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS incomes (
                month TEXT PRIMARY KEY,
                cash REAL NOT NULL DEFAULT 0,
                voucher REAL NOT NULL DEFAULT 0,
                payday INTEGER,
                source TEXT NOT NULL DEFAULT '',
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS income_entries (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                entry_date TEXT NOT NULL,
                amount REAL NOT NULL CHECK(amount > 0),
                source TEXT NOT NULL,
                category TEXT NOT NULL,
                description TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS budgets (
                month TEXT NOT NULL,
                category TEXT NOT NULL,
                amount REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY(month, category)
            );
            CREATE TABLE IF NOT EXISTS budget_categories (
                name TEXT PRIMARY KEY,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS app_state (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL
            );
        """)
        columns = {row["name"] for row in db.execute("PRAGMA table_info(expenses)").fetchall()}
        for name, definition in (("installment_group", "TEXT"), ("installment_number", "INTEGER"), ("installment_count", "INTEGER"), ("original_total", "REAL"), ("finance_details", "TEXT NOT NULL DEFAULT '{}'")):
            if name not in columns:
                db.execute(f"ALTER TABLE expenses ADD COLUMN {name} {definition}")
        db.execute("CREATE UNIQUE INDEX IF NOT EXISTS expenses_installment_uidx ON expenses(installment_group,installment_number) WHERE installment_group IS NOT NULL")
        income_columns = {row["name"] for row in db.execute("PRAGMA table_info(incomes)").fetchall()}
        if "payday" not in income_columns: db.execute("ALTER TABLE incomes ADD COLUMN payday INTEGER")
        if "source" not in income_columns: db.execute("ALTER TABLE incomes ADD COLUMN source TEXT NOT NULL DEFAULT ''")
        db.executemany("INSERT OR IGNORE INTO budget_categories(name) VALUES(?)", ((name,) for name in sorted(CATEGORIES)))
        if first_run:
            investment_data = {"version": 1, "updated_at": None, "investments": [], "history": []}
            db.execute("INSERT OR IGNORE INTO app_state(key,value) VALUES('investments',?)",
                       (json.dumps(investment_data, ensure_ascii=False),))


def create_backup() -> Path:
    initialize()
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = BACKUPS / f"meu-gasto-{stamp}.db"
    with connect() as source, sqlite3.connect(destination) as target:
        source.backup(target)
    for old in sorted(BACKUPS.glob("meu-gasto-*.db"), reverse=True)[20:]:
        old.unlink()
    return destination


def read_expenses(user_id: int | None = None) -> list[dict]:
    initialize()
    with connect() as db:
        rows = db.execute("SELECT id,expense_date,amount,place,category,payment,description,installment_group,installment_number,installment_count,original_total,finance_details FROM expenses ORDER BY expense_date,id").fetchall()
    return [{"id": row["id"], "row": row["id"], "date": row["expense_date"], "amount": round(row["amount"], 2),
             "where": row["place"], "category": row["category"], "payment": row["payment"], "description": row["description"],
             "finance": json.loads(row["finance_details"]), "installment_group": row["installment_group"], "installment_number": row["installment_number"],
             "installment_count": row["installment_count"], "original_total": round(row["original_total"], 2) if row["original_total"] is not None else None} for row in rows]


def add_expense(payload: dict, user_id: int | None = None) -> dict:
    try:
        expense_date = date.fromisoformat(str(payload["date"])).isoformat()
        amount = round(float(payload["amount"]), 2)
        place = str(payload["where"]).strip()
        category = str(payload["category"]).strip()
        payment = str(payload["payment"]).strip()
        description = str(payload.get("description", "")).strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Preencha data, valor, local, categoria e pagamento") from exc
    if amount <= 0 or amount > 10_000_000:
        raise ValueError("O valor deve ser maior que zero")
    if not place or len(place) > 100 or len(description) > 200:
        raise ValueError("Revise o local ou a descrição")
    if category not in set(read_categories()) or payment not in PAYMENTS:
        raise ValueError("Categoria ou pagamento inválido")
    expense_date, installments, finance = expense_finance(payload, expense_date, payment)
    initialize()
    with LOCK:
        with connect() as db:
            duplicate = db.execute("SELECT id FROM expenses WHERE expense_date=? AND amount=? AND lower(place)=lower(?) AND category=? AND payment=? AND lower(description)=lower(?) LIMIT 1",
                                   (expense_date, amount, place, category, payment, description)).fetchone()
            if installments and not duplicate:
                duplicate = db.execute("SELECT id FROM expenses WHERE installment_number=1 AND expense_date=? AND original_total=? AND lower(place)=lower(?) LIMIT 1", (installments[0]["date"], amount, place)).fetchone()
            if duplicate and payload.get("allow_duplicate") is not True:
                raise DuplicateExpenseError(f"Este gasto já existe no lançamento {duplicate['id']}")
        backup = create_backup()
        with connect() as db:
            if installments:
                ids = []
                for part in installments:
                    part_description = f"{description} · Parcela {part['number']}/{part['count']}".strip(" ·")
                    cursor = db.execute("INSERT INTO expenses(expense_date,amount,place,category,payment,description,installment_group,installment_number,installment_count,original_total,finance_details) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                        (part["date"], part["amount"], place, category, payment, part_description, part["group"], part["number"], part["count"], part["original_total"], json.dumps({**finance, **({"principal_part": part["amortization"], "interest_part": part["interest"], "balance_after": part["balance_after"]} if finance.get("debt_entry") else {})})))
                    ids.append(cursor.lastrowid)
                return {"row": ids[0], "id": ids[0], "ids": ids, "installment_group": installments[0]["group"], "backup": backup.name}
            cursor = db.execute("INSERT INTO expenses(expense_date,amount,place,category,payment,description,finance_details) VALUES(?,?,?,?,?,?,?)", (expense_date, amount, place, category, payment, description, json.dumps(finance)))
    return {"row": cursor.lastrowid, "id": cursor.lastrowid, "backup": backup.name}


def update_expense(item_id: int, payload: dict, user_id: int | None = None) -> dict:
    try:
        expense_date = date.fromisoformat(str(payload["date"])).isoformat()
        amount = round(float(payload["amount"]), 2)
        place, category = str(payload["where"]).strip(), str(payload["category"]).strip()
        payment, description = str(payload["payment"]).strip(), str(payload.get("description", "")).strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Preencha data, valor, local, categoria e pagamento") from exc
    if amount <= 0 or amount > 10_000_000 or not place or len(place) > 100 or len(description) > 200:
        raise ValueError("Revise os dados do gasto")
    if category not in set(read_categories()) or payment not in PAYMENTS:
        raise ValueError("Categoria ou pagamento inválido")
    expense_date, _, finance = expense_finance({**payload, "installment": False}, expense_date, payment)
    with LOCK:
        backup = create_backup()
        with connect() as db:
            current = db.execute("SELECT installment_group,finance_details FROM expenses WHERE id=?", (int(item_id),)).fetchone()
            if not current:
                raise KeyError("Gasto não encontrado")
            if json.loads(current["finance_details"]).get("paid"):
                raise ValueError("Desfaça a baixa antes de alterar uma parcela paga")
            if payload.get("scope") == "all" and current["installment_group"]:
                rows = db.execute("SELECT finance_details FROM expenses WHERE installment_group=?", (current["installment_group"],)).fetchall()
                if any(json.loads(row["finance_details"]).get("paid") for row in rows):
                    raise ValueError("Desfaça as baixas antes de alterar todas as parcelas")
            if payload.get("scope") == "all" and current["installment_group"]:
                cursor = db.execute("UPDATE expenses SET amount=?,original_total=?*installment_count,place=?,category=?,payment=?,description=CASE WHEN installment_number IS NOT NULL THEN ? || ' · Parcela ' || installment_number || '/' || installment_count ELSE ? END WHERE installment_group=?",
                                    (amount, amount, place, category, payment, description, description, current["installment_group"]))
            else:
                cursor = db.execute("UPDATE expenses SET expense_date=?,amount=?,place=?,category=?,payment=?,description=?,finance_details=CASE WHEN installment_group IS NULL THEN ? ELSE finance_details END WHERE id=?",
                                    (expense_date, amount, place, category, payment, description, json.dumps(finance), int(item_id)))
            if not cursor.rowcount:
                raise KeyError("Gasto não encontrado")
    return {"id": int(item_id), "backup": backup.name}


def update_debt(item_id: int, payload: dict, user_id: int | None = None) -> dict:
    draft = prepare_debt_update(payload, set(read_categories()), PAYMENTS)
    with LOCK:
        backup = create_backup()
        with connect() as db:
            current = db.execute("SELECT installment_group,finance_details FROM expenses WHERE id=?", (int(item_id),)).fetchone()
            if not current or not current["installment_group"] or json.loads(current["finance_details"]).get("financing_kind") not in {"loan", "debt", "asset"}:
                raise KeyError("Compromisso não encontrado")
            group = current["installment_group"]
            records = db.execute("SELECT * FROM expenses WHERE installment_group=? ORDER BY expense_date,installment_number", (group,)).fetchall()
            paid, pending = debt_revision(draft, records)
            db.executemany("DELETE FROM expenses WHERE id=?", ((row["id"],) for row in pending))
            ids = []
            for part in draft["parts"]:
                finance = {**draft["finance"], "principal_part": part["amortization"],
                           "interest_part": part["interest"], "balance_after": part["balance_after"]}
                description = f"{draft['description']} · Parcela {part['number']}/{part['count']}".strip(" ·")
                cursor = db.execute("INSERT INTO expenses(expense_date,amount,place,category,payment,description,installment_group,installment_number,installment_count,original_total,finance_details) VALUES(?,?,?,?,?,?,?,?,?,?,?)",
                                    (part["date"], part["amount"], draft["place"], draft["category"], draft["payment"], description,
                                     group, part["number"], part["count"], part["original_total"], json.dumps(finance)))
                ids.append(cursor.lastrowid)
    return {"id": ids[0], "ids": ids, "installment_group": group, "backup": backup.name, "paid_preserved": len(paid)}


def delete_expense(item_id: int, user_id: int | None = None, scope: str = "single") -> None:
    with LOCK:
        create_backup()
        with connect() as db:
            current = db.execute("SELECT installment_group FROM expenses WHERE id=?", (int(item_id),)).fetchone()
            if not current:
                raise KeyError("Gasto não encontrado")
            records = db.execute("SELECT finance_details FROM expenses WHERE installment_group=?", (current["installment_group"],)).fetchall() if scope == "all" and current["installment_group"] else db.execute("SELECT finance_details FROM expenses WHERE id=?", (int(item_id),)).fetchall()
            if any(json.loads(record["finance_details"]).get("paid") for record in records):
                raise ValueError("Desfaça a baixa das parcelas pagas antes de excluir")
            cursor = db.execute("DELETE FROM expenses WHERE installment_group=?", (current["installment_group"],)) if scope == "all" and current["installment_group"] else db.execute("DELETE FROM expenses WHERE id=?", (int(item_id),))
            if not cursor.rowcount:
                raise KeyError("Gasto não encontrado")


def read_incomes(user_id: int | None = None) -> dict[str, dict[str, float]]:
    initialize()
    with connect() as db:
        rows = db.execute("SELECT month,cash,voucher,payday,source FROM incomes").fetchall()
    return {row["month"]: {"cash": round(row["cash"], 2), "voucher": round(row["voucher"], 2), "payday": row["payday"], "source": row["source"]} for row in rows}


def set_income(payload: dict, user_id: int | None = None) -> dict:
    month = str(payload.get("month", ""))
    mode = payload.get("income_mode")
    if mode is not None and mode not in {'auto','declared','imported'}:raise ValueError('Escolha a origem usada no cálculo da renda')
    try:
        date.fromisoformat(f"{month}-01")
        cash, voucher = round(float(payload.get("cash", 0)), 2), round(float(payload.get("voucher", 0)), 2)
        payday = int(payload["payday"]) if payload.get("payday") not in (None, "") else None
        source = str(payload.get("source", "")).strip()
    except (TypeError, ValueError) as exc:
        raise ValueError("Mês ou valores de renda inválidos") from exc
    if min(cash, voucher) < 0 or max(cash, voucher) > 10_000_000:
        raise ValueError("Os valores de renda precisam ser positivos")
    if payday is not None and not 1 <= payday <= 31 or len(source) > 100:
        raise ValueError("Revise o dia ou a origem da renda")
    with LOCK:
        backup = create_backup()
        with connect() as db:
            db.execute("INSERT INTO incomes(month,cash,voucher,payday,source) VALUES(?,?,?,?,?) ON CONFLICT(month) DO UPDATE SET cash=excluded.cash,voucher=excluded.voucher,payday=excluded.payday,source=excluded.source,updated_at=CURRENT_TIMESTAMP",
                       (month, cash, voucher, payday, source))
            if mode is not None:
                row=db.execute("SELECT value FROM app_state WHERE key='investments'").fetchone()
                data=json.loads(row['value']) if row else {'version':1,'investments':[],'history':[]}
                data.setdefault('preferences',{}).setdefault('income_modes',{})[month]=mode
                db.execute("INSERT INTO app_state(key,value) VALUES('investments',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(data,ensure_ascii=False),))
    return {"month": month, "cash": cash, "voucher": voucher, "payday": payday, "source": source, "backup": backup.name}


def read_income_entries(user_id: int | None = None) -> list[dict]:
    initialize()
    with connect() as db:
        rows = db.execute("SELECT id,entry_date,amount,source,category,description FROM income_entries ORDER BY entry_date,id").fetchall()
    return [{"id": row["id"], "date": row["entry_date"], "amount": round(row["amount"], 2), "source": row["source"], "category": row["category"], "description": row["description"]} for row in rows]


def add_income_entry(payload: dict, user_id: int | None = None) -> dict:
    categories = {"Salário", "Pagamento recebido", "Transferência recebida", "Reembolso", "Rendimentos", "Outras entradas"}
    try:
        entry_date = date.fromisoformat(str(payload["date"])).isoformat()
        amount = round(float(payload["amount"]), 2)
        source, category = str(payload["where"]).strip(), str(payload["category"]).strip()
        description = str(payload.get("description", "")).strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Revise os dados da entrada") from exc
    if amount <= 0 or amount > 10_000_000 or not source or len(source) > 100 or category not in categories or len(description) > 200:
        raise ValueError("Revise os dados da entrada")
    initialize()
    with LOCK:
        with connect() as db:
            duplicate = db.execute("SELECT id FROM income_entries WHERE entry_date=? AND amount=? AND lower(source)=lower(?) AND category=? LIMIT 1", (entry_date, amount, source, category)).fetchone()
            if duplicate:
                raise DuplicateExpenseError(f"Esta entrada já existe no lançamento {duplicate['id']}")
        backup = create_backup()
        with connect() as db:
            cursor = db.execute("INSERT INTO income_entries(entry_date,amount,source,category,description) VALUES(?,?,?,?,?)", (entry_date, amount, source, category, description))
    return {"id": cursor.lastrowid, "backup": backup.name}


def read_budgets(user_id: int | None = None) -> dict[str, dict[str, float]]:
    initialize()
    with connect() as db:
        rows = db.execute("SELECT month,category,amount FROM budgets").fetchall()
    result: dict[str, dict[str, float]] = {}
    for row in rows:
        result.setdefault(row["month"], {})[row["category"]] = round(row["amount"], 2)
    return result


def set_budget(payload: dict, user_id: int | None = None) -> dict:
    month, category = str(payload.get("month", "")), str(payload.get("category", "")).strip()
    try:
        date.fromisoformat(f"{month}-01")
        amount = round(float(payload.get("limit", 0)), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError("Mês ou limite inválido") from exc
    if category not in set(read_categories()) or amount < 0 or amount > 10_000_000:
        raise ValueError("Categoria ou limite inválido")
    with LOCK:
        backup = create_backup()
        with connect() as db:
            db.execute("INSERT INTO budgets(month,category,amount) VALUES(?,?,?) ON CONFLICT(month,category) DO UPDATE SET amount=excluded.amount,updated_at=CURRENT_TIMESTAMP",
                       (month, category, amount))
    return {"month": month, "category": category, "limit": amount, "backup": backup.name}


def delete_budget(month: str, category: str, user_id: int | None = None) -> None:
    date.fromisoformat(f"{month}-01")
    with LOCK:
        create_backup()
        with connect() as db:
            db.execute("DELETE FROM budgets WHERE month=? AND category=?", (month, category))


def read_categories(user_id: int | None = None) -> list[str]:
    initialize()
    with connect() as db:
        rows = db.execute("SELECT name FROM budget_categories ORDER BY name COLLATE NOCASE").fetchall()
    return [row["name"] for row in rows]


def add_category(name: str, user_id: int | None = None) -> str:
    name = str(name).strip()
    if len(name) < 2 or len(name) > 40:
        raise ValueError("Use um nome de categoria entre 2 e 40 caracteres")
    with LOCK:
        create_backup()
        with connect() as db:
            db.execute("INSERT OR IGNORE INTO budget_categories(name) VALUES(?)", (name,))
    return name


def delete_category(name: str, user_id: int | None = None) -> None:
    name = str(name).strip()
    if name in CATEGORIES:
        raise ValueError("As categorias padrão não podem ser excluídas")
    with LOCK:
        create_backup()
        with connect() as db:
            if db.execute("SELECT 1 FROM expenses WHERE category=? LIMIT 1", (name,)).fetchone():
                raise ValueError("Esta categoria possui gastos e não pode ser excluída")
            db.execute("DELETE FROM budgets WHERE category=?", (name,))
            db.execute("DELETE FROM budget_categories WHERE name=?", (name,))


def rename_category(name: str, new_name: str, user_id: int | None = None) -> str:
    name, new_name = str(name).strip(), str(new_name).strip()
    if name in CATEGORIES:
        raise ValueError("As categorias padrão não podem ser renomeadas")
    if len(new_name) < 2 or len(new_name) > 40:
        raise ValueError("Use um nome de categoria entre 2 e 40 caracteres")
    with LOCK:
        create_backup()
        with connect() as db:
            if not db.execute("SELECT 1 FROM budget_categories WHERE name=?", (name,)).fetchone():
                raise KeyError("Categoria não encontrada")
            if db.execute("SELECT 1 FROM budget_categories WHERE name=?", (new_name,)).fetchone():
                raise ValueError("Já existe uma categoria com este nome")
            db.execute("INSERT OR IGNORE INTO budget_categories(name) VALUES(?)", (new_name,))
            db.execute("UPDATE expenses SET category=? WHERE category=?", (new_name, name))
            db.execute("UPDATE budgets SET category=? WHERE category=?", (new_name, name))
            db.execute("DELETE FROM budget_categories WHERE name=?", (name,))
    return new_name


def load_investments(user_id: int | None = None) -> dict:
    initialize()
    with connect() as db:
        row = db.execute("SELECT value FROM app_state WHERE key='investments'").fetchone()
    return json.loads(row["value"]) if row else {"version": 1, "updated_at": None, "investments": [], "history": []}


def save_investments(data: dict, user_id: int | None = None) -> None:
    with LOCK:
        create_backup()
        with connect() as db:
            db.execute("INSERT INTO app_state(key,value) VALUES('investments',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (json.dumps(data, ensure_ascii=False),))


def mutate_investments(operation, user_id: int | None = None):
    """Apply a portfolio change and its cash movement in one transaction."""
    initialize()
    with LOCK:
        create_backup()
        with connect() as db:
            db.execute("BEGIN IMMEDIATE")
            row = db.execute("SELECT value FROM app_state WHERE key='investments'").fetchone()
            data = json.loads(row["value"]) if row else {"version": 1, "updated_at": None, "investments": [], "history": []}
            result = operation(data)
            db.execute("INSERT INTO app_state(key,value) VALUES('investments',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                       (json.dumps(data, ensure_ascii=False),))
    return result


def set_debt_payment(item_id: int, payload: dict, user_id: int | None = None) -> dict:
    initialize()
    with LOCK:
        create_backup()
        with connect() as db:
            row = db.execute("SELECT finance_details FROM expenses WHERE id=?", (item_id,)).fetchone()
            if not row:
                raise KeyError("Parcela não encontrada")
            finance = debt_payment_metadata(json.loads(row["finance_details"]), payload)
            db.execute("UPDATE expenses SET finance_details=? WHERE id=?", (json.dumps(finance), item_id))
    return {"id": item_id, "finance": finance}


def export_financial_data(user_id: int | None = None) -> dict:
    try:from src import portability
    except ImportError:import portability
    initialize()
    with connect() as db:
        db.execute('BEGIN')
        tables={name:[dict(row) for row in db.execute('SELECT '+','.join(columns)+' FROM '+name).fetchall()] for name,columns in portability.TABLES.items()}
        row=db.execute("SELECT value FROM app_state WHERE key='investments'").fetchone()
        portfolio=json.loads(row['value']) if row else {'version':1,'investments':[],'history':[]}
    return portability.package(tables,portfolio)


def restore_financial_data(payload: dict, user_id: int | None = None) -> dict:
    try:from src import portability
    except ImportError:import portability
    data=portability.validate(payload)
    with LOCK:
        create_backup()
        with connect() as db:
            db.execute('BEGIN IMMEDIATE')
            tables={name:[dict(row) for row in db.execute('SELECT '+','.join(columns)+' FROM '+name).fetchall()] for name,columns in portability.TABLES.items()}
            row=db.execute("SELECT value FROM app_state WHERE key='investments'").fetchone()
            old=portability.package(tables,json.loads(row['value']) if row else {'investments':[],'history':[]})
            db.execute("INSERT INTO app_state(key,value) VALUES('safety_backup',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(old,ensure_ascii=False),))
            for name in portability.TABLES:db.execute('DELETE FROM '+name)
            for name,columns in portability.TABLES.items():
                for row in data[name]:
                    values=[json.dumps(row[key],ensure_ascii=False) if key=='finance_details' else row[key] for key in columns]
                    db.execute('INSERT INTO '+name+'('+','.join(columns)+') VALUES('+','.join('?' for _ in columns)+')',values)
            db.execute("INSERT INTO app_state(key,value) VALUES('investments',?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",(json.dumps(data['portfolio'],ensure_ascii=False),))
    return portability.counts(data)


def previous_financial_backup(user_id: int | None = None):
    initialize()
    with connect() as db:row=db.execute("SELECT value FROM app_state WHERE key='safety_backup'").fetchone()
    return json.loads(row['value']) if row else None


def delete_financial_account(user_id: int | None = None):
    with LOCK:
        with connect() as db:
            for table in ('expenses','incomes','income_entries','budgets','budget_categories','app_state'):db.execute('DELETE FROM '+table)
    for path in BACKUPS.glob('*.db'):path.unlink(missing_ok=True)


def backup_metadata(user_id=None):
    initialize()
    with connect() as db:row=db.execute("SELECT json_extract(value,'$.exported_at') AS date FROM app_state WHERE key='safety_backup'").fetchone()
    return {'available':bool(row),'date':row['date'] if row else None}
