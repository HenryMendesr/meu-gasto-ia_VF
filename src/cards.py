"""Card billing cycles. Purchases are commitments; invoice payments are cash outflows."""
from datetime import date
from decimal import Decimal, ROUND_DOWN
from uuid import uuid4
import hashlib
import json
from collections import Counter

try:
    from src import investments, portfolio_ops as ops, recurring, runtime_storage as storage
except ImportError:
    import investments, portfolio_ops as ops, recurring
    import runtime_storage as storage


def shift_month(month,offset):
    first=recurring.month_start(month);index=first.year*12+first.month-1+offset
    return f'{index//12:04d}-{index%12+1:02d}'


def first_invoice(card,purchase_date):
    if not card.get('closing_day'):raise ValueError('Cadastre o dia de fechamento do cartão antes de vincular compras')
    month=purchase_date[:7]
    if purchase_date>=recurring.due_date(month,card['closing_day']):month=shift_month(month,1)
    return shift_month(month,1) if card['closing_day']>=card['due_day'] else month


def parts(purchase):
    total=ops.cents(purchase['amount']);count=purchase['installments']
    regular=(total/Decimal(count)).quantize(ops.CENT,rounding=ROUND_DOWN)
    return [{'number':i+1,'date':recurring.due_date(shift_month(purchase['first_invoice_month'],i),purchase['due_day']),
             'amount':float(regular if i<count-1 else total-regular*(count-1))} for i in range(count)]


def invoice_key(card_id,month):return card_id+':'+month


def invoices(prefs):
    cards={card['id']:card for card in prefs.get('credit_cards',[])};result={}
    for purchase in prefs.get('card_purchases',[]):
        for part in parts(purchase):
            key=invoice_key(purchase['card_id'],part['date'][:7])
            bill=result.setdefault(key,{'key':key,'card_id':purchase['card_id'],'name':cards.get(purchase['card_id'],{}).get('name','Cartão arquivado'),
                'month':part['date'][:7],'due_date':part['date'],'items':[],'total':0,'paid':0,'payments':[]})
            bill['due_date']=min(bill['due_date'],part['date'])
            bill['items'].append({**part,'purchase_id':purchase['id'],'label':purchase['where'],'purchase_date':purchase['date'],
                                  'category':purchase['category'],'installments':purchase['installments'],'total_purchase':purchase['amount']})
            bill['total']=float(ops.cents(bill['total'])+ops.cents(part['amount']))
    for payment in prefs.get('card_payments',[]):
        if payment.get('reversed'):continue
        if payment['invoice_key'] in result:
            bill=result[payment['invoice_key']];bill['paid']=float(ops.cents(bill['paid'])+ops.cents(payment['amount']));bill['payments'].append(payment)
    for entry in prefs.get('card_refunds',[]):
        if entry.get('reversed'):continue
        if entry['invoice_key'] in result:
            bill=result[entry['invoice_key']]
            bill.setdefault('refunds',[]).append(entry)
            bill['total']=round(bill['total']-entry['amount'],2)
    today=investments.investment_today().isoformat()
    for bill in result.values():
        bill['remaining']=float(ops.cents(bill['total'])-ops.cents(bill['paid']))
        bill['credit']=max(0,-bill['remaining'])
        bill['remaining']=max(0,bill['remaining'])
        review=prefs.get('invoice_reviews',{}).get(bill['key'])
        bill['review']=review
        bill['review_difference']=round(review['amount']-bill['total'],2) if review else None
        bill['status']='paid' if bill['remaining']==0 else 'overdue' if bill['due_date']<today else 'partial' if bill['paid'] else 'open'
    return sorted(result.values(),key=lambda bill:(bill['due_date'],bill['name']))


def expense_rows(prefs):
    rows=[]
    for purchase in prefs.get('card_purchases',[]):
        for part in parts(purchase):
            rows.append({'id':f"card:{purchase['id']}:{part['number']}",'date':part['date'],'amount':part['amount'],
                'where':purchase['where'],'category':purchase['category'],'payment':'Crédito',
                'description':f"{purchase.get('description','')} · Cartão · Parcela {part['number']}/{purchase['installments']}",
                'finance':{'card_purchase_id':purchase['id'],'credit_card_id':purchase['card_id'],'invoice_key':invoice_key(purchase['card_id'],part['date'][:7])},
                'installment_group':None,'installment_number':part['number'],'installment_count':purchase['installments']})
    for entry in prefs.get('card_refunds',[]):
        if entry.get('reversed'):continue
        bill=next((b for b in invoices(prefs) if b['key']==entry['invoice_key']),None)
        if bill:rows.append({'id':'refund:'+entry['id'],'date':bill['due_date'],'amount':-entry['amount'],'where':bill['name']+' · Estorno','category':'Contas','payment':'Crédito','description':entry['reason'],'finance':{'card_purchase_id':'refund','invoice_key':bill['key']},'installment_group':None})
    return rows


def expense_fingerprint(entry):
    values=[entry['date'],round(entry['amount'],2),entry['where'],entry['category'],entry['payment'],entry.get('description','')]
    return hashlib.sha256(json.dumps(values,ensure_ascii=False).encode()).hexdigest()


def planned_expenses(expenses,prefs):
    try:from src import fixed_expenses
    except ImportError:import fixed_expenses
    expenses=list(expenses)+fixed_expenses.expense_rows(prefs)
    linked=Counter(entry['linked_fingerprint'] for entry in prefs.get('card_purchases',[]) if entry.get('linked_fingerprint'))
    if not linked:return list(expenses)+expense_rows(prefs)
    rows=[]
    for entry in expenses:
        signature=expense_fingerprint(entry)
        if linked[signature]:linked[signature]-=1
        else:rows.append(entry)
    return rows+expense_rows(prefs)


def payment_expenses(prefs):
    names={card['id']:card['name'] for card in prefs.get('credit_cards',[])}
    return [{'id':'card-payment:'+payment['id'],'date':payment['date'],'amount':payment['amount'],'where':names.get(payment['invoice_key'].split(':')[0],'Cartão'),
             'category':'Contas','payment':'Pix','description':'Pagamento de fatura','finance':{'card_payment':True},'installment_group':None}
            for payment in prefs.get('card_payments',[]) if not payment.get('reversed')]


def purchase(payload,user_id=None):
    if not isinstance(payload,dict):raise ValueError('Compra inválida')
    original_rows=storage.read_expenses(user_id);categories=set(storage.read_categories(user_id))
    linked_id=payload.get('linked_expense_id')
    linked=next((entry for entry in original_rows if str(entry['id'])==str(linked_id)),None) if linked_id else None
    if linked_id and (not linked or linked['payment']!='Crédito' or linked.get('installment_group')):raise ValueError('Escolha um gasto avulso no crédito desta conta; parcelas existentes devem ser vinculadas individualmente')
    data={**payload,**({'date':linked['date'],'amount':linked['amount'],'where':linked['where'],'category':linked['category'],'description':linked['description']} if linked else {})}
    day=investments.iso_date(data.get('date'),'Data da compra')
    if day>investments.investment_today().isoformat():raise ValueError('A compra não pode ser futura')
    amount=float(ops.cents(investments.number(data.get('amount'),'Valor total',minimum=.01)))
    if amount>10000000:raise ValueError('Revise o valor da compra')
    place=str(data.get('where','')).strip();category=str(data.get('category',''));description=str(data.get('description','')).strip()
    try:
        count=int(data.get('installments',1))
        if str(count)!=str(data.get('installments',1)) or not 1<=count<=120 or ops.cents(amount)<Decimal(count)/100:raise ValueError()
    except (TypeError,ValueError) as exc:raise ValueError('Informe de 1 a 120 parcelas, de ao menos um centavo') from exc
    if not place or len(place)>100 or len(description)>200 or category not in categories:raise ValueError('Revise estabelecimento, categoria e descrição')
    item_id=str(payload.get('id') or '');request_id=str(payload.get('request_id') or '')[:100]
    def apply(store):
        prefs=store.setdefault('preferences',{});items=prefs.setdefault('card_purchases',[])
        duplicate=next((entry for entry in items if request_id and entry.get('request_id')==request_id),None)
        if duplicate and not item_id:return duplicate
        old=next((entry for entry in items if entry['id']==item_id),None)
        if item_id and not old:raise KeyError('Compra não encontrada')
        if old:assert_editable(prefs,old)
        card=next((entry for entry in prefs.get('credit_cards',[]) if entry['id']==data.get('card_id')),None)
        if not card:raise ValueError('Escolha um cartão desta conta')
        first=str(data.get('first_invoice_month') or first_invoice(card,day));recurring.month_start(first)
        if recurring.due_date(first,card['due_day'])<day:raise ValueError('A primeira fatura não pode vencer antes da compra')
        effective_link=linked['id'] if linked else old.get('linked_expense_id') if old else None
        if linked and any(entry.get('linked_fingerprint')==expense_fingerprint(linked) and entry['id']!=item_id for entry in items):raise ValueError('Este gasto já está vinculado a um cartão')
        saved={'id':item_id or uuid4().hex,'card_id':card['id'],'date':day,'amount':amount,'where':place,'category':category,'description':description,
               'installments':count,'first_invoice_month':first,'due_day':card['due_day'],'request_id':request_id,'linked_expense_id':effective_link,'linked_fingerprint':expense_fingerprint(linked) if linked else old.get('linked_fingerprint') if old else None}
        existing_bills={bill['key']:bill for bill in invoices(prefs)}
        if old and any(existing_bills.get(invoice_key(card['id'],part['date'][:7]),{}).get('paid',0)>0 for part in parts(saved)):
            raise ValueError('A fatura já tem pagamento. Desfaça os pagamentos antes de alterar suas compras')
        if old:items[items.index(old)]=saved
        else:items.append(saved)
        investments.audit_change(store,'card_purchase',place,old or {},saved,'Compra vinculada à fatura')
        return saved
    return investments.mutate_store(apply,user_id)


def assert_editable(prefs,purchase):
    keys={invoice_key(purchase['card_id'],p['date'][:7]) for p in parts(purchase)}
    if any(e['invoice_key'] in keys for e in prefs.get('card_refunds',[])) or any(k in keys for k in prefs.get('invoice_reviews',{})):
        raise ValueError('Fatura com estorno ou conferência: preserve a compra e seu histórico')
    keys={invoice_key(purchase['card_id'],part['date'][:7]) for part in parts(purchase)}
    if any(payment['invoice_key'] in keys and not payment.get('reversed') for payment in prefs.get('card_payments',[])):
        raise ValueError('Desfaça os pagamentos das faturas afetadas antes de editar ou excluir esta compra')


def delete_purchase(item_id,user_id=None):
    def apply(store):
        prefs=store.setdefault('preferences',{});items=prefs.get('card_purchases',[])
        item=next((entry for entry in items if entry['id']==item_id),None)
        if not item:raise KeyError('Compra não encontrada')
        assert_editable(prefs,item);prefs['card_purchases']=[entry for entry in items if entry['id']!=item_id]
        investments.audit_change(store,'card_purchase_removed',item['where'],item,{},'Compra removida; gasto original, se vinculado, permanece')
        return {'deleted':True}
    return investments.mutate_store(apply,user_id)


def pay(payload,user_id=None):
    key=str(payload.get('invoice_key',''));request_id=str(payload.get('request_id',''))[:100]
    if not request_id:raise ValueError('Identificador do pagamento ausente. Reabra o formulário')
    day=investments.iso_date(payload.get('date'),'Data do pagamento')
    if day>investments.investment_today().isoformat():raise ValueError('Confirme apenas pagamentos já efetuados')
    amount=float(ops.cents(investments.number(payload.get('amount'),'Valor pago',minimum=.01)))
    def apply(store):
        prefs=store.setdefault('preferences',{});payments=prefs.setdefault('card_payments',[])
        previous=next((entry for entry in payments if entry.get('request_id')==request_id),None)
        if previous:
            if previous['invoice_key']!=key or previous['date']!=day or previous['amount']!=amount:raise ValueError('Este identificador já foi usado em outro pagamento. Reabra o formulário')
            return previous
        bill=next((entry for entry in invoices(prefs) if entry['key']==key),None)
        if not bill:raise KeyError('Fatura não encontrada')
        if amount>bill['remaining']:raise ValueError('O pagamento ultrapassa o saldo pendente da fatura')
        if day<min(entry['purchase_date'] for entry in bill['items']):raise ValueError('Pagamento anterior às compras da fatura')
        entry={'id':uuid4().hex,'invoice_key':key,'date':day,'amount':amount,'request_id':request_id}
        payments.append(entry);investments.audit_change(store,'card_payment',bill['name'],{},entry,'Pagamento da fatura confirmado pelo usuário')
        return entry
    return investments.mutate_store(apply,user_id)


def reverse_payment(payment_id,user_id=None):
    def apply(store):
        payment=next((entry for entry in store.get('preferences',{}).get('card_payments',[]) if entry['id']==payment_id),None)
        if not payment:raise KeyError('Pagamento não encontrado')
        if not payment.get('reversed'):
            before=dict(payment);payment['reversed']=True
            investments.audit_change(store,'card_payment_reversed','Fatura',before,payment,'Pagamento desfeito pelo usuário')
        return payment
    return investments.mutate_store(apply,user_id)


def status(month,user_id=None):
    recurring.month_start(month);prefs=investments.load_store(user_id).get('preferences',{});bills=invoices(prefs)
    selected=[bill for bill in bills if bill['month']==month]
    return {'month':month,'invoices':selected,'open_invoices':[bill for bill in bills if bill['remaining']>0],
            'total':round(sum(bill['total'] for bill in selected),2),'paid':round(sum(bill['paid'] for bill in selected),2),
            'remaining':round(sum(bill['remaining'] for bill in selected),2),
            'future_installments':round(sum(bill['remaining'] for bill in bills if bill['month']>month),2)}


def validate_state(prefs):
    """Reject orphan invoices, invalid totals and duplicate restored payment requests."""
    import re
    card_ids={entry['id'] for entry in prefs.get('credit_cards',[])};ids=set()
    purchases=prefs.get('card_purchases',[]);payments=prefs.get('card_payments',[])
    if not isinstance(purchases,list) or not isinstance(payments,list) or len(purchases)>10000 or len(payments)>10000:raise ValueError('Histórico de cartões inválido')
    for item in purchases:
        if not isinstance(item,dict) or not re.fullmatch('[a-f0-9]{32}',str(item.get('id',''))) or item['id'] in ids:raise ValueError('Compra de cartão inválida')
        ids.add(item['id'])
        if item.get('card_id') not in card_ids:raise ValueError('Compra sem cartão')
        item['date']=investments.iso_date(item.get('date'),'Data da compra')
        recurring.month_start(item.get('first_invoice_month'))
        item['amount']=float(ops.cents(investments.number(item.get('amount'),'Compra',minimum=.01)))
        if not isinstance(item.get('installments'),int) or not 1<=item['installments']<=120 or item['amount']<item['installments']/100:raise ValueError('Parcelas inválidas')
        if not isinstance(item.get('due_day'),int) or not 1<=item['due_day']<=31:raise ValueError('Vencimento inválido')
        if not isinstance(item.get('where'),str) or not 1<=len(item['where'])<=100 or not isinstance(item.get('category'),str) or not 1<=len(item['category'])<=40:raise ValueError('Compra inválida')
        if recurring.due_date(item['first_invoice_month'],item['due_day'])<item['date']:raise ValueError('Fatura anterior à compra')
        fingerprint=item.get('linked_fingerprint')
        if fingerprint and not re.fullmatch('[a-f0-9]{64}',str(fingerprint)):raise ValueError('Vínculo inválido')
        item['linked_expense_id']=None  # SQL identifiers are reassigned during restore.
    requests=set();payment_ids=set();known={entry['key']:entry for entry in invoices({**prefs,'card_payments':[]})}
    for payment in payments:
        if not isinstance(payment,dict) or not re.fullmatch('[a-f0-9]{32}',str(payment.get('id',''))) or payment['id'] in payment_ids:raise ValueError('Pagamento inválido')
        payment_ids.add(payment['id'])
        key=payment.get('invoice_key');request=payment.get('request_id')
        if (key not in known and not payment.get('reversed')) or not isinstance(request,str) or not 1<=len(request)<=100 or request in requests:raise ValueError('Pagamento sem fatura ou duplicado')
        requests.add(request);payment['date']=investments.iso_date(payment.get('date'),'Pagamento')
        if not re.fullmatch(r'[a-f0-9]{32}:\d{4}-\d{2}',str(key)):raise ValueError('Fatura inválida')
        recurring.month_start(key.split(':')[1])
        if key in known and payment['date']<min(entry['purchase_date'] for entry in known[key]['items']):raise ValueError('Pagamento anterior à compra')
        payment['amount']=float(ops.cents(investments.number(payment.get('amount'),'Pagamento',minimum=.01)))
        if 'reversed' in payment and not isinstance(payment['reversed'],bool):raise ValueError('Estorno inválido')
    for bill in invoices({**prefs,'card_refunds':[]}):
        if bill.get('credit',0)>0:raise ValueError('Pagamentos excedem o valor da fatura')
    refunds=prefs.get('card_refunds',[])
    if not isinstance(refunds,list):raise ValueError('Estornos inválidos')
    refund_ids=set();refund_requests=set()
    for e in refunds:
        if not isinstance(e,dict) or not re.fullmatch('[a-f0-9]{32}',str(e.get('id',''))) or e['id'] in refund_ids or e.get('invoice_key') not in known:raise ValueError('Estorno inválido')
        if 'reversed' in e and not isinstance(e['reversed'],bool):raise ValueError('Estado de estorno inválido')
        refund_ids.add(e['id'])
        if not isinstance(e.get('request_id'),str) or not 1<=len(e['request_id'])<=100 or e['request_id'] in refund_requests:raise ValueError('Estorno duplicado')
        refund_requests.add(e['request_id']);e['date']=investments.iso_date(e.get('date'),'Estorno')
        e['amount']=float(ops.cents(investments.number(e.get('amount'),'Crédito',minimum=.01)))
        if not isinstance(e.get('reason'),str) or not 3<=len(e['reason'])<=200:raise ValueError('Motivo inválido')
    if any(b['total']<0 for b in invoices(prefs)):raise ValueError('Estorno excede a fatura')
    reviews=prefs.get('invoice_reviews',{})
    if not isinstance(reviews,dict):raise ValueError('Conferências inválidas')
    for key,e in reviews.items():
        if key not in known or not isinstance(e,dict):raise ValueError('Conferência sem fatura')
        e['date']=investments.iso_date(e.get('date'),'Conferência')
        for field in ('amount','registered_total'):e[field]=float(ops.cents(investments.number(e.get(field),'Conferência')))


def ensure_original_editable(item_id,user_id=None):
    entry=next((entry for entry in storage.read_expenses(user_id) if str(entry['id'])==str(item_id)),None)
    if not entry:return
    signature=expense_fingerprint(entry)
    if any(item.get('linked_fingerprint')==signature for item in investments.load_store(user_id).get('preferences',{}).get('card_purchases',[])):
        raise ValueError('Este gasto está vinculado a uma fatura. Faça a alteração pelo controle de cartões')


def ensure_category_editable(category,user_id=None):
    prefs=investments.load_store(user_id).get('preferences',{})
    if any(v.get('category')==category for plan in prefs.get('fixed_expenses',[]) for v in plan.get('versions',[])):
        raise ValueError('Esta categoria tem gastos fixos no histórico. Preserve a categoria ou escolha outro nome para a nova categoria')
    if any(item['category']==category for item in investments.load_store(user_id).get('preferences',{}).get('card_purchases',[])):
        raise ValueError('Esta categoria está no histórico de cartões. Altere as compras sem pagamento antes de renomear ou excluir a categoria')


def refund(payload,user_id=None):
    """Record an actual credit on one invoice, preserving the purchase and payments."""
    if not isinstance(payload,dict):raise ValueError('Estorno inválido')
    request=str(payload.get('request_id',''));key=str(payload.get('invoice_key',''))
    day=investments.iso_date(payload.get('date'),'Data do crédito')
    amount=float(ops.cents(investments.number(payload.get('amount'),'Crédito',minimum=.01)))
    reason=str(payload.get('reason','')).strip()
    if not 1<=len(request)<=100 or not 3<=len(reason)<=200 or day>investments.investment_today().isoformat():raise ValueError('Confira data, motivo e identificador')
    def apply(store):
        prefs=store.setdefault('preferences',{});entries=prefs.setdefault('card_refunds',[])
        previous=next((e for e in entries if e['request_id']==request),None)
        if previous:
            if any(previous[k]!=v for k,v in {'invoice_key':key,'date':day,'amount':amount,'reason':reason}.items()):raise ValueError('Identificador já usado')
            return previous
        bill=next((bill for bill in invoices(prefs) if bill['key']==key),None)
        if not bill or amount>bill['total'] or day<min(e['purchase_date'] for e in bill['items']):raise ValueError('Crédito deve corresponder a uma fatura existente e não ultrapassar seu total líquido')
        entry={'id':uuid4().hex,'request_id':request,'invoice_key':key,'date':day,'amount':amount,'reason':reason}
        entries.append(entry);investments.audit_change(store,'card_refund',bill['name'],{},entry,reason)
        return entry
    return investments.mutate_store(apply,user_id)


def review(payload,user_id=None):
    key=str(payload.get('invoice_key',''))
    amount=float(ops.cents(investments.number(payload.get('amount'),'Total da fatura')))
    def apply(store):
        prefs=store.setdefault('preferences',{})
        bill=next((b for b in invoices(prefs) if b['key']==key),None)
        if not bill:raise ValueError('Fatura não encontrada')
        entry={'date':investments.investment_today().isoformat(),'amount':amount,'registered_total':bill['total']}
        prefs.setdefault('invoice_reviews',{})[key]=entry
        investments.audit_change(store,'invoice_review',bill['name'],{},entry,'Total conferido no extrato')
        return {**entry,'difference':round(amount-bill['total'],2)}
    return investments.mutate_store(apply,user_id)


def reverse_refund(payload,user_id=None):
    reason=str(payload.get('reason','')).strip()
    if not 3<=len(reason)<=200:raise ValueError('Informe o motivo da correção')
    def apply(store):
        entry=next((e for e in store.get('preferences',{}).get('card_refunds',[]) if e['id']==payload.get('id')),None)
        if not entry:raise ValueError('Estorno não encontrado')
        if not entry.get('reversed'):
            before=dict(entry);entry['reversed']=True
            investments.audit_change(store,'card_refund_reversed','Fatura',before,entry,reason)
        return entry
    return investments.mutate_store(apply,user_id)
