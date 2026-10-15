"""Persistência PostgreSQL multiusuário no Neon."""
from __future__ import annotations

from base64 import urlsafe_b64encode
from datetime import date
import hashlib
import hmac
import json
import os
import re
import secrets
from threading import Lock

import psycopg
from psycopg.rows import dict_row

CATEGORIES={"Alimentação","Mercado","Transporte","Moradia","Saúde","Educação","Lazer","Compras","Assinaturas","Contas","Viagem","Presentes","Outros"}
PAYMENTS={"Pix","Crédito","Débito","Dinheiro","Transferência","Voucher","Não informado"}
_INITIALIZED=False
_INIT_LOCK=Lock()
PBKDF2_ITERATIONS=600_000
EMPTY_INVESTMENTS={"version":1,"updated_at":None,"investments":[],"history":[]}

class DuplicateExpenseError(ValueError): pass


def connect():
    url=os.environ.get("DATABASE_URL")
    if not url: raise RuntimeError("DATABASE_URL não configurada")
    url=url.replace("postgresql+psycopg://","postgresql://",1).replace("postgresql+psycopg2://","postgresql://",1)
    return psycopg.connect(url,row_factory=dict_row,autocommit=False)


def initialize():
    global _INITIALIZED
    if _INITIALIZED:return
    with _INIT_LOCK:
        if _INITIALIZED:return
        with connect() as db,db.cursor() as c:
            c.execute("""
            CREATE TABLE IF NOT EXISTS users(id BIGSERIAL PRIMARY KEY,name VARCHAR(80) NOT NULL,email VARCHAR(254) NOT NULL,password_salt VARCHAR(64) NOT NULL,password_hash VARCHAR(128) NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
            CREATE UNIQUE INDEX IF NOT EXISTS users_email_lower_uidx ON users((lower(email)));
            CREATE TABLE IF NOT EXISTS expenses(id BIGSERIAL PRIMARY KEY,expense_date DATE NOT NULL,amount NUMERIC(14,2) NOT NULL CHECK(amount>0),place VARCHAR(100) NOT NULL,category VARCHAR(40) NOT NULL,payment VARCHAR(40) NOT NULL,description VARCHAR(200) NOT NULL DEFAULT '',created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
            CREATE TABLE IF NOT EXISTS incomes(month VARCHAR(7) PRIMARY KEY,cash NUMERIC(14,2) NOT NULL DEFAULT 0,voucher NUMERIC(14,2) NOT NULL DEFAULT 0,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
            CREATE TABLE IF NOT EXISTS budgets(month VARCHAR(7) NOT NULL,category VARCHAR(40) NOT NULL,amount NUMERIC(14,2) NOT NULL DEFAULT 0,updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(month,category));
            CREATE TABLE IF NOT EXISTS app_state(key VARCHAR(80) PRIMARY KEY,value JSONB NOT NULL);
            ALTER TABLE expenses ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id) ON DELETE CASCADE;
            ALTER TABLE incomes ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id) ON DELETE CASCADE;
            ALTER TABLE budgets ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id) ON DELETE CASCADE;
            ALTER TABLE incomes DROP CONSTRAINT IF EXISTS incomes_pkey;
            ALTER TABLE budgets DROP CONSTRAINT IF EXISTS budgets_pkey;
            CREATE UNIQUE INDEX IF NOT EXISTS incomes_user_month_uidx ON incomes(user_id,month);
            CREATE UNIQUE INDEX IF NOT EXISTS budgets_user_month_category_uidx ON budgets(user_id,month,category);
            """)
            c.execute("INSERT INTO app_state(key,value) VALUES('investments',%s::jsonb) ON CONFLICT(key) DO NOTHING",(json.dumps(EMPTY_INVESTMENTS),))
            db.commit()
        _INITIALIZED=True


def _encoded(raw:bytes)->str:return urlsafe_b64encode(raw).decode().rstrip('=')
def _password_digest(password:str,salt:bytes)->str:return _encoded(hashlib.pbkdf2_hmac('sha256',password.encode(),salt,PBKDF2_ITERATIONS))
def _valid_email(email:str)->bool:return bool(re.fullmatch(r"[^\s@]+@[^\s@]+\.[^\s@]+",email)) and len(email)<=254


def register_user(name:str,email:str,password:str,invitation_code:str)->dict:
    initialize();name=name.strip();email=email.strip().lower()
    expected=os.environ.get('REGISTRATION_CODE') or os.environ.get('APP_PASSWORD','')
    if not expected or not hmac.compare_digest(invitation_code,expected):raise ValueError('Código de convite inválido')
    if len(name)<2 or len(name)>80:raise ValueError('Informe seu nome')
    if not _valid_email(email):raise ValueError('Informe um e-mail válido')
    if len(password)<10 or len(password)>200:raise ValueError('Use uma senha com pelo menos 10 caracteres')
    salt=secrets.token_bytes(16)
    try:
        with connect() as db,db.cursor() as c:
            # Serializa cadastros para que apenas uma conta possa assumir dados legados.
            c.execute("SELECT pg_advisory_xact_lock(732614092)")
            c.execute("INSERT INTO users(name,email,password_salt,password_hash) VALUES(%s,%s,%s,%s) RETURNING id,name,email",(name,email,_encoded(salt),_password_digest(password,salt)))
            user=c.fetchone();uid=user['id']
            c.execute('SELECT COUNT(*) AS total FROM users');first=c.fetchone()['total']==1
            if first:
                c.execute('UPDATE expenses SET user_id=%s WHERE user_id IS NULL',(uid,))
                c.execute('UPDATE incomes SET user_id=%s WHERE user_id IS NULL',(uid,))
                c.execute('UPDATE budgets SET user_id=%s WHERE user_id IS NULL',(uid,))
                c.execute("UPDATE app_state SET key=%s WHERE key='investments' AND NOT EXISTS(SELECT 1 FROM app_state WHERE key=%s)",(f'investments:{uid}',f'investments:{uid}'))
            c.execute("INSERT INTO app_state(key,value) VALUES(%s,%s::jsonb) ON CONFLICT(key) DO NOTHING",(f'investments:{uid}',json.dumps(EMPTY_INVESTMENTS)))
            db.commit()
        return dict(user)
    except psycopg.errors.UniqueViolation as exc:raise ValueError('Este e-mail já está cadastrado') from exc


def authenticate_user(email:str,password:str)->dict|None:
    initialize()
    if len(password)>200:return None
    with connect() as db,db.cursor() as c:
        c.execute('SELECT id,name,email,password_salt,password_hash FROM users WHERE lower(email)=lower(%s)',(email.strip(),));user=c.fetchone()
    if not user:return None
    import base64
    salt=base64.urlsafe_b64decode(user['password_salt']+'='*(-len(user['password_salt'])%4))
    if not hmac.compare_digest(_password_digest(password,salt),user['password_hash']):return None
    return {'id':user['id'],'name':user['name'],'email':user['email']}


def get_user(user_id:int)->dict|None:
    initialize()
    with connect() as db,db.cursor() as c:c.execute('SELECT id,name,email FROM users WHERE id=%s',(user_id,));row=c.fetchone()
    return dict(row) if row else None


def read_expenses(user_id:int)->list[dict]:
    initialize()
    with connect() as db,db.cursor() as c:c.execute('SELECT id,expense_date,amount,place,category,payment,description FROM expenses WHERE user_id=%s ORDER BY expense_date,id',(user_id,));rows=c.fetchall()
    return [{'id':r['id'],'row':r['id'],'date':r['expense_date'].isoformat(),'amount':round(float(r['amount']),2),'where':r['place'],'category':r['category'],'payment':r['payment'],'description':r['description']} for r in rows]


def add_expense(payload:dict,user_id:int)->dict:
    try:expense_date=date.fromisoformat(str(payload['date']));amount=round(float(payload['amount']),2);place=str(payload['where']).strip();category=str(payload['category']).strip();payment=str(payload['payment']).strip();description=str(payload.get('description','')).strip()
    except (KeyError,TypeError,ValueError) as exc:raise ValueError('Preencha data, valor, local, categoria e pagamento') from exc
    if amount<=0 or amount>10_000_000:raise ValueError('O valor deve ser maior que zero')
    if not place or len(place)>100 or len(description)>200:raise ValueError('Revise o local ou a descrição')
    if category not in CATEGORIES or payment not in PAYMENTS:raise ValueError('Categoria ou pagamento inválido')
    initialize()
    with connect() as db,db.cursor() as c:
        c.execute('SELECT id FROM expenses WHERE user_id=%s AND expense_date=%s AND amount=%s AND lower(place)=lower(%s) AND category=%s AND payment=%s AND lower(description)=lower(%s) LIMIT 1',(user_id,expense_date,amount,place,category,payment,description));duplicate=c.fetchone()
        if duplicate and payload.get('allow_duplicate') is not True:raise DuplicateExpenseError(f"Este gasto já existe no lançamento {duplicate['id']}")
        c.execute('INSERT INTO expenses(user_id,expense_date,amount,place,category,payment,description) VALUES(%s,%s,%s,%s,%s,%s,%s) RETURNING id',(user_id,expense_date,amount,place,category,payment,description));item_id=c.fetchone()['id'];db.commit()
    return {'row':item_id,'id':item_id}


def read_incomes(user_id:int)->dict:
    initialize()
    with connect() as db,db.cursor() as c:c.execute('SELECT month,cash,voucher FROM incomes WHERE user_id=%s',(user_id,));rows=c.fetchall()
    return {r['month']:{'cash':round(float(r['cash']),2),'voucher':round(float(r['voucher']),2)} for r in rows}


def set_income(payload:dict,user_id:int)->dict:
    month=str(payload.get('month',''))
    try:date.fromisoformat(f'{month}-01');cash=round(float(payload.get('cash',0)),2);voucher=round(float(payload.get('voucher',0)),2)
    except (TypeError,ValueError) as exc:raise ValueError('Mês ou valores de renda inválidos') from exc
    if min(cash,voucher)<0 or max(cash,voucher)>10_000_000:raise ValueError('Os valores de renda precisam ser positivos')
    initialize()
    with connect() as db,db.cursor() as c:c.execute('INSERT INTO incomes(user_id,month,cash,voucher) VALUES(%s,%s,%s,%s) ON CONFLICT(user_id,month) DO UPDATE SET cash=EXCLUDED.cash,voucher=EXCLUDED.voucher,updated_at=NOW()',(user_id,month,cash,voucher));db.commit()
    return {'month':month,'cash':cash,'voucher':voucher}


def read_budgets(user_id:int)->dict:
    initialize();result={}
    with connect() as db,db.cursor() as c:c.execute('SELECT month,category,amount FROM budgets WHERE user_id=%s',(user_id,));rows=c.fetchall()
    for r in rows:result.setdefault(r['month'],{})[r['category']]=round(float(r['amount']),2)
    return result


def set_budget(payload:dict,user_id:int)->dict:
    month=str(payload.get('month',''));category=str(payload.get('category','')).strip()
    try:date.fromisoformat(f'{month}-01');amount=round(float(payload.get('limit',0)),2)
    except (TypeError,ValueError) as exc:raise ValueError('Mês ou limite inválido') from exc
    if category not in CATEGORIES or amount<0 or amount>10_000_000:raise ValueError('Categoria ou limite inválido')
    initialize()
    with connect() as db,db.cursor() as c:c.execute('INSERT INTO budgets(user_id,month,category,amount) VALUES(%s,%s,%s,%s) ON CONFLICT(user_id,month,category) DO UPDATE SET amount=EXCLUDED.amount,updated_at=NOW()',(user_id,month,category,amount));db.commit()
    return {'month':month,'category':category,'limit':amount}


def load_investments(user_id:int)->dict:
    initialize();key=f'investments:{user_id}'
    with connect() as db,db.cursor() as c:c.execute('SELECT value FROM app_state WHERE key=%s',(key,));row=c.fetchone()
    return row['value'] if row else dict(EMPTY_INVESTMENTS)


def save_investments(data:dict,user_id:int)->None:
    initialize();key=f'investments:{user_id}'
    with connect() as db,db.cursor() as c:c.execute('INSERT INTO app_state(key,value) VALUES(%s,%s::jsonb) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value',(key,json.dumps(data,ensure_ascii=False)));db.commit()
