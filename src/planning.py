"""Goals and monthly summaries built from the user's existing records."""
from calendar import monthrange
from datetime import date
from uuid import uuid4
import re

try:
    from src import investments, runtime_storage as storage, portfolio_ops as ops
except ImportError:
    import investments
    import runtime_storage as storage
    import portfolio_ops as ops


GOAL_MODES={'manual','portfolio_value','portfolio_cost'}


def goal_progress(goal, items):
    mode=goal.get('tracking_mode','manual')
    field={'portfolio_value':'current_value','portfolio_cost':'amount_applied'}.get(mode)
    current=round(sum(item[field] for item in items),2) if field else goal.get('current_amount',0)
    return {**goal,'tracking_mode':mode,'current_amount':current}


def save_goal(payload, user_id=None):
    if not isinstance(payload, dict):
        raise ValueError('Dados da meta inválidos')
    name = str(payload.get('name', '')).strip()
    if not 2 <= len(name) <= 80:
        raise ValueError('Informe um nome de 2 a 80 caracteres')
    target = float(ops.cents(investments.number(payload.get('target_amount'), 'Valor da meta', minimum=.01)))
    mode=str(payload.get('tracking_mode','manual'))
    if mode not in GOAL_MODES:raise ValueError('Escolha acompanhamento manual, valor atual investido ou valor aplicado')
    current = float(ops.cents(investments.number(payload.get('current_amount', 0), 'Valor já reservado', minimum=0))) if mode=='manual' else 0
    deadline = investments.iso_date(payload.get('target_date'), 'Prazo da meta')
    goal_id = str(payload.get('id') or '')
    def save(store):
        goals = store.setdefault('goals', [])
        existing = next((goal for goal in goals if goal['id'] == goal_id), None)
        if goal_id and not existing:
            raise KeyError('Meta não encontrada')
        goal = {'id': goal_id or uuid4().hex, 'name': name, 'target_amount': target,
                'current_amount': current, 'tracking_mode':mode,'target_date': deadline, 'updated_at': investments.now_iso()}
        if existing:
            goals[goals.index(existing)] = goal
        else:
            goals.append(goal)
        return goal_progress(goal,[investments.calculated(item) for item in store['investments']])
    return investments.mutate_store(save, user_id)


def delete_goal(goal_id, user_id=None):
    def remove(store):
        goals = store.get('goals', [])
        if not any(goal['id'] == goal_id for goal in goals):
            raise KeyError('Meta não encontrada')
        store['goals'] = [goal for goal in goals if goal['id'] != goal_id]
    investments.mutate_store(remove, user_id)


def monthly_report(month, user_id=None):
    try:from src.recurring import process_due
    except ImportError:from recurring import process_due
    process_due(user_id)
    if not re.fullmatch(r'\d{4}-\d{2}', str(month)):
        raise ValueError('Escolha um mês válido')
    try:
        first = date.fromisoformat(month + '-01')
        if first.year < 1900:
            raise ValueError()
    except ValueError as exc:
        raise ValueError('Escolha um mês válido') from exc
    last = date(first.year, first.month, monthrange(first.year, first.month)[1]).isoformat()
    expenses = storage.read_expenses(user_id)
    incomes = storage.read_incomes(user_id)
    imported = storage.read_income_entries(user_id)
    store = investments.load_store(user_id)
    try:from src import cards
    except ImportError:import cards
    prefs=store.get('preferences',{})
    expenses=cards.planned_expenses(expenses,prefs)
    expenses=[entry for entry in expenses if not entry.get('finance',{}).get('card_purchase_id')]+cards.payment_expenses(prefs)
    operations = []
    for item in store['investments']:
        label = item.get('symbol') or item.get('name')
        if item['type'] in investments.VARIABLE_TYPES:
            for buy in ops.buys(item):
                operations.append({'date': buy['date'], 'kind': 'Aporte', 'label': label,
                                   'amount': -buy['total'], 'realized': 0, 'fees': buy.get('fees', 0)})
            for sale in item.get('sales', []):
                if sale.get('reversed'):continue
                operations.append({'date': sale['date'], 'kind': 'Venda', 'label': label,
                                   'amount': sale.get('net_total', sale['total']), 'realized': sale['profit_loss'], 'fees': sale.get('fees', 0)})
            for income in item.get('incomes', []):
                if income.get('reversed'):continue
                operations.append({'date': income['date'], 'kind': 'Provento', 'label': label,
                                   'amount': income['amount'], 'realized': income['amount'], 'fees': 0})
        else:
            operations.append({'date': item['application_date'], 'kind': 'Aporte', 'label': label,
                               'amount': -item['amount_invested'], 'realized': 0, 'fees': 0})
    for item in store['investments']:
        for entry in item.get('redemptions', []):
            if not entry.get('reversed'):
                operations.append({'date':entry['date'],'kind':'Venda','label':item['name']+' · Resgate','amount':entry['net'],'realized':entry['net']-entry['principal'],'fees':entry['tax']})
    def is_debt(entry):
        return entry.get('finance', {}).get('financing_kind') in {'loan','debt','asset'}
    def requires_confirmation(entry):
        return is_debt(entry) or bool(entry.get('finance',{}).get('fixed_expense_id'))
    def effective_date(entry):
        return entry['finance'].get('paid_date', entry['date']) if requires_confirmation(entry) else entry['date']
    def actual_entries(period):
        return [entry for entry in expenses if effective_date(entry).startswith(period)
                and effective_date(entry)<=investments.investment_today().isoformat()
                and (not requires_confirmation(entry) or entry.get('finance', {}).get('paid') is True)]
    def income_for(period):
        try:from src.trust import income_basis
        except ImportError:from trust import income_basis
        basis=income_basis(period,incomes,imported,store.get('preferences'))
        return basis['used'],basis['imported'],basis['source']
    actual = actual_entries(month)
    cash_expenses = round(sum(entry['amount'] for entry in actual if entry['payment'] != 'Voucher'), 2)
    voucher = round(sum(entry['amount'] for entry in actual if entry['payment'] == 'Voucher'), 2)
    income, imported_total, source = income_for(month)
    selected = [entry for entry in operations if entry['date'].startswith(month)]
    categories = {}
    for entry in actual:
        categories[entry['category']] = round(categories.get(entry['category'], 0) + entry['amount'], 2)
    flow = []
    for offset in range(5, -1, -1):
        index = first.year * 12 + first.month - 1 - offset
        period = f'{index//12:04d}-{index%12+1:02d}'
        flow.append({'month': period, 'income': income_for(period)[0],
                     'expenses': round(sum(entry['amount'] for entry in actual_entries(period) if entry['payment'] != 'Voucher'), 2),
                     'invested': round(-sum(entry['amount'] for entry in operations if entry['kind'] == 'Aporte' and entry['date'].startswith(period)), 2)})
    wealth = [point for point in store.get('wealth_history', []) if flow[0]['month'] <= point['date'][:7] <= month]
    transactions = [{'date': effective_date(entry), 'kind': 'Fatura paga' if entry.get('finance',{}).get('card_payment') else 'Gasto fixo pago' if entry.get('finance',{}).get('fixed_expense_id') else 'Parcela paga' if is_debt(entry) else 'Gasto',
                     'label': entry['where'], 'amount': -entry['amount'], 'account': 'Voucher' if entry['payment'] == 'Voucher' else 'Dia a dia'} for entry in actual]
    transactions += [{'date': entry['date'], 'kind': 'Entrada importada', 'label': entry['source'],
                      'amount': entry['amount'], 'account': 'Dia a dia'} for entry in imported if entry['date'].startswith(month) and entry['date']<=investments.investment_today().isoformat() and source=='imported']
    transactions += [{**entry, 'account': 'Investimentos'} for entry in selected]
    try:from src.trust import income_basis
    except ImportError:from trust import income_basis
    basis=income_basis(month,incomes,imported,prefs)
    transactions += [{'date':entry.get('received_date',entry['date']),'kind':'Salário confirmado','label':entry['source'],'amount':entry['amount'],'account':'Dia a dia'} for entry in prefs.get('salary_receipts',[]) if entry.get('received_date',entry['date'])[:7]==month and entry.get('status')=='confirmed' and source=='scheduled']
    if source=='declared' and income:
        transactions.append({'date':month+'-01','kind':'Renda informada confirmada','label':incomes.get(month,{}).get('source') or 'Renda','amount':income,'account':'Dia a dia'})
    return {'expected_income':basis['expected'],'pending_income':basis['pending'],'month': month, 'income': income, 'income_source': source, 'imported_income': imported_total,
            'cash_expenses': cash_expenses, 'voucher_expenses': voucher, 'available': round(income - cash_expenses, 2),
            'invested': round(-sum(entry['amount'] for entry in selected if entry['kind'] == 'Aporte'), 2),
            'sales': round(sum(entry['amount'] for entry in selected if entry['kind'] == 'Venda'), 2),
            'investment_income': round(sum(entry['amount'] for entry in selected if entry['kind'] == 'Provento'), 2),
            'realized_result': round(sum(entry['realized'] for entry in selected), 2),
            'debt_due': round(sum(entry['amount'] for entry in expenses if is_debt(entry) and entry['date'].startswith(month)), 2),
            'debt_open': round(sum(entry['amount'] for entry in expenses if is_debt(entry) and not entry.get('finance', {}).get('paid')), 2),
            'debt_paid': round(sum(entry['amount'] for entry in actual if is_debt(entry)), 2),
            'categories': categories, 'flow': flow, 'wealth_history': wealth,
            'transactions': sorted(transactions, key=lambda entry: entry['date'], reverse=True)}
