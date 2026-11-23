"""Salary installments and card due-date reminders, scoped to the portfolio owner."""
from calendar import monthrange
from datetime import date
from uuid import uuid4

try:
    from src import investments, portfolio_ops as ops
except ImportError:
    import investments
    import portfolio_ops as ops


def month_start(value):
    try:
        first=date.fromisoformat(str(value)+'-01')
        if first.year<1900:raise ValueError()
        return first
    except (TypeError,ValueError) as exc:raise ValueError('Escolha um mês de início válido') from exc


def due_date(month,day):
    first=month_start(month)
    return date(first.year,first.month,min(day,monthrange(first.year,first.month)[1])).isoformat()


def validate_plan(payload):
    if not isinstance(payload,dict) or not isinstance(payload.get('enabled'),bool):raise ValueError('Configuração de salário inválida')
    if not payload['enabled']:return {'enabled':False}
    start=month_start(payload.get('start_month')).strftime('%Y-%m')
    source=str(payload.get('source','Salário')).strip()
    slots=payload.get('payments')
    if not source or len(source)>100 or not isinstance(slots,list) or not 1<=len(slots)<=2:raise ValueError('Informe a origem e uma ou duas datas de recebimento')
    payments=[]
    for index,slot in enumerate(slots):
        try:
            day=int(slot['day'])
            if str(day)!=str(slot['day']) or not 1<=day<=31:raise ValueError()
            amount=float(ops.cents(investments.number(slot.get('amount'),'Valor do recebimento',minimum=.01)))
            if amount>10000000:raise ValueError()
        except (TypeError,KeyError,ValueError) as exc:raise ValueError('Informe dia de 1 a 31 e valor positivo para cada recebimento') from exc
        payments.append({'slot':str(index+1),'day':day,'amount':amount})
    if len({payment['day'] for payment in payments})!=len(payments):raise ValueError('Escolha dias diferentes para os recebimentos')
    return {'enabled':True,'start_month':start,'source':source,'payments':payments}


def pending_receipts(prefs,today):
    plan=prefs.get('salary_plan',{})
    if not plan.get('enabled'):return []
    first=month_start(plan['start_month']);last=month_start(today[:7])
    existing={entry['key'] for entry in prefs.get('salary_receipts',[])}
    result=[];current=first
    while current<=last:
        month=current.strftime('%Y-%m')
        for payment in plan['payments']:
            day=due_date(month,payment['day']);key=month+':'+payment['slot']
            if day<=today and key not in existing:
                result.append({'key':key,'date':day,'month':month,'slot':payment['slot'],
                    'amount':payment['amount'],'source':plan['source'],'status':'confirmed',
                    'received_date':day,'automatic':True})
        current=date(current.year+(current.month==12),current.month%12+1,1)
    return result


def process_due(user_id=None):
    today=investments.investment_today().isoformat()
    prefs=investments.load_store(user_id).get('preferences',{})
    if not pending_receipts(prefs,today) and not any(e.get('status')=='scheduled' and not e.get('manual_pending') and e['date']<=today for e in prefs.get('salary_receipts',[])):return {'posted':0}
    def apply(store):
        current=store.setdefault('preferences',{});pending=pending_receipts(current,today)
        for entry in pending:entry['posted_at']=investments.now_iso()
        current.setdefault('salary_receipts',[]).extend(pending)
        for entry in current['salary_receipts']:
            if entry.get('status')=='scheduled' and not entry.get('manual_pending') and entry['date']<=today:
                entry.update(status='confirmed',received_date=entry['date'],automatic=True)
        return {'posted':len(pending)}
    return investments.mutate_store(apply,user_id)


def save_plan(payload,user_id=None):
    plan=validate_plan(payload)
    today=investments.investment_today().isoformat()
    def apply(store):
        prefs=store.setdefault('preferences',{});old=prefs.get('salary_plan',{})
        # Settle due installments using the prior plan before applying new dates/amounts.
        pending=pending_receipts(prefs,today)
        for entry in pending:entry['posted_at']=investments.now_iso()
        prefs.setdefault('salary_receipts',[]).extend(pending)
        if not plan['enabled']:new={**old,'enabled':False}
        else:new=plan
        prefs['salary_plan']=new
        if new.get('enabled'):
            for month in {new['start_month'],today[:7]}:
                if month>=new['start_month']:prefs.setdefault('income_modes',{})[month]='scheduled'
        pending_new=pending_receipts(prefs,today)
        for entry in pending_new:entry['posted_at']=investments.now_iso()
        prefs['salary_receipts'].extend(pending_new)
        investments.audit_change(store,'salary_plan','Salário recorrente',old,new,'Configuração dos recebimentos mensais')
        return {'plan':new,'posted':len(pending)+len(pending_new)}
    return investments.mutate_store(apply,user_id)


def receipt_action(key,payload,user_id=None):
    action=payload.get('action')
    if action not in {'confirm','skip','restore','delay'}:raise ValueError('Escolha confirmar, desconsiderar ou restaurar')
    def apply(store):
        prefs=store.setdefault('preferences',{})
        entry=next((entry for entry in prefs.get('salary_receipts',[]) if entry['key']==key),None)
        if not entry:raise KeyError('Recebimento não encontrado')
        before=dict(entry)
        if action=='confirm':
            if entry.get('status')=='skipped':raise ValueError('Restaure o recebimento antes de confirmar')
            entry['amount']=float(ops.cents(investments.number(payload.get('amount'),'Valor recebido',minimum=.01)))
            if entry['amount']>10000000:raise ValueError('Revise o valor recebido')
            received_date=investments.iso_date(payload.get('received_date') or investments.investment_today().isoformat(),'Data do recebimento')
            if received_date>investments.investment_today().isoformat():raise ValueError('Confirme apenas recebimentos já ocorridos')
            entry['received_date']=received_date
            entry['status']='confirmed'
            entry['automatic']=False
            entry.pop('manual_pending',None)
        elif action=='delay':
            entry['status']='scheduled'
            entry['manual_pending']=True
            entry.pop('received_date',None)
            entry['automatic']=False
        elif action=='restore':
            entry.update(status='confirmed',received_date=entry['date'],automatic=True)
            entry.pop('manual_pending',None)
        else:entry['status']='skipped'
        investments.audit_change(store,'salary_receipt',entry['source'],before,entry,'Ajuste do recebimento de '+entry['date'])
        return entry
    return investments.mutate_store(apply,user_id)


def salary_basis(month,prefs):
    receipts=[entry for entry in prefs.get('salary_receipts',[]) if entry['month']==month]
    plan=prefs.get('salary_plan',{})
    active=bool(receipts) or bool(plan.get('enabled') and month>=plan['start_month'])
    confirmed_entries=[entry for entry in prefs.get('salary_receipts',[]) if entry.get('status')=='confirmed' and entry.get('received_date',entry['date'])[:7]==month]
    confirmed=round(sum(entry['amount'] for entry in confirmed_entries),2)
    expected=round(confirmed+sum(entry['amount'] for entry in receipts if entry.get('status') not in {'skipped','confirmed'}),2)
    keys={entry['key'] for entry in receipts}
    if plan.get('enabled') and month>=plan['start_month']:
        expected=round(expected+sum(payment['amount'] for payment in plan['payments'] if month+':'+payment['slot'] not in keys),2)
    return {'active':active or bool(confirmed_entries),'received':confirmed,'confirmed':confirmed,'expected':expected,'pending':round(expected-confirmed,2)}


def validate_card(payload):
    if not isinstance(payload,dict):raise ValueError('Dados do cartão inválidos')
    name=str(payload.get('name','')).strip()
    try:
        day=int(payload.get('due_day'))
        if str(day)!=str(payload.get('due_day')) or not 1<=day<=31:raise ValueError()
    except (TypeError,ValueError) as exc:raise ValueError('Informe um dia de vencimento de 1 a 31') from exc
    if not 1<=len(name)<=80:raise ValueError('Informe o nome do cartão (até 80 caracteres)')
    closing=payload.get('closing_day')
    if closing not in (None,''):
        try:
            closing_number=int(closing)
            if str(closing_number)!=str(closing) or not 1<=closing_number<=31:raise ValueError()
        except (ValueError,TypeError) as exc:raise ValueError('Informe o fechamento de 1 a 31') from exc
    else:closing_number=None
    limit=payload.get('limit')
    if limit not in (None,''):
        limit=investments.number(limit,'Limite do cartão',minimum=0)
        if limit>10000000:raise ValueError('Revise o limite do cartão')
    else:limit=None
    goals={}
    for field,label in (('spending_goal','Meta de gasto do cartão'),('installment_cap','Máximo em parcelas por mês')):
        value=payload.get(field)
        if value in (None,''):goals[field]=None;continue
        value=investments.number(value,label,minimum=0)
        if value>10000000:raise ValueError('Revise o valor de '+label.lower())
        goals[field]=round(value,2)
    return {'name':name,'due_day':day,'closing_day':closing_number,'limit':limit,**goals}


def save_card(payload,user_id=None):
    card=validate_card(payload);item_id=str(payload.get('id') or '')
    def apply(store):
        cards=store.setdefault('preferences',{}).setdefault('credit_cards',[])
        existing=next((entry for entry in cards if entry['id']==item_id),None)
        if item_id and not existing:raise KeyError('Cartão não encontrado')
        saved={**card,'id':item_id or uuid4().hex}
        if existing:cards[cards.index(existing)]=saved
        else:
            if len(cards)>=100:raise ValueError('Limite de 100 cartões por conta')
            cards.append(saved)
        return saved
    return investments.mutate_store(apply,user_id)


def delete_card(item_id,user_id=None):
    def apply(store):
        prefs=store.setdefault('preferences',{});cards=prefs.get('credit_cards',[])
        if not any(entry['id']==item_id for entry in cards):raise KeyError('Cartão não encontrado')
        if any(entry['card_id']==item_id for entry in prefs.get('card_purchases',[])):raise ValueError('Este cartão tem compras no histórico. Preserve o cadastro ou remova as compras sem pagamento primeiro')
        prefs['credit_cards']=[entry for entry in cards if entry['id']!=item_id]
        return {'deleted':True}
    return investments.mutate_store(apply,user_id)


def card_dates(cards,today):
    result=[]
    for card in cards:
        due=due_date(today[:7],card['due_day'])
        if due<today:
            current=month_start(today[:7]);next_month=date(current.year+(current.month==12),current.month%12+1,1).strftime('%Y-%m')
            due=due_date(next_month,card['due_day'])
        result.append({**card,'next_due':due,'days_until':(date.fromisoformat(due)-date.fromisoformat(today)).days})
    return sorted(result,key=lambda entry:entry['next_due'])


def status(month,user_id=None):
    month_start(month);process_due(user_id)
    prefs=investments.load_store(user_id).get('preferences',{})
    return {'preferences':prefs,'cards':card_dates(prefs.get('credit_cards',[]),investments.investment_today().isoformat()),
            'receipts':[entry for entry in prefs.get('salary_receipts',[]) if entry['month']==month]}
