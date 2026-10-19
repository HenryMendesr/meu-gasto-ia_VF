"""Banco de dados local e backups do Minha Carteira."""

from __future__ import annotations

from datetime import date, datetime
import json
from pathlib import Path
import sqlite3
from threading import Lock


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
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE TABLE IF NOT EXISTS incomes (
                month TEXT PRIMARY KEY,
                cash REAL NOT NULL DEFAULT 0,
                voucher REAL NOT NULL DEFAULT 0,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
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
        rows = db.execute("SELECT id,expense_date,amount,place,category,payment,description FROM expenses ORDER BY expense_date,id").fetchall()
    return [{"id": row["id"], "row": row["id"], "date": row["expense_date"], "amount": round(row["amount"], 2),
             "where": row["place"], "category": row["category"], "payment": row["payment"], "description": row["description"]} for row in rows]


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
    initialize()
    with LOCK:
        with connect() as db:
            duplicate = db.execute("SELECT id FROM expenses WHERE expense_date=? AND amount=? AND lower(place)=lower(?) AND category=? AND payment=? AND lower(description)=lower(?) LIMIT 1",
                                   (expense_date, amount, place, category, payment, description)).fetchone()
            if duplicate and payload.get("allow_duplicate") is not True:
                raise DuplicateExpenseError(f"Este gasto já existe no lançamento {duplicate['id']}")
        backup = create_backup()
        with connect() as db:
            cursor = db.execute("INSERT INTO expenses(expense_date,amount,place,category,payment,description) VALUES(?,?,?,?,?,?)",
                                (expense_date, amount, place, category, payment, description))
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
    with LOCK:
        backup = create_backup()
        with connect() as db:
            cursor = db.execute("UPDATE expenses SET expense_date=?,amount=?,place=?,category=?,payment=?,description=? WHERE id=?",
                                (expense_date, amount, place, category, payment, description, int(item_id)))
            if not cursor.rowcount:
                raise KeyError("Gasto não encontrado")
    return {"id": int(item_id), "backup": backup.name}


def delete_expense(item_id: int, user_id: int | None = None) -> None:
    with LOCK:
        create_backup()
        with connect() as db:
            cursor = db.execute("DELETE FROM expenses WHERE id=?", (int(item_id),))
            if not cursor.rowcount:
                raise KeyError("Gasto não encontrado")


def read_incomes(user_id: int | None = None) -> dict[str, dict[str, float]]:
    initialize()
    with connect() as db:
        rows = db.execute("SELECT month,cash,voucher FROM incomes").fetchall()
    return {row["month"]: {"cash": round(row["cash"], 2), "voucher": round(row["voucher"], 2)} for row in rows}


def set_income(payload: dict, user_id: int | None = None) -> dict:
    month = str(payload.get("month", ""))
    try:
        date.fromisoformat(f"{month}-01")
        cash, voucher = round(float(payload.get("cash", 0)), 2), round(float(payload.get("voucher", 0)), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError("Mês ou valores de renda inválidos") from exc
    if min(cash, voucher) < 0 or max(cash, voucher) > 10_000_000:
        raise ValueError("Os valores de renda precisam ser positivos")
    with LOCK:
        backup = create_backup()
        with connect() as db:
            db.execute("INSERT INTO incomes(month,cash,voucher) VALUES(?,?,?) ON CONFLICT(month) DO UPDATE SET cash=excluded.cash,voucher=excluded.voucher,updated_at=CURRENT_TIMESTAMP",
                       (month, cash, voucher))
    return {"month": month, "cash": cash, "voucher": voucher, "backup": backup.name}


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
