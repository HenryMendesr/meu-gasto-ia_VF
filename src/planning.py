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


def save_goal(payload, user_id=None):
    if not isinstance(payload, dict):
        raise ValueError('Dados da meta inválidos')
    name = str(payload.get('name', '')).strip()
    if not 2 <= len(name) <= 80:
        raise ValueError('Informe um nome de 2 a 80 caracteres')
    target = float(ops.cents(investments.number(payload.get('target_amount'), 'Valor da meta', minimum=.01)))
    current = float(ops.cents(investments.number(payload.get('current_amount', 0), 'Valor já reservado', minimum=0)))
    deadline = investments.iso_date(payload.get('target_date'), 'Prazo da meta')
    goal_id = str(payload.get('id') or '')
    def save(store):
        goals = store.setdefault('goals', [])
        existing = next((goal for goal in goals if goal['id'] == goal_id), None)
        if goal_id and not existing:
            raise KeyError('Meta não encontrada')
        goal = {'id': goal_id or uuid4().hex, 'name': name, 'target_amount': target,
                'current_amount': current, 'target_date': deadline, 'updated_at': investments.now_iso()}
        if existing:
            goals[goals.index(existing)] = goal
        else:
            goals.append(goal)
        return goal
    return investments.mutate_store(save, user_id)


def delete_goal(goal_id, user_id=None):
    def remove(store):
        goals = store.get('goals', [])
        if not any(goal['id'] == goal_id for goal in goals):
            raise KeyError('Meta não encontrada')
        store['goals'] = [goal for goal in goals if goal['id'] != goal_id]
    investments.mutate_store(remove, user_id)


def monthly_report(month, user_id=None):
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
    operations = []
    for item in store['investments']:
        label = item.get('symbol') or item.get('name')
        if item['type'] in investments.VARIABLE_TYPES:
            for buy in ops.buys(item):
                operations.append({'date': buy['date'], 'kind': 'Aporte', 'label': label,
                                   'amount': -buy['total'], 'realized': 0, 'fees': buy.get('fees', 0)})
            for sale in item.get('sales', []):
                operations.append({'date': sale['date'], 'kind': 'Venda', 'label': label,
                                   'amount': sale.get('net_total', sale['total']), 'realized': sale['profit_loss'], 'fees': sale.get('fees', 0)})
            for income in item.get('incomes', []):
                operations.append({'date': income['date'], 'kind': 'Provento', 'label': label,
                                   'amount': income['amount'], 'realized': income['amount'], 'fees': 0})
        else:
            operations.append({'date': item['application_date'], 'kind': 'Aporte', 'label': label,
                               'amount': -item['amount_invested'], 'realized': 0, 'fees': 0})
    def is_debt(entry):
        return entry.get('finance', {}).get('financing_kind') in {'loan', 'debt', 'asset'}
    def effective_date(entry):
        return entry['finance'].get('paid_date', entry['date']) if is_debt(entry) else entry['date']
    def actual_entries(period):
        return [entry for entry in expenses if effective_date(entry).startswith(period)
                and (not is_debt(entry) or entry.get('finance', {}).get('paid') is True)]
    def income_for(period):
        declared = incomes.get(period, {}).get('cash', 0)
        total_imported = round(sum(entry['amount'] for entry in imported if entry['date'].startswith(period)), 2)
        return (declared if declared > 0 else total_imported), total_imported, 'declared' if declared > 0 else 'imported'
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
    transactions = [{'date': effective_date(entry), 'kind': 'Parcela paga' if is_debt(entry) else 'Gasto',
                     'label': entry['where'], 'amount': -entry['amount'], 'account': 'Voucher' if entry['payment'] == 'Voucher' else 'Dia a dia'} for entry in actual]
    transactions += [{'date': entry['date'], 'kind': 'Entrada importada', 'label': entry['source'],
                      'amount': entry['amount'], 'account': 'Dia a dia'} for entry in imported if entry['date'].startswith(month)]
    transactions += [{**entry, 'account': 'Investimentos'} for entry in selected]
    return {'month': month, 'income': income, 'income_source': source, 'imported_income': imported_total,
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
