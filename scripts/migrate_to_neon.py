"""Migra uma única vez o banco SQLite local para a conta escolhida no Neon."""
from argparse import ArgumentParser
import os
from pathlib import Path
import sys

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from src import cloud_storage,storage  # noqa: E402


def main():
    parser=ArgumentParser(description='Migra os dados locais para uma conta do Neon')
    parser.add_argument('--email',required=True,help='E-mail da conta que receberá os dados')
    parser.add_argument('--allow-existing',action='store_true',help='Permite migrar para uma conta que já contém lançamentos')
    options=parser.parse_args()
    if not os.environ.get('DATABASE_URL'):raise SystemExit('Defina DATABASE_URL somente neste terminal antes de executar a migração.')
    if not storage.DATABASE.exists():raise SystemExit(f'Banco local não encontrado: {storage.DATABASE}')
    cloud_storage.initialize()
    with cloud_storage.connect() as db,db.cursor() as cursor:
        cursor.execute('SELECT id FROM users WHERE lower(email)=lower(%s)',(options.email,));user=cursor.fetchone()
    if not user:raise SystemExit('Conta não encontrada. Cadastre-se no aplicativo antes de migrar os dados.')
    uid=user['id'];existing=cloud_storage.read_expenses(uid)
    if existing and not options.allow_existing:raise SystemExit('Esta conta já possui lançamentos. Migração cancelada para evitar duplicidade.')
    expenses=storage.read_expenses()
    for item in expenses:
        payload={'date':item['date'],'amount':item['amount'],'where':item['where'],'category':item['category'],'payment':item['payment'],'description':item['description'],'allow_duplicate':True}
        cloud_storage.add_expense(payload,uid)
    incomes=storage.read_incomes()
    for month,values in incomes.items():cloud_storage.set_income({'month':month,**values},uid)
    income_entries=storage.read_income_entries()
    for item in income_entries:cloud_storage.add_income_entry({'date':item['date'],'amount':item['amount'],'where':item['source'],'category':item['category'],'description':item['description']},uid)
    for category in storage.read_categories():cloud_storage.add_category(category,uid)
    for month,categories in storage.read_budgets().items():
        for category,limit in categories.items():cloud_storage.set_budget({'month':month,'category':category,'limit':limit},uid)
    cloud_storage.save_investments(storage.load_investments(),uid)
    print(f"Migração concluída para {options.email}: {len(expenses)} gastos, {len(income_entries)} entradas, {len(incomes)} meses de renda e {len(storage.load_investments().get('investments',[]))} investimentos.")

if __name__=='__main__':main()
