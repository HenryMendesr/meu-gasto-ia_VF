"""Monthly fixed expenses with dated versions and explicit payment confirmation."""
from datetime import date
from uuid import uuid4
try:
    from src import investments, recurring, portfolio_ops as ops, runtime_storage as storage
except ImportError:
    import investments, recurring, portfolio_ops as ops
    import runtime_storage as storage


def shift(month, offset):
    d=recurring.month_start(month);n=d.year*12+d.month-1+offset
    return f'{n//12:04d}-{n%12+1:02d}'


def version(plan, month):
    candidates=[v for v in plan['versions'] if v['from_month']<=month]
    return max(candidates,key=lambda v:v['from_month']) if candidates else None


def row(plan, month, prefs):
    v=version(plan,month)
    saved=prefs.get('fixed_payments',{}).get(plan['id']+':'+month,{})
    if saved.get('skipped'):return None
    if not saved.get('paid') and (not v or not v.get('enabled',True)):return None
    values=saved if saved.get('paid') else v
    if not values:return None
    return {'id':'fixed:'+plan['id']+':'+month,'date':recurring.due_date(month,values['day']),
            'amount':values['amount'],'where':values['name'],'category':values['category'],'payment':values['payment'],
            'description':'Gasto fixo mensal','installment_group':None,
            'finance':{'fixed_expense_id':plan['id'],'fixed_month':month,'paid':saved.get('paid',False),
                       **({'paid_date':saved['paid_date']} if saved.get('paid') else {})}}


def expense_rows(prefs):
    end=shift(investments.investment_today().isoformat()[:7],12)
    rows=[]
    for plan in prefs.get('fixed_expenses',[]):
        current=min(v['from_month'] for v in plan['versions'])
        while current<=end:
            entry=row(plan,current,prefs)
            if entry:rows.append(entry)
            current=shift(current,1)
    return rows


def status(month,user_id=None):
    recurring.month_start(month)
    prefs=investments.load_store(user_id).get('preferences',{})
    items=[]
    for plan in prefs.get('fixed_expenses',[]):
        v=version(plan,month)
        if not v:continue
        entry=row(plan,month,prefs)
        saved=prefs.get('fixed_payments',{}).get(plan['id']+':'+month,{})
        items.append({'id':plan['id'],**v,'row':entry,'skipped':saved.get('skipped',False)})
    return {'month':month,'items':items,'total':round(sum(i['row']['amount'] for i in items if i['row'] and i['row']['payment']!='Voucher'),2),
            'voucher_total':round(sum(i['row']['amount'] for i in items if i['row'] and i['row']['payment']=='Voucher'),2),
            'paid':round(sum(i['row']['amount'] for i in items if i['row'] and i['row']['payment']!='Voucher' and i['row']['finance']['paid']),2)}


def save(payload,user_id=None):
    if not isinstance(payload,dict):raise ValueError('Gasto fixo inválido')
    month=str(payload.get('from_month',''));recurring.month_start(month)
    current=investments.investment_today().isoformat()[:7]
    if not shift(current,-120)<=month<=shift(current,12):raise ValueError('Escolha um mês entre dez anos atrás e os próximos doze meses')
    name=str(payload.get('name','')).strip()
    if not 2<=len(name)<=100:raise ValueError('Informe o nome do gasto')
    amount=float(ops.cents(investments.number(payload.get('amount'),'Valor mensal',minimum=.01)))
    day=payload.get('day')
    try:
        parsed=int(day)
        if str(parsed)!=str(day) or not 1<=parsed<=31:raise ValueError()
    except (ValueError,TypeError):raise ValueError('Informe um dia de 1 a 31')
    category=str(payload.get('category','Contas'));payment=str(payload.get('payment','Pix'))
    if category not in storage.read_categories(user_id):raise ValueError('Escolha uma categoria cadastrada')
    if payment not in {'Pix','Débito','Dinheiro','Transferência','Voucher','Não informado'}:raise ValueError('Para compras no cartão, use Cartões para evitar duplicação da fatura')
    item_id=str(payload.get('id',''));enabled=payload.get('enabled',True)
    if not isinstance(enabled,bool):raise ValueError('Estado de repetição inválido')
    def apply(store):
        prefs=store.setdefault('preferences',{});plans=prefs.setdefault('fixed_expenses',[])
        plan=next((p for p in plans if p['id']==item_id),None)
        if item_id and not plan:raise ValueError('Gasto fixo não encontrado')
        if plan and month<current:raise ValueError('Edite a partir deste mês; os meses anteriores ficam preservados')
        before=dict(plan) if plan else {}
        if not plan:
            if len(plans)>=100:raise ValueError('Limite de 100 gastos fixos')
            plan={'id':uuid4().hex,'versions':[]};plans.append(plan)
        v={'from_month':month,'name':name,'amount':amount,'day':parsed,'category':category,'payment':payment,'enabled':enabled}
        plan['versions']=[v0 for v0 in plan['versions'] if v0['from_month']<month]+[v]
        investments.audit_change(store,'fixed_expense',name,before,plan,'Repetição mensal ajustada a partir de '+month)
        return plan
    return investments.mutate_store(apply,user_id)


def payment(payload,user_id=None):
    month=str(payload.get('month',''));recurring.month_start(month)
    action=payload.get('action');item_id=payload.get('id')
    if action not in {'pay','undo','skip','restore'}:raise ValueError('Ação inválida')
    def apply(store):
        prefs=store.setdefault('preferences',{});plan=next((p for p in prefs.get('fixed_expenses',[]) if p['id']==item_id),None)
        if not plan:raise ValueError('Gasto fixo não encontrado')
        if not version(plan,month) or month>shift(investments.investment_today().isoformat()[:7],12):raise ValueError('Escolha um mês dentro do período do gasto fixo')
        records=prefs.setdefault('fixed_payments',{});key=item_id+':'+month;before=dict(records.get(key,{}))
        if action=='pay':
            entry=row(plan,month,prefs)
            if not entry:raise ValueError('Restaure o gasto antes de confirmar')
            if entry['finance']['paid']:return records[key]
            day=investments.iso_date(payload.get('paid_date'),'Data do pagamento')
            if day>investments.investment_today().isoformat():raise ValueError('Confirme somente pagamentos já realizados')
            v=version(plan,month)
            records[key]={**v,'paid':True,'paid_date':day}
        elif action=='skip':
            if before.get('paid'):raise ValueError('Desfaça a confirmação de pagamento primeiro')
            records[key]={'skipped':True}
        else:records.pop(key,None)
        investments.audit_change(store,'fixed_payment',plan['id'],before,records.get(key,{}),'Gasto fixo: '+action+' · '+month)
        return records.get(key,{})
    return investments.mutate_store(apply,user_id)


def validate(prefs,categories):
    plans=prefs.get('fixed_expenses',[]);payments=prefs.get('fixed_payments',{})
    if not isinstance(plans,list) or len(plans)>100 or not isinstance(payments,dict):raise ValueError('Gastos fixos inválidos')
    import re
    ids=set()
    def values(v):
        if not isinstance(v,dict) or not isinstance(v.get('enabled',True),bool):raise ValueError('Repetição inválida')
        if not isinstance(v.get('name'),str) or not 2<=len(v['name'])<=100 or v.get('category') not in categories:raise ValueError('Gasto fixo inválido')
        v['amount']=float(ops.cents(investments.number(v.get('amount'),'Valor mensal',minimum=.01)))
        if type(v.get('day')) is not int or not 1<=v['day']<=31 or v.get('payment') not in {'Pix','Débito','Dinheiro','Transferência','Voucher','Não informado'}:raise ValueError('Vencimento ou pagamento inválido')
    for p in plans:
        if not isinstance(p,dict) or not re.fullmatch('[a-f0-9]{32}',str(p.get('id',''))) or p['id'] in ids:raise ValueError('Gasto fixo duplicado ou inválido')
        ids.add(p['id']);versions=p.get('versions')
        if not isinstance(versions,list) or not 1<=len(versions)<=1200:raise ValueError('Histórico de gasto fixo inválido')
        months=[]
        for v in versions:
            values(v);recurring.month_start(v.get('from_month'));months.append(v['from_month'])
        if months!=sorted(set(months)):raise ValueError('Histórico de gasto fixo duplicado')
        if months[0]<'1900-01':raise ValueError('Histórico de gasto fixo muito antigo')
    for key,v in payments.items():
        if not isinstance(key,str) or not re.fullmatch(r'[a-f0-9]{32}:\d{4}-\d{2}',key) or key[:32] not in ids or not isinstance(v,dict):raise ValueError('Pagamento de gasto fixo inválido')
        recurring.month_start(key[33:])
        owner=next(p for p in plans if p['id']==key[:32])
        if not version(owner,key[33:]):raise ValueError('Pagamento anterior ao início do gasto fixo')
        for flag in ('paid','skipped'):
            if flag in v and not isinstance(v[flag],bool):raise ValueError('Estado de gasto fixo inválido')
        if v.get('paid'):
            values(v);v['paid_date']=investments.iso_date(v.get('paid_date'),'Pagamento')
            if v.get('skipped'):raise ValueError('Pagamento desconsiderado inválido')
