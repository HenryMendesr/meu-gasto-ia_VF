"""Daily activity and performance; cash flows are never counted as profit."""
from datetime import date, timedelta
from decimal import Decimal

try:
    from src import portfolio_ops as ops
except ImportError:
    import portfolio_ops as ops


def summaries(store, expenses, today):
    try:from src import investments
    except ImportError:import investments
    try:from src import cards
    except ImportError:import cards
    prefs=store.get('preferences',{})
    expenses=[entry for entry in cards.planned_expenses(expenses,prefs) if not entry.get('finance',{}).get('card_purchase_id')]+cards.payment_expenses(prefs)
    operations=[]
    for item in store['investments']:
        common={'asset_id':item.get('id',item.get('name','')),'label':item.get('symbol') or item.get('name'),'type':item['type']}
        if item['type'] in investments.VARIABLE_TYPES:
            state=ops.position(item)
            for kind,entries in [('Compra',ops.buys(item)),('Venda',item.get('sales',[])),('Provento',item.get('incomes',[]))]:
                for entry in entries:
                    if entry.get('reversed') or entry['date']>today:continue
                    total=entry.get('amount',entry.get('total',0))
                    operations.append({**common,'id':entry['id'],'date':entry['date'],'kind':kind,
                        'amount':total,'net':entry.get('net_total',total),'fees':entry.get('fees',0),
                        'quantity':entry.get('quantity'),'realized':state['sales'].get(entry['id'],{}).get('profit_loss',0)})
        elif item['application_date']<=today:
            operations.append({**common,'id':common['asset_id'],'date':item['application_date'],'kind':'Aplicação',
                               'amount':item['amount_invested'],'net':item['amount_invested'],'fees':0,'realized':0})
    for item in store['investments']:
        for entry in item.get('redemptions',[]):
            if not entry.get('reversed'):
                operations.append({'asset_id':item['id'],'label':item['name'],'type':item['type'],'id':entry['id'],'date':entry['date'],'kind':'Venda','amount':entry['gross'],'net':entry['net'],'fees':entry['tax'],'realized':entry['net']-entry['principal']})
    latest=max([entry['date'] for entry in operations] or [today])

    def build(day):
        selected=[entry for entry in operations if entry['date']==day]
        buys=sum(entry['amount'] for entry in selected if entry['kind'] in {'Compra','Aplicação'})
        sales=sum(entry['net'] for entry in selected if entry['kind']=='Venda')
        income=sum(entry['amount'] for entry in selected if entry['kind']=='Provento')
        realized=sum(entry['realized'] for entry in selected)
        fees=sum(entry['fees'] for entry in selected)
        prior=(date.fromisoformat(day)-timedelta(days=1)).isoformat()
        assets=[];known=0;missing=0
        for item in store['investments']:
            label=item.get('symbol') or item.get('name')
            moves=[entry for entry in selected if entry['asset_id']==item.get('id',item.get('name',''))]
            change=None;estimated=False
            if item['type'] in investments.VARIABLE_TYPES:
                opening=ops.position(item,prior);closing=ops.position(item,day)
                if not opening['quantity'] and not closing['quantity'] and not moves:continue
                previous=item.get('previous_close');price=item.get('current_price')
                if not investments.foreign_quote_unconverted(item) and item.get('quote_date')==day and item.get('quote_source') not in {None,'Manual','Última compra'} and previous is not None and price is not None:
                    change=float(closing['quantity']*Decimal(str(price))-opening['quantity']*Decimal(str(previous)))
                    change+=sum(entry['net'] if entry['kind'] in {'Venda','Provento'} else -entry['amount'] for entry in moves)
                elif not opening['quantity'] and not closing['quantity']:
                    change=sum(entry['realized']+ (entry['amount'] if entry['kind']=='Provento' else 0) for entry in moves)
            else:
                if item['application_date']>day:continue
                estimated=True
                if investments.fixed_mode(item)=='automatic' and investments.fixed_annual_rate(item) is not None:
                    start=investments.fixed_income_value(item,date.fromisoformat(prior))
                    change=investments.fixed_income_value(item,date.fromisoformat(day))-start
                    change+=sum(entry['net'] for entry in moves if entry['kind']=='Venda')
            if change is None:missing+=1
            else:known+=change
            assets.append({'id':item.get('id',item.get('name','')),'label':label,'change':round(change,2) if change is not None else None,
                           'estimated':estimated,'source':item.get('quote_source') or item.get('institution'),
                           'quote_date':item.get('quote_date'),'invested':round(sum(e['amount'] for e in moves if e['kind'] in {'Compra','Aplicação'}),2)})
        personal=[]
        for row in expenses:
            finance=row.get('finance',{})
            debt=finance.get('financing_kind') in {'loan','debt','asset'}
            if debt and not finance.get('paid'):continue
            effective=finance.get('paid_date',row['date']) if debt else row['date']
            if effective==day:personal.append({'label':row['where'],'amount':row['amount'],'payment':row['payment']})
        return {'date':day,'operations':sorted(selected,key=lambda entry:(entry['label'],entry['kind'])),
                'invested':round(buys,2),'sales':round(sales,2),'income':round(income,2),
                'realized_profit':round(realized,2),'realized_with_income':round(realized+income,2),'fees':round(fees,2),
                'cash_flow':round(sales+income-buys,2),'assets':assets,'missing_quotes':missing,
                'performance':round(known,2) if assets and not missing else None,'known_performance':round(known,2),
                'personal_expenses':round(sum(row['amount'] for row in personal),2),'expense_rows':personal}
    return {'latest':build(latest),'today':build(today)}
