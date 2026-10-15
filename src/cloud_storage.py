"""Persistência PostgreSQL no Neon para a versão hospedada."""

from __future__ import annotations

from datetime import date
import json
import os
from threading import Lock

import psycopg
from psycopg.rows import dict_row


CATEGORIES = {"Alimentação", "Mercado", "Transporte", "Moradia", "Saúde", "Educação", "Lazer", "Compras", "Assinaturas", "Contas", "Viagem", "Presentes", "Outros"}
PAYMENTS = {"Pix", "Crédito", "Débito", "Dinheiro", "Transferência", "Voucher", "Não informado"}
_INITIALIZED = False
_INIT_LOCK = Lock()


class DuplicateExpenseError(ValueError):
    pass


def connect():
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL não configurada")
    url = url.replace("postgresql+psycopg://", "postgresql://", 1).replace("postgresql+psycopg2://", "postgresql://", 1)
    return psycopg.connect(url, row_factory=dict_row, autocommit=False)


def initialize() -> None:
    global _INITIALIZED
    if _INITIALIZED:
        return
    with _INIT_LOCK:
        if _INITIALIZED:
            return
        with connect() as db, db.cursor() as cursor:
            cursor.execute("""
            CREATE TABLE IF NOT EXISTS expenses(id BIGSERIAL PRIMARY KEY,expense_date DATE NOT NULL,amount NUMERIC(14,2) NOT NULL CHECK(amount>0),place VARCHAR(100) NOT NULL,category VARCHAR(40) NOT NULL,payment VARCHAR(40) NOT NULL,description VARCHAR(200) NOT NULL DEFAULT '',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
            CREATE TABLE IF NOT EXISTS incomes(month VARCHAR(7) PRIMARY KEY,cash NUMERIC(14,2) NOT NULL DEFAULT 0,voucher NUMERIC(14,2) NOT NULL DEFAULT 0,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
            CREATE TABLE IF NOT EXISTS budgets(month VARCHAR(7) NOT NULL,category VARCHAR(40) NOT NULL,amount NUMERIC(14,2) NOT NULL DEFAULT 0,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(month,category));
            CREATE TABLE IF NOT EXISTS app_state(key VARCHAR(80) PRIMARY KEY,value JSONB NOT NULL);
        """)
            cursor.execute("INSERT INTO app_state(key,value) VALUES('investments',%s::jsonb) ON CONFLICT(key) DO NOTHING", (json.dumps({"version":1,"updated_at":None,"investments":[],"history":[]}),))
            db.commit()
        _INITIALIZED = True


def read_expenses() -> list[dict]:
    initialize()
    with connect() as db, db.cursor() as cursor:
        cursor.execute("SELECT id,expense_date,amount,place,category,payment,description FROM expenses ORDER BY expense_date,id")
        rows = cursor.fetchall()
    return [{"id":r["id"],"row":r["id"],"date":r["expense_date"].isoformat(),"amount":round(float(r["amount"]),2),"where":r["place"],"category":r["category"],"payment":r["payment"],"description":r["description"]} for r in rows]


def add_expense(payload: dict) -> dict:
    try:
        expense_date=date.fromisoformat(str(payload["date"])); amount=round(float(payload["amount"]),2); place=str(payload["where"]).strip(); category=str(payload["category"]).strip(); payment=str(payload["payment"]).strip(); description=str(payload.get("description","")).strip()
    except (KeyError,TypeError,ValueError) as exc: raise ValueError("Preencha data, valor, local, categoria e pagamento") from exc
    if amount<=0 or amount>10_000_000: raise ValueError("O valor deve ser maior que zero")
    if not place or len(place)>100 or len(description)>200: raise ValueError("Revise o local ou a descrição")
    if category not in CATEGORIES or payment not in PAYMENTS: raise ValueError("Categoria ou pagamento inválido")
    initialize()
    with connect() as db, db.cursor() as cursor:
        cursor.execute("SELECT id FROM expenses WHERE expense_date=%s AND amount=%s AND lower(place)=lower(%s) AND category=%s AND payment=%s AND lower(description)=lower(%s) LIMIT 1",(expense_date,amount,place,category,payment,description))
        duplicate=cursor.fetchone()
        if duplicate and payload.get("allow_duplicate") is not True: raise DuplicateExpenseError(f"Este gasto já existe no lançamento {duplicate['id']}")
        cursor.execute("INSERT INTO expenses(expense_date,amount,place,category,payment,description) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id",(expense_date,amount,place,category,payment,description)); item_id=cursor.fetchone()["id"]; db.commit()
    return {"row":item_id,"id":item_id}


def read_incomes() -> dict:
    initialize()
    with connect() as db, db.cursor() as cursor: cursor.execute("SELECT month,cash,voucher FROM incomes"); rows=cursor.fetchall()
    return {r["month"]:{"cash":round(float(r["cash"]),2),"voucher":round(float(r["voucher"]),2)} for r in rows}


def set_income(payload: dict) -> dict:
    month=str(payload.get("month",""))
    try: date.fromisoformat(f"{month}-01"); cash=round(float(payload.get("cash",0)),2); voucher=round(float(payload.get("voucher",0)),2)
    except (TypeError,ValueError) as exc: raise ValueError("Mês ou valores de renda inválidos") from exc
    if min(cash,voucher)<0 or max(cash,voucher)>10_000_000: raise ValueError("Os valores de renda precisam ser positivos")
    initialize()
    with connect() as db, db.cursor() as cursor: cursor.execute("INSERT INTO incomes(month,cash,voucher) VALUES(%s,%s,%s) ON CONFLICT(month) DO UPDATE SET cash=EXCLUDED.cash,voucher=EXCLUDED.voucher,updated_at=NOW()",(month,cash,voucher)); db.commit()
    return {"month":month,"cash":cash,"voucher":voucher}


def read_budgets() -> dict:
    initialize(); result={}
    with connect() as db, db.cursor() as cursor: cursor.execute("SELECT month,category,amount FROM budgets"); rows=cursor.fetchall()
    for r in rows: result.setdefault(r["month"],{})[r["category"]]=round(float(r["amount"]),2)
    return result


def set_budget(payload: dict) -> dict:
    month=str(payload.get("month","")); category=str(payload.get("category","")).strip()
    try: date.fromisoformat(f"{month}-01"); amount=round(float(payload.get("limit",0)),2)
    except (TypeError,ValueError) as exc: raise ValueError("Mês ou limite inválido") from exc
    if category not in CATEGORIES or amount<0 or amount>10_000_000: raise ValueError("Categoria ou limite inválido")
    initialize()
    with connect() as db, db.cursor() as cursor: cursor.execute("INSERT INTO budgets(month,category,amount) VALUES(%s,%s,%s) ON CONFLICT(month,category) DO UPDATE SET amount=EXCLUDED.amount,updated_at=NOW()",(month,category,amount)); db.commit()
    return {"month":month,"category":category,"limit":amount}


def load_investments() -> dict:
    initialize()
    with connect() as db, db.cursor() as cursor: cursor.execute("SELECT value FROM app_state WHERE key='investments'"); row=cursor.fetchone()
    return row["value"] if row else {"version":1,"updated_at":None,"investments":[],"history":[]}


def save_investments(data: dict) -> None:
    initialize()
    with connect() as db, db.cursor() as cursor: cursor.execute("INSERT INTO app_state(key,value) VALUES('investments',%s::jsonb) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value",(json.dumps(data,ensure_ascii=False),)); db.commit()
