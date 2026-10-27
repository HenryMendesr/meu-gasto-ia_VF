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
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
try:
    from src.finance_rules import installment_plan, expense_finance, prepare_debt_update, debt_payment_metadata
except ImportError:
    from finance_rules import installment_plan, expense_finance, prepare_debt_update, debt_payment_metadata

import psycopg
from psycopg.rows import dict_row

CATEGORIES={"Alimentação","Mercado","Transporte","Moradia","Saúde","Educação","Lazer","Compras","Assinaturas","Contas","Viagem","Presentes","Outros"}
PAYMENTS={"Pix","Crédito","Débito","Dinheiro","Transferência","Voucher","Não informado"}
_INITIALIZED=False
_INIT_LOCK=Lock()
PBKDF2_ITERATIONS=600_000
EMPTY_INVESTMENTS={"version":1,"updated_at":None,"investments":[],"history":[]}

class DuplicateExpenseError(ValueError): pass


def database_url()->str:
    """Normaliza a conexão copiada do Neon sem expor suas credenciais."""
    url=(os.environ.get("DATABASE_URL") or "").strip().strip('"').strip("'")
    if url.startswith("psql "):
        url=url[5:].strip().strip('"').strip("'")
    url=url.replace("postgresql+psycopg://","postgresql://",1).replace("postgresql+psycopg2://","postgresql://",1)
    if url.startswith("postgres://"):url="postgresql://"+url[len("postgres://"):]
    parsed=urlsplit(url)
    if parsed.scheme!="postgresql" or not parsed.hostname:raise RuntimeError("DATABASE_URL inválida ou não configurada")
    query=dict(parse_qsl(parsed.query,keep_blank_values=True))
    query.setdefault("sslmode","require")
    query.setdefault("connect_timeout","8")
    return urlunsplit((parsed.scheme,parsed.netloc,parsed.path,urlencode(query),parsed.fragment))


def connect():
    return psycopg.connect(database_url(),row_factory=dict_row,autocommit=False,application_name="minha-carteira")


def database_status()->dict:
    with connect() as db,db.cursor() as c:
        c.execute("SELECT current_database() AS name, 1 AS ready")
        row=c.fetchone()
    return {"connected":row["ready"]==1,"name":row["name"]}


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
            CREATE TABLE IF NOT EXISTS budget_categories(user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,name VARCHAR(40) NOT NULL,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),PRIMARY KEY(user_id,name));
            CREATE TABLE IF NOT EXISTS income_entries(id BIGSERIAL PRIMARY KEY,entry_date DATE NOT NULL,amount NUMERIC(14,2) NOT NULL CHECK(amount>0),source VARCHAR(100) NOT NULL,category VARCHAR(40) NOT NULL,description VARCHAR(200) NOT NULL DEFAULT '',user_id BIGINT NOT NULL REFERENCES users(id) ON DELETE CASCADE,created_at TIMESTAMPTZ NOT NULL DEFAULT NOW());
            ALTER TABLE expenses ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id) ON DELETE CASCADE;
            ALTER TABLE expenses ADD COLUMN IF NOT EXISTS installment_group VARCHAR(32);
            ALTER TABLE expenses ADD COLUMN IF NOT EXISTS installment_number INTEGER;
            ALTER TABLE expenses ADD COLUMN IF NOT EXISTS installment_count INTEGER;
            ALTER TABLE expenses ADD COLUMN IF NOT EXISTS original_total NUMERIC(14,2);
            ALTER TABLE expenses ADD COLUMN IF NOT EXISTS finance_details TEXT NOT NULL DEFAULT '{}';
            ALTER TABLE incomes ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id) ON DELETE CASCADE;
            ALTER TABLE incomes ADD COLUMN IF NOT EXISTS payday INTEGER;
            ALTER TABLE incomes ADD COLUMN IF NOT EXISTS source VARCHAR(100) NOT NULL DEFAULT '';
            ALTER TABLE budgets ADD COLUMN IF NOT EXISTS user_id BIGINT REFERENCES users(id) ON DELETE CASCADE;
            ALTER TABLE incomes DROP CONSTRAINT IF EXISTS incomes_pkey;
            ALTER TABLE budgets DROP CONSTRAINT IF EXISTS budgets_pkey;
            CREATE UNIQUE INDEX IF NOT EXISTS incomes_user_month_uidx ON incomes(user_id,month);
            CREATE UNIQUE INDEX IF NOT EXISTS budgets_user_month_category_uidx ON budgets(user_id,month,category);
            CREATE UNIQUE INDEX IF NOT EXISTS expenses_user_installment_uidx ON expenses(user_id,installment_group,installment_number) WHERE installment_group IS NOT NULL;
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
    import base64
    if not user:
        # Mantém custo semelhante para e-mails existentes e inexistentes.
        _password_digest(password,b'\0'*16)
        return None
    salt=base64.urlsafe_b64decode(user['password_salt']+'='*(-len(user['password_salt'])%4))
    if not hmac.compare_digest(_password_digest(password,salt),user['password_hash']):return None
    return {'id':user['id'],'name':user['name'],'email':user['email']}


def get_user(user_id:int)->dict|None:
    initialize()
    with connect() as db,db.cursor() as c:c.execute('SELECT id,name,email FROM users WHERE id=%s',(user_id,));row=c.fetchone()
    return dict(row) if row else None


def read_expenses(user_id:int)->list[dict]:
    initialize()
    with connect() as db,db.cursor() as c:c.execute('SELECT id,expense_date,amount,place,category,payment,description,installment_group,installment_number,installment_count,original_total,finance_details FROM expenses WHERE user_id=%s ORDER BY expense_date,id',(user_id,));rows=c.fetchall()
    return [{'id':r['id'],'row':r['id'],'date':r['expense_date'].isoformat(),'amount':round(float(r['amount']),2),'where':r['place'],'category':r['category'],'payment':r['payment'],'description':r['description'],'finance':json.loads(r['finance_details']),'installment_group':r['installment_group'],'installment_number':r['installment_number'],'installment_count':r['installment_count'],'original_total':round(float(r['original_total']),2) if r['original_total'] is not None else None} for r in rows]


def add_expense(payload:dict,user_id:int)->dict:
    try:expense_date=date.fromisoformat(str(payload['date']));amount=round(float(payload['amount']),2);place=str(payload['where']).strip();category=str(payload['category']).strip();payment=str(payload['payment']).strip();description=str(payload.get('description','')).strip()
    except (KeyError,TypeError,ValueError) as exc:raise ValueError('Preencha data, valor, local, categoria e pagamento') from exc
    if amount<=0 or amount>10_000_000:raise ValueError('O valor deve ser maior que zero')
    if not place or len(place)>100 or len(description)>200:raise ValueError('Revise o local ou a descrição')
    if category not in set(read_categories(user_id)) or payment not in PAYMENTS:raise ValueError('Categoria ou pagamento inválido')
    expense_date,installments,finance=expense_finance(payload,expense_date,payment)
    initialize()
    with connect() as db,db.cursor() as c:
        c.execute('SELECT id FROM expenses WHERE user_id=%s AND expense_date=%s AND amount=%s AND lower(place)=lower(%s) AND category=%s AND payment=%s AND lower(description)=lower(%s) LIMIT 1',(user_id,expense_date,amount,place,category,payment,description));duplicate=c.fetchone()
        if installments and not duplicate:c.execute('SELECT id FROM expenses WHERE user_id=%s AND installment_number=1 AND expense_date=%s AND original_total=%s AND lower(place)=lower(%s) LIMIT 1',(user_id,installments[0]['date'],amount,place));duplicate=c.fetchone()
        if duplicate and payload.get('allow_duplicate') is not True:raise DuplicateExpenseError(f"Este gasto já existe no lançamento {duplicate['id']}")
        if installments:
            ids=[]
            for part in installments:
                part_description=f"{description} · Parcela {part['number']}/{part['count']}".strip(' ·')
                c.execute('INSERT INTO expenses(user_id,expense_date,amount,place,category,payment,description,installment_group,installment_number,installment_count,original_total,finance_details) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',(user_id,part['date'],part['amount'],place,category,payment,part_description,part['group'],part['number'],part['count'],part['original_total'],json.dumps({**finance, **({"principal_part":part["amortization"],"interest_part":part["interest"],"balance_after":part["balance_after"]} if finance.get("debt_entry") else {})})));ids.append(c.fetchone()['id'])
            db.commit();return {'row':ids[0],'id':ids[0],'ids':ids,'installment_group':installments[0]['group']}
        c.execute('INSERT INTO expenses(user_id,expense_date,amount,place,category,payment,description,finance_details) VALUES(%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',(user_id,expense_date,amount,place,category,payment,description,json.dumps(finance)));item_id=c.fetchone()['id'];db.commit()
    return {'row':item_id,'id':item_id}


def update_expense(item_id:int,payload:dict,user_id:int)->dict:
    try:expense_date=date.fromisoformat(str(payload['date']));amount=round(float(payload['amount']),2);place=str(payload['where']).strip();category=str(payload['category']).strip();payment=str(payload['payment']).strip();description=str(payload.get('description','')).strip()
    except (KeyError,TypeError,ValueError) as exc:raise ValueError('Preencha data, valor, local, categoria e pagamento') from exc
    if amount<=0 or amount>10_000_000 or not place or len(place)>100 or len(description)>200:raise ValueError('Revise os dados do gasto')
    if category not in set(read_categories(user_id)) or payment not in PAYMENTS:raise ValueError('Categoria ou pagamento inválido')
    expense_date,_,finance=expense_finance({**payload,"installment":False},expense_date,payment)
    with connect() as db,db.cursor() as c:
        c.execute('SELECT installment_group,finance_details FROM expenses WHERE id=%s AND user_id=%s FOR UPDATE',(item_id,user_id));current=c.fetchone()
        if not current:raise KeyError('Gasto não encontrado')
        if json.loads(current['finance_details']).get('paid'):raise ValueError('Desfaça a baixa antes de alterar uma parcela paga')
        if payload.get('scope')=='all' and current['installment_group']:
            c.execute('SELECT finance_details FROM expenses WHERE user_id=%s AND installment_group=%s FOR UPDATE',(user_id,current['installment_group']))
            if any(json.loads(row['finance_details']).get('paid') for row in c.fetchall()):raise ValueError('Desfaça as baixas antes de alterar todas as parcelas')
        if payload.get('scope')=='all' and current['installment_group']:
            c.execute("UPDATE expenses SET amount=%s,original_total=%s*installment_count,place=%s,category=%s,payment=%s,description=%s || ' · Parcela ' || installment_number || '/' || installment_count WHERE user_id=%s AND installment_group=%s",(amount,amount,place,category,payment,description,user_id,current['installment_group']))
        else:c.execute('UPDATE expenses SET expense_date=%s,amount=%s,place=%s,category=%s,payment=%s,description=%s,finance_details=CASE WHEN installment_group IS NULL THEN %s ELSE finance_details END WHERE id=%s AND user_id=%s',(expense_date,amount,place,category,payment,description,json.dumps(finance),item_id,user_id))
        if not c.rowcount:raise KeyError('Gasto não encontrado')
        db.commit()
    return {'id':item_id}


def update_debt(item_id: int, payload: dict, user_id: int) -> dict:
    draft = prepare_debt_update(payload, set(read_categories(user_id)), PAYMENTS)
    with connect() as db, db.cursor() as c:
        c.execute('SELECT installment_group,finance_details FROM expenses WHERE id=%s AND user_id=%s FOR UPDATE', (item_id, user_id))
        current = c.fetchone()
        if not current or not current['installment_group'] or json.loads(current['finance_details']).get('financing_kind') not in {'loan', 'debt', 'asset'}:
            raise KeyError('Compromisso não encontrado')
        group = current['installment_group']
        c.execute('SELECT finance_details FROM expenses WHERE user_id=%s AND installment_group=%s FOR UPDATE', (user_id, group))
        if any(json.loads(row['finance_details']).get('paid') for row in c.fetchall()):
            raise ValueError('Há parcelas pagas. Desfaça a baixa antes de alterar o contrato')
        c.execute('DELETE FROM expenses WHERE user_id=%s AND installment_group=%s', (user_id, group))
        ids = []
        for part in draft['parts']:
            finance = {**draft['finance'], 'principal_part': part['amortization'],
                       'interest_part': part['interest'], 'balance_after': part['balance_after']}
            description = f"{draft['description']} · Parcela {part['number']}/{part['count']}".strip(' ·')
            c.execute('INSERT INTO expenses(user_id,expense_date,amount,place,category,payment,description,installment_group,installment_number,installment_count,original_total,finance_details) VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING id',
                      (user_id, part['date'], part['amount'], draft['place'], draft['category'], draft['payment'], description,
                       group, part['number'], part['count'], part['original_total'], json.dumps(finance)))
            ids.append(c.fetchone()['id'])
        db.commit()
    return {'id': ids[0], 'ids': ids, 'installment_group': group}


def delete_expense(item_id:int,user_id:int,scope:str='single')->None:
    with connect() as db,db.cursor() as c:
        c.execute('SELECT installment_group FROM expenses WHERE id=%s AND user_id=%s',(item_id,user_id));current=c.fetchone()
        if not current:raise KeyError('Gasto não encontrado')
        if scope=='all' and current['installment_group']:
            c.execute('SELECT finance_details FROM expenses WHERE user_id=%s AND installment_group=%s FOR UPDATE',(user_id,current['installment_group']))
        else:c.execute('SELECT finance_details FROM expenses WHERE id=%s AND user_id=%s FOR UPDATE',(item_id,user_id))
        if any(json.loads(row['finance_details']).get('paid') for row in c.fetchall()):raise ValueError('Desfaça a baixa das parcelas pagas antes de excluir')
        if scope=='all' and current['installment_group']:c.execute('DELETE FROM expenses WHERE user_id=%s AND installment_group=%s',(user_id,current['installment_group']))
        else:c.execute('DELETE FROM expenses WHERE id=%s AND user_id=%s',(item_id,user_id))
        if not c.rowcount:raise KeyError('Gasto não encontrado')
        db.commit()


def read_incomes(user_id:int)->dict:
    initialize()
    with connect() as db,db.cursor() as c:c.execute('SELECT month,cash,voucher,payday,source FROM incomes WHERE user_id=%s',(user_id,));rows=c.fetchall()
    return {r['month']:{'cash':round(float(r['cash']),2),'voucher':round(float(r['voucher']),2),'payday':r['payday'],'source':r['source']} for r in rows}


def set_income(payload:dict,user_id:int)->dict:
    month=str(payload.get('month',''))
    try:date.fromisoformat(f'{month}-01');cash=round(float(payload.get('cash',0)),2);voucher=round(float(payload.get('voucher',0)),2);payday=int(payload['payday']) if payload.get('payday') not in (None,'') else None;source=str(payload.get('source','')).strip()
    except (TypeError,ValueError) as exc:raise ValueError('Mês ou valores de renda inválidos') from exc
    if min(cash,voucher)<0 or max(cash,voucher)>10_000_000:raise ValueError('Os valores de renda precisam ser positivos')
    if payday is not None and not 1<=payday<=31 or len(source)>100:raise ValueError('Revise o dia ou a origem da renda')
    initialize()
    with connect() as db,db.cursor() as c:c.execute('INSERT INTO incomes(user_id,month,cash,voucher,payday,source) VALUES(%s,%s,%s,%s,%s,%s) ON CONFLICT(user_id,month) DO UPDATE SET cash=EXCLUDED.cash,voucher=EXCLUDED.voucher,payday=EXCLUDED.payday,source=EXCLUDED.source,updated_at=NOW()',(user_id,month,cash,voucher,payday,source));db.commit()
    return {'month':month,'cash':cash,'voucher':voucher,'payday':payday,'source':source}


def read_income_entries(user_id:int)->list[dict]:
    initialize()
    with connect() as db,db.cursor() as c:c.execute('SELECT id,entry_date,amount,source,category,description FROM income_entries WHERE user_id=%s ORDER BY entry_date,id',(user_id,));rows=c.fetchall()
    return [{'id':r['id'],'date':r['entry_date'].isoformat(),'amount':round(float(r['amount']),2),'source':r['source'],'category':r['category'],'description':r['description']} for r in rows]


def add_income_entry(payload:dict,user_id:int)->dict:
    categories={'Salário','Pagamento recebido','Transferência recebida','Reembolso','Rendimentos','Outras entradas'}
    try:entry_date=date.fromisoformat(str(payload['date']));amount=round(float(payload['amount']),2);source=str(payload['where']).strip();category=str(payload['category']).strip();description=str(payload.get('description','')).strip()
    except (KeyError,TypeError,ValueError) as exc:raise ValueError('Revise os dados da entrada') from exc
    if amount<=0 or amount>10_000_000 or not source or len(source)>100 or category not in categories or len(description)>200:raise ValueError('Revise os dados da entrada')
    initialize()
    with connect() as db,db.cursor() as c:
        c.execute('SELECT id FROM income_entries WHERE user_id=%s AND entry_date=%s AND amount=%s AND lower(source)=lower(%s) AND category=%s LIMIT 1',(user_id,entry_date,amount,source,category));duplicate=c.fetchone()
        if duplicate:raise DuplicateExpenseError(f"Esta entrada já existe no lançamento {duplicate['id']}")
        c.execute('INSERT INTO income_entries(user_id,entry_date,amount,source,category,description) VALUES(%s,%s,%s,%s,%s,%s) RETURNING id',(user_id,entry_date,amount,source,category,description));item_id=c.fetchone()['id'];db.commit()
    return {'id':item_id}


def read_budgets(user_id:int)->dict:
    initialize();result={}
    with connect() as db,db.cursor() as c:c.execute('SELECT month,category,amount FROM budgets WHERE user_id=%s',(user_id,));rows=c.fetchall()
    for r in rows:result.setdefault(r['month'],{})[r['category']]=round(float(r['amount']),2)
    return result


def set_budget(payload:dict,user_id:int)->dict:
    month=str(payload.get('month',''));category=str(payload.get('category','')).strip()
    try:date.fromisoformat(f'{month}-01');amount=round(float(payload.get('limit',0)),2)
    except (TypeError,ValueError) as exc:raise ValueError('Mês ou limite inválido') from exc
    if category not in set(read_categories(user_id)) or amount<0 or amount>10_000_000:raise ValueError('Categoria ou limite inválido')
    initialize()
    with connect() as db,db.cursor() as c:c.execute('INSERT INTO budgets(user_id,month,category,amount) VALUES(%s,%s,%s,%s) ON CONFLICT(user_id,month,category) DO UPDATE SET amount=EXCLUDED.amount,updated_at=NOW()',(user_id,month,category,amount));db.commit()
    return {'month':month,'category':category,'limit':amount}


def delete_budget(month:str,category:str,user_id:int)->None:
    date.fromisoformat(f'{month}-01')
    with connect() as db,db.cursor() as c:c.execute('DELETE FROM budgets WHERE user_id=%s AND month=%s AND category=%s',(user_id,month,category));db.commit()


def read_categories(user_id:int)->list[str]:
    initialize()
    with connect() as db,db.cursor() as c:
        c.executemany('INSERT INTO budget_categories(user_id,name) VALUES(%s,%s) ON CONFLICT DO NOTHING',((user_id,name) for name in sorted(CATEGORIES)))
        c.execute('SELECT name FROM budget_categories WHERE user_id=%s ORDER BY name',(user_id,));rows=c.fetchall();db.commit()
    return [r['name'] for r in rows]


def add_category(name:str,user_id:int)->str:
    name=str(name).strip()
    if len(name)<2 or len(name)>40:raise ValueError('Use um nome de categoria entre 2 e 40 caracteres')
    initialize()
    with connect() as db,db.cursor() as c:c.execute('INSERT INTO budget_categories(user_id,name) VALUES(%s,%s) ON CONFLICT DO NOTHING',(user_id,name));db.commit()
    return name


def delete_category(name:str,user_id:int)->None:
    name=str(name).strip()
    if name in CATEGORIES:raise ValueError('As categorias padrão não podem ser excluídas')
    with connect() as db,db.cursor() as c:
        c.execute('SELECT 1 FROM expenses WHERE user_id=%s AND category=%s LIMIT 1',(user_id,name))
        if c.fetchone():raise ValueError('Esta categoria possui gastos e não pode ser excluída')
        c.execute('DELETE FROM budgets WHERE user_id=%s AND category=%s',(user_id,name));c.execute('DELETE FROM budget_categories WHERE user_id=%s AND name=%s',(user_id,name));db.commit()


def rename_category(name:str,new_name:str,user_id:int)->str:
    name,new_name=str(name).strip(),str(new_name).strip()
    if name in CATEGORIES:raise ValueError('As categorias padrão não podem ser renomeadas')
    if len(new_name)<2 or len(new_name)>40:raise ValueError('Use um nome de categoria entre 2 e 40 caracteres')
    with connect() as db,db.cursor() as c:
        c.execute('SELECT 1 FROM budget_categories WHERE user_id=%s AND name=%s',(user_id,name))
        if not c.fetchone():raise KeyError('Categoria não encontrada')
        c.execute('SELECT 1 FROM budget_categories WHERE user_id=%s AND name=%s',(user_id,new_name))
        if c.fetchone():raise ValueError('Já existe uma categoria com este nome')
        c.execute('INSERT INTO budget_categories(user_id,name) VALUES(%s,%s) ON CONFLICT DO NOTHING',(user_id,new_name));c.execute('UPDATE expenses SET category=%s WHERE user_id=%s AND category=%s',(new_name,user_id,name));c.execute('UPDATE budgets SET category=%s WHERE user_id=%s AND category=%s',(new_name,user_id,name));c.execute('DELETE FROM budget_categories WHERE user_id=%s AND name=%s',(user_id,name));db.commit()
    return new_name


def load_investments(user_id:int)->dict:
    initialize();key=f'investments:{user_id}'
    with connect() as db,db.cursor() as c:c.execute('SELECT value FROM app_state WHERE key=%s',(key,));row=c.fetchone()
    return row['value'] if row else dict(EMPTY_INVESTMENTS)


def save_investments(data:dict,user_id:int)->None:
    initialize();key=f'investments:{user_id}'
    with connect() as db,db.cursor() as c:c.execute('INSERT INTO app_state(key,value) VALUES(%s,%s::jsonb) ON CONFLICT(key) DO UPDATE SET value=EXCLUDED.value',(key,json.dumps(data,ensure_ascii=False)));db.commit()


def mutate_investments(operation, user_id: int):
    """Lock this user's portfolio while updating assets and available cash."""
    initialize()
    key = f'investments:{user_id}'
    with connect() as db, db.cursor() as c:
        c.execute('INSERT INTO app_state(key,value) VALUES(%s,%s::jsonb) ON CONFLICT(key) DO NOTHING',
                  (key, json.dumps(EMPTY_INVESTMENTS)))
        c.execute('SELECT value FROM app_state WHERE key=%s FOR UPDATE', (key,))
        data = c.fetchone()['value']
        result = operation(data)
        c.execute('UPDATE app_state SET value=%s::jsonb WHERE key=%s', (json.dumps(data, ensure_ascii=False), key))
        db.commit()
    return result


def set_debt_payment(item_id: int, payload: dict, user_id: int) -> dict:
    with connect() as db, db.cursor() as c:
        c.execute('SELECT finance_details FROM expenses WHERE id=%s AND user_id=%s FOR UPDATE', (item_id, user_id))
        row = c.fetchone()
        if not row:
            raise KeyError('Parcela não encontrada')
        finance = debt_payment_metadata(json.loads(row['finance_details']), payload)
        c.execute('UPDATE expenses SET finance_details=%s WHERE id=%s AND user_id=%s', (json.dumps(finance), item_id, user_id))
        db.commit()
    return {'id': item_id, 'finance': finance}
