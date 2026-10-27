"""Replay variable-income operations using a weighted average cost basis."""
from decimal import Decimal, ROUND_HALF_UP

CENT = Decimal('0.01')


def cents(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def initial_buy(item):
    return {'id': 'initial-' + item['id'], 'date': item['purchase_date'],
            'quantity': item['quantity'], 'unit_price': item['average_price'], 'fees': 0,
            'total': float(cents(Decimal(str(item['quantity'])) * Decimal(str(item['average_price'])))),
            'sequence': 0, 'initial': True}


def buys(item):
    return [entry for entry in item['buys'] if not entry.get('reversed')] if 'buys' in item else [initial_buy(item)]


def position(item, as_of=None, include_ledger=False):
    events = [(buy['date'], buy.get('sequence', i), 'buy', buy) for i, buy in enumerate(buys(item))]
    events += [(sale['date'], sale.get('sequence', i + 1), 'sale', sale) for i, sale in enumerate(item.get('sales', [])) if not sale.get('reversed')]
    quantity, basis, realized = Decimal(0), Decimal(0), Decimal(0)
    results = {}
    ledger = {}
    for day, _, kind, entry in sorted(events, key=lambda event: (event[0], event[1])):
        if as_of and day > as_of:
            continue
        before_quantity, before_basis = quantity, basis
        count = Decimal(str(entry['quantity']))
        if kind == 'buy':
            quantity += count
            basis += cents(entry['total'])
        else:
            if count > quantity or quantity <= 0:
                raise ValueError('A venda ultrapassa a quantidade disponível naquela data')
            cost = basis if count == quantity else cents(basis * count / quantity)
            net = cents(entry.get('net_total', cents(entry['total']) - cents(entry.get('fees', 0))))
            gain = net - cost
            realized += gain
            quantity -= count
            basis -= cost
            results[entry['id']] = {'profit_loss': float(gain), 'cost_basis': float(cost), 'net_total': float(net)}
        if include_ledger:
            ledger[entry['id']] = {'quantity_before':float(before_quantity),'quantity_after':float(quantity),
                'average_before':float(before_basis/before_quantity) if before_quantity else 0,
                'average_after':float(basis/quantity) if quantity else 0,
                'basis_before':float(before_basis),'basis_after':float(basis),
                'profit_loss':results.get(entry['id'],{}).get('profit_loss',0)}
    income = sum((cents(entry['amount']) for entry in item.get('incomes', []) if not entry.get('reversed') and (not as_of or entry['date'] <= as_of)), Decimal(0))
    return {'quantity': quantity, 'basis': basis, 'average': basis / quantity if quantity else Decimal(0),
            'realized': realized, 'income': income, 'sales': results, 'operations':ledger}


def sequence(item):
    return max([entry.get('sequence', i + 1) for i, entry in enumerate(buys(item) + item.get('sales', []))] or [0]) + 1


def sync(item):
    state = position(item)
    item['quantity'] = float(sum((Decimal(str(buy['quantity'])) for buy in item.get('buys', buys(item))), Decimal(0)))
    if buys(item):
        item['purchase_date'] = min(buy['date'] for buy in buys(item))
    if state['quantity'] and state['average'] > 0:
        item['average_price'] = float(state['average'].quantize(Decimal('0.00000001'), rounding=ROUND_HALF_UP))
    for sale in item.get('sales', []):
        if sale['id'] in state['sales']:
            sale.update(state['sales'][sale['id']])
    return state


def latest_date(item):
    return max([entry['date'] for entry in buys(item) + [sale for sale in item.get('sales', []) if not sale.get('reversed')]] or [item['purchase_date']])
