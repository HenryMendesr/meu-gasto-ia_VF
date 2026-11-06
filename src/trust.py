"""Explainable balances, correction previews, and user-owned preferences."""
import copy
import hashlib
import json
from datetime import datetime
from uuid import uuid4
from decimal import Decimal
from zoneinfo import ZoneInfo

try:
    from src import investments, portfolio_ops as ops, runtime_storage as storage
except ImportError:
    import investments
    import portfolio_ops as ops
    import runtime_storage as storage


def audit(store, kind, subject, before, after, reason):
    entry = {'id': uuid4().hex, 'date': investments.now_iso(), 'kind': kind, 'subject': subject,
             'before': copy.deepcopy(before), 'after': copy.deepcopy(after), 'reason': str(reason)[:200]}
    store['audit_log'] = (store.get('audit_log', []) + [entry])[-500:]
    return entry


def preferences(payload, user_id=None):
    if not isinstance(payload, dict):
        raise ValueError('Preferências inválidas')
    profile = None
    if 'investor_profile' in payload:
        try:
            from src import suitability
        except ImportError:
            import suitability
        profile = suitability.evaluate(payload['investor_profile'])
        profile['completed_at'] = investments.now_iso()
    allowed = {'onboarding_dismissed', 'analytics_consent', 'investor_profile_started', 'investment_education'}
    if any(key not in allowed or (key != 'investment_education' and not isinstance(value, bool)) for key, value in payload.items() if key != 'investor_profile'):
        raise ValueError('Preferências inválidas')
    payload = copy.deepcopy(payload)
    if 'investment_education' in payload:
        try:from src.investor_education import validate_education
        except ImportError:from investor_education import validate_education
        payload['investment_education'] = validate_education(payload['investment_education'])
    def save(store):
        current = store.setdefault('preferences', {})
        current.update({key: value for key, value in payload.items() if key != 'investor_profile'})
        if profile is not None:
            current['investor_profile'] = profile
        if payload.get('analytics_consent') is False:
            store.pop('usage_metrics', None)
        return current
    return investments.mutate_store(save, user_id)


def income_basis(month, incomes, entries, prefs=None):
    declared = incomes.get(month, {}).get('cash', 0)
    imported = round(sum(entry['amount'] for entry in entries if entry['date'].startswith(month)), 2)
    try:from src.recurring import salary_basis
    except ImportError:from recurring import salary_basis
    salary=salary_basis(month,prefs or {})
    mode = (prefs or {}).get('income_modes', {}).get(month, 'auto')
    if mode=='scheduled' or mode=='auto' and salary['active']:
        return {'declared':declared,'imported':imported,'mode':mode,'source':'scheduled','used':salary['confirmed'],'expected':salary['expected'],'pending':salary['pending']}
    source = 'declared' if mode == 'declared' or (mode == 'auto' and declared > 0) else 'imported'
    value=declared if source=='declared' else imported
    imported_confirmed=round(sum(entry['amount'] for entry in entries if entry['date'].startswith(month) and entry['date']<=investments.investment_today().isoformat()),2)
    confirmed=source=='imported' or (prefs or {}).get('income_confirmed',{}).get(month,False)
    return {'declared':declared,'imported':imported,'mode':mode,'source':source,'used':imported_confirmed if source=='imported' else value if confirmed else 0,
            'expected':value,'pending':round(value-imported_confirmed,2) if source=='imported' else 0 if confirmed else value}


def carried_cash(month, rows, incomes, entries, prefs):
    """Carry confirmed cash forward, using the same income source rules each month."""
    periods = set(incomes)
    periods.update(entry['date'][:7] for entry in entries)
    for row in rows:
        periods.add(row['date'][:7])
        if row.get('finance', {}).get('paid_date'):
            periods.add(row['finance']['paid_date'][:7])
    for receipt in prefs.get('salary_receipts', []):
        periods.add(receipt['month'])
        periods.add(receipt.get('received_date', receipt['date'])[:7])
    periods.update(entry['date'][:7] for entry in prefs.get('card_payments', []))
    received = spent = 0
    for period in sorted(periods):
        if period >= month:
            continue
        received += income_basis(period, incomes, entries, prefs)['used']
        spent += actual_cash(rows, prefs, period)
    return {'opening_balance': round(received - spent, 2),
            'previous_income': round(received, 2), 'previous_expenses': round(spent, 2)}


def insights(month, user_id=None):
    try:from src.recurring import process_due
    except ImportError:from recurring import process_due
    process_due(user_id)
    try:
        first = datetime.strptime(month, '%Y-%m').date()
    except (TypeError, ValueError) as exc:
        raise ValueError('Escolha um mês válido') from exc
    if first.year < 1900:
        raise ValueError('Escolha um mês válido')
    rows = storage.read_expenses(user_id)
    incomes = storage.read_incomes(user_id)
    imported = storage.read_income_entries(user_id)
    store = investments.load_store(user_id)
    basis = income_basis(month, incomes, imported, store.get('preferences'))
    try:from src import cards
    except ImportError:import cards
    rows=cards.planned_expenses(rows,store.get('preferences',{}))
    selected = [row for row in rows if row['date'].startswith(month)]
    cash = [row for row in selected if row['payment'] != 'Voucher']
    voucher = [row for row in selected if row['payment'] == 'Voucher']
    is_debt = lambda row: row.get('finance', {}).get('financing_kind') in {'loan', 'debt', 'asset'}
    pending = [row for row in cash if is_debt(row) and not row['finance'].get('paid')]
    today = investments.investment_today().isoformat()
    upcoming = [row for row in rows if is_debt(row) and not row['finance'].get('paid')]
    upcoming.sort(key=lambda row: row['date'])
    spent = round(sum(row['amount'] for row in cash), 2)
    reserved = round(sum(row['amount'] for row in pending), 2)
    card_payments=[entry for entry in store.get('preferences',{}).get('card_payments',[]) if not entry.get('reversed')]
    paid_due=sum(min(bill['paid'],bill['total']) for bill in cards.invoices(store.get('preferences',{})) if bill['month']==month)
    paid_month=sum(entry['amount'] for entry in card_payments if entry['date'].startswith(month))
    try:from src.finance_rules import projected_expenses
    except ImportError:from finance_rules import projected_expenses
    projected=round(projected_expenses(rows,month)-paid_due+paid_month,2)
    carry = carried_cash(month, rows, incomes, imported, store.get('preferences', {}))
    wallet = investments.portfolio(user_id)
    quotes = []
    for item in wallet['investments']:
        if item['type'] not in investments.VARIABLE_TYPES or item.get('remaining_quantity',0)<=0:
            continue
        stamp = item.get('quote_updated_at')
        age = None
        try:
            age = max(0, (datetime.now(ZoneInfo('UTC')) - datetime.fromisoformat(stamp.replace('Z', '+00:00'))).total_seconds()) if stamp else None
        except (ValueError, AttributeError):
            pass
        manual = not stamp or item.get('quote_source') in {None, 'Manual', 'Última compra'}
        quotes.append({'id': item['id'], 'symbol': item['symbol'], 'source': item.get('quote_source', 'Manual'),
                       'updated_at': stamp, 'manual': manual, 'stale': age is None or age > 24*3600,
                       'price': item['current_price'] if item.get('current_price') is not None else item['average_price']})
    return {**carry, 'accumulated_balance': round(carry['opening_balance'] + basis['used'] - actual_cash(rows,store.get('preferences',{}),month), 2),
            'accumulated_income': round(carry['previous_income'] + basis['used'], 2),
            'accumulated_expenses': round(carry['previous_expenses'] + actual_cash(rows,store.get('preferences',{}),month), 2),
            'projected_balance_with_carry': round(carry['opening_balance'] + basis['expected'] - projected, 2),
            'month': month, 'income': basis, 'cash_expenses': spent, 'pending_debts': reserved,
            'balance': round(basis['expected'] - projected, 2),'projected_expenses':projected,'confirmed_income':basis['used'],'expected_income':basis['expected'],
            'confirmed_balance':round(basis['used']-actual_cash(rows,store.get('preferences',{}),month),2),
            'actual_expenses':actual_cash(rows,store.get('preferences',{}),month),
            'voucher_income': incomes.get(month, {}).get('voucher', 0),
            'voucher_expenses': round(sum(row['amount'] for row in voucher), 2),
            'rows': [{'id': row['id'], 'date': row['date'], 'label': row['where'], 'amount': row['amount'],
                      'category': row['category'], 'payment': row['payment'],
                      'status': 'paid' if row.get('finance', {}).get('paid') else 'pending' if is_debt(row) else 'registered'} for row in selected],
            'upcoming': [{'id': row['id'], 'date': row['date'], 'label': row['where'], 'amount': row['amount'],
                          'overdue': row['date'] < today} for row in upcoming[:8]],
            'wallet': wallet['summary'], 'quotes': quotes,
            'audit': store.get('audit_log', [])[-50:], 'preferences': store.get('preferences', {})}


def operation_revision(item, cash):
    raw = json.dumps({'item': item, 'cash': cash}, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256(raw.encode()).hexdigest()


def ensure_funding_flags(item):
    item.setdefault('buys', [ops.initial_buy(item)])
    additional = sum((ops.cents(entry['total']) for entry in item['buys'] if not entry.get('initial') and not entry.get('reversed')), ops.cents(0))
    initial_funded = ops.cents(item.get('cash_funded_amount', 0)) - additional
    for entry in item['buys']:
        entry.setdefault('cash_debited', not entry.get('initial') or initial_funded >= ops.cents(entry['total']))
    for entry in item.get('incomes', []):
        entry.setdefault('cash_credited', True)


def cash_effect(item):
    value = ops.cents(0)
    for entry in item.get('buys', []):
        if not entry.get('reversed') and entry.get('cash_debited'):
            value -= ops.cents(entry['total'])
    for entry in item.get('sales', []):
        if not entry.get('reversed') and entry.get('cash_credited'):
            value += ops.cents(entry.get('net_total', entry['total']))
    for entry in item.get('incomes', []):
        if not entry.get('reversed') and entry.get('cash_credited'):
            value += ops.cents(entry['amount'])
    return value


def operation_change(item_id, operation_id, payload, user_id=None, preview=False):
    if not isinstance(payload, dict):
        raise ValueError('Dados da correção inválidos')
    reason = str(payload.get('reason', '')).strip()
    if not 3 <= len(reason) <= 200:
        raise ValueError('Informe o motivo da alteração (3 a 200 caracteres)')
    action = payload.get('action', 'edit')
    if action not in {'edit', 'reverse', 'restore'}:
        raise ValueError('Escolha corrigir, estornar ou restaurar')
    def change(store, persist):
        original = next((item for item in store['investments'] if item['id'] == item_id), None)
        if not original or original['type'] not in investments.VARIABLE_TYPES:
            raise KeyError('Ativo não encontrado')
        revision = operation_revision(original, store['cash_balance'])
        if persist and payload.get('revision') != revision:
            raise ValueError('Os dados mudaram. Veja a prévia novamente antes de confirmar')
        item = copy.deepcopy(original)
        ensure_funding_flags(item)
        collection, entry = next(((name, entry) for name in ('buys', 'sales', 'incomes') for entry in item.get(name, []) if entry['id'] == operation_id), (None, None))
        if not entry:
            raise KeyError('Operação não encontrada')
        before = copy.deepcopy(entry)
        old_effect = cash_effect(item)
        old_position = investments.calculated(item)
        if action == 'reverse':
            if entry.get('reversed'):
                raise ValueError('Esta operação já foi estornada')
            entry['reversed'] = True
        elif action == 'restore':
            if not entry.get('reversed'):
                raise ValueError('Esta operação não está estornada')
            entry['reversed'] = False
        else:
            if entry.get('reversed'):
                raise ValueError('Restaure a operação antes de corrigir os valores')
            day = investments.iso_date(payload.get('date'), 'Data da operação')
            if day > investments.investment_today().isoformat():
                raise ValueError('A data da operação não pode ser futura')
            entry['date'] = day
            if collection in {'buys', 'sales'}:
                quantity = investments.number(payload.get('quantity'), 'Quantidade', minimum=.00000001)
                price = investments.number(payload.get('unit_price'), 'Preço por unidade', minimum=.00000001)
                fees = ops.cents(investments.number(payload.get('fees') or 0, 'Taxas', minimum=0))
                gross = ops.cents(Decimal(str(quantity)) * Decimal(str(price)))
                if gross <= 0 or collection == 'sales' and fees >= gross:
                    raise ValueError('Revise o valor total e as taxas')
                entry.update(quantity=quantity, unit_price=price, fees=float(fees), total=float(gross + fees if collection == 'buys' else gross))
                if collection == 'sales':
                    entry['net_total'] = float(gross - fees)
            else:
                amount = investments.number(payload.get('amount'), 'Valor líquido', minimum=.01)
                kind = str(payload.get('kind', entry['kind']))
                if kind not in {'Dividendos', 'JCP', 'Rendimento de FII', 'Outros proventos'}:
                    raise ValueError('Escolha o tipo de provento')
                entry.update(amount=float(ops.cents(amount)), kind=kind)
        active_buys = ops.buys(item)
        active_incomes = [income for income in item.get('incomes', []) if not income.get('reversed')]
        if active_incomes and (not active_buys or min(income['date'] for income in active_incomes) < min(buy['date'] for buy in active_buys)):
            raise ValueError('O provento ficaria sem uma compra anterior. Corrija ou estorne o recebimento primeiro')
        state = ops.sync(item)
        new_position = investments.calculated(item)
        difference = cash_effect(item) - old_effect
        cash_after = ops.cents(store['cash_balance']) + difference
        if cash_after < 0:
            raise ValueError('O caixa ficaria negativo. Ajuste o saldo antes de confirmar a correção ou estorno')
        item['cash_funded_amount'] = float(sum((ops.cents(buy['total']) for buy in active_buys if buy.get('cash_debited')), ops.cents(0)))
        item['operation_corrected'] = True
        item['updated_at'] = investments.now_iso()
        result = {'revision': revision, 'action': action, 'reason': reason, 'collection': collection,
                  'operation_before': before, 'operation_after': copy.deepcopy(entry),
                  'cash_before': store['cash_balance'], 'cash_after': float(cash_after), 'cash_difference': float(difference),
                  'quantity_before': old_position['remaining_quantity'], 'quantity_after': new_position['remaining_quantity'],
                  'average_before': old_position['average_price'], 'average_after': new_position['average_price'],
                  'result_before': old_position['total_profit_loss'], 'result_after': new_position['total_profit_loss']}
        if persist:
            investments.adjust_cash(store, -difference)
            store['investments'][store['investments'].index(original)] = item
            store['updated_at'] = investments.now_iso()
            audit(store, 'operation_' + action, item.get('symbol', item_id),
                  {'operation': before, 'cash': result['cash_before'], 'result': result['result_before']},
                  {'operation': entry, 'cash': result['cash_after'], 'result': result['result_after']}, reason)
            investments.record_snapshot(store)
        return result
    return change(investments.load_store(user_id), False) if preview else investments.mutate_store(lambda store: change(store, True), user_id)


def reconcile_cash(payload, user_id=None):
    amount = float(ops.cents(investments.number(payload.get('amount'), 'Saldo conferido', minimum=0)))
    reason = str(payload.get('reason', '')).strip()
    if len(reason) < 3 or len(reason) > 200:
        raise ValueError('Descreva a origem da diferença')
    def apply(store):
        before = store['cash_balance']
        store['cash_balance'] = amount
        store['cash_updated_at'] = investments.now_iso()
        audit(store, 'cash_reconciliation', 'Caixa de investimentos', {'cash': before}, {'cash': amount}, reason)
        return {'before': before, 'after': amount, 'difference': round(amount-before, 2)}
    return investments.mutate_store(apply, user_id)


def feedback(payload, user_id=None):
    text = str(payload.get('message', '')).strip()
    rating = int(payload.get('rating', 0))
    if not 5 <= len(text) <= 1000 or rating not in range(1,6):
        raise ValueError('Escolha uma nota e escreva de 5 a 1000 caracteres')
    def save(store):
        entry = {'id': uuid4().hex, 'date': investments.now_iso(), 'rating': rating, 'message': text}
        store['feedback'] = (store.get('feedback', []) + [entry])[-30:]
        return {'id': entry['id']}
    return investments.mutate_store(save, user_id)


def usage_event(payload, user_id=None):
    name = str(payload.get('name', ''))
    if name not in {'onboarding_completed','expense_created','report_opened','goal_created','wallet_operation','feedback_sent'}:
        raise ValueError('Evento inválido')
    def save(store):
        if not store.get('preferences', {}).get('analytics_consent'):
            return {'recorded': False}
        day = investments.investment_today().isoformat()
        metrics = store.setdefault('usage_metrics', {})
        bucket = metrics.setdefault(day, {})
        bucket[name] = min(100, bucket.get(name, 0)+1)
        for old in sorted(metrics)[:-90]:metrics.pop(old, None)
        return {'recorded': True}
    return investments.mutate_store(save, user_id)


def actual_cash(rows,prefs,month):
    try:from src import cards
    except ImportError:import cards
    today=investments.investment_today().isoformat();total=0
    for row in rows:
        finance=row.get('finance',{})
        if finance.get('card_purchase_id') or row['payment']=='Voucher':continue
        debt=finance.get('financing_kind') in {'loan','debt','asset'} or bool(finance.get('fixed_expense_id'))
        effective=finance.get('paid_date',row['date']) if debt else row['date']
        if effective.startswith(month) and effective<=today and (not debt or finance.get('paid')):total+=row['amount']
    return round(total+sum(entry['amount'] for entry in cards.payment_expenses(prefs) if entry['date'].startswith(month)),2)
