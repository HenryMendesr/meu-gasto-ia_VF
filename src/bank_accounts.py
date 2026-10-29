"""User-owned account ledger; opening balances and corrections are not income."""
from uuid import uuid4
try:from src import investments, portfolio_ops as ops
except ImportError:import investments, portfolio_ops as ops


def signed(value):
    return float(ops.cents(investments.number(value, 'Valor', minimum=-1_000_000_000)))


def balance(account, entries, day=None):
    return round(account['opening_balance'] + sum(entry['amount'] for entry in entries
        if entry['account_id'] == account['id'] and not entry.get('reversed') and (not day or entry['date'] <= day)), 2)


def status(user_id=None):
    prefs=investments.load_store(user_id).get('preferences', {})
    entries=prefs.get('account_entries', [])
    today=investments.investment_today().isoformat()
    accounts=[{**account,'balance':balance(account, entries, today)} for account in prefs.get('bank_accounts', [])]
    return {'accounts':accounts, 'entries':entries, 'total':round(sum(a['balance'] for a in accounts), 2)}


def action(kind, payload, user_id=None):
    if not isinstance(payload,dict):raise ValueError('Dados da conta inválidos')
    request=str(payload.get('request_id',''))
    if not 1<=len(request)<=100:raise ValueError('Identificador da operação obrigatório')
    def apply(store):
        prefs=store.setdefault('preferences',{})
        accounts=prefs.setdefault('bank_accounts',[]);entries=prefs.setdefault('account_entries',[])
        requests=prefs.setdefault('account_requests',{})
        import json
        fingerprint=json.dumps([kind,payload],sort_keys=True,ensure_ascii=False)
        if request in requests:
            if requests[request]!=fingerprint:raise ValueError('Identificador já usado em outra operação')
            return
        day=investments.iso_date(payload.get('date'),'Data')
        if day>investments.investment_today().isoformat():raise ValueError('Informe uma data até hoje')
        name=str(payload.get('name','')).strip()
        reason=str(payload.get('reason','')).strip()
        if kind=='create':
            if not 2<=len(name)<=80:raise ValueError('Informe um nome de 2 a 80 caracteres')
            if len(accounts)>=100:raise ValueError('Limite de 100 contas')
            account={'id':uuid4().hex,'name':name,'opening_date':day,'opening_balance':signed(payload.get('amount'))}
            accounts.append(account)
            investments.audit_change(store,'bank_account',name,{},account,'Saldo inicial informado')
        else:
            account=next((a for a in accounts if a['id']==payload.get('account_id')),None)
            if not account:raise ValueError('Conta não encontrada')
            if day<account['opening_date']:raise ValueError('Movimento anterior ao saldo inicial')
            if not 3<=len(reason)<=200:raise ValueError('Informe uma descrição de 3 a 200 caracteres')
            amount=signed(payload.get('amount'))
            if kind=='reconcile':
                if any(e['account_id']==account['id'] and e['date']>day for e in entries):raise ValueError('Concilie na data do último movimento ou depois')
                expected=balance(account,entries,day)
                if signed(payload.get('expected_balance'))!=expected:raise ValueError('O saldo mudou. Confira novamente antes de conciliar')
                amount=round(amount-expected,2)
            elif kind not in {'entry','transfer'}:raise ValueError('Ação inválida')
            if kind=='transfer' and amount<=0:raise ValueError('Informe um valor positivo para transferir')
            group=uuid4().hex
            entry={'id':group,'account_id':account['id'],'date':day,'amount':-amount if kind=='transfer' else amount,'kind':kind,'reason':reason}
            if kind=='transfer':
                target=next((a for a in accounts if a['id']==payload.get('target_id')),None)
                if not target or target['id']==account['id'] or day<target['opening_date']:raise ValueError('Escolha outra conta válida')
                entries.append({**entry,'id':uuid4().hex,'account_id':target['id'],'amount':amount,'transfer_id':group})
                entry['transfer_id']=group
            entries.append(entry)
            investments.audit_change(store,'bank_'+kind,account['name'],{},entry,reason)
        requests[request]=fingerprint
    investments.mutate_store(apply,user_id)
    return status(user_id)


def validate(prefs):
    accounts=prefs.get('bank_accounts',[]);entries=prefs.get('account_entries',[])
    if not isinstance(accounts,list) or len(accounts)>100 or not isinstance(entries,list) or len(entries)>10000:raise ValueError('Contas inválidas no backup')
    import re
    ids=set()
    for a in accounts:
        if not isinstance(a,dict) or not re.fullmatch('[a-f0-9]{32}',str(a.get('id',''))) or a['id'] in ids:raise ValueError('Conta duplicada ou inválida')
        ids.add(a['id']);a['opening_date']=investments.iso_date(a.get('opening_date'),'Saldo inicial');a['opening_balance']=signed(a.get('opening_balance'))
        if not isinstance(a.get('name'),str) or not 2<=len(a['name'])<=80:raise ValueError('Nome de conta inválido')
    seen=set();transfers={}
    for e in entries:
        if not isinstance(e,dict) or not re.fullmatch('[a-f0-9]{32}',str(e.get('id',''))) or e['id'] in seen or e.get('account_id') not in ids:raise ValueError('Movimento de conta inválido')
        seen.add(e['id']);e['date']=investments.iso_date(e.get('date'),'Movimento');e['amount']=signed(e.get('amount'))
        if e['date']<next(a['opening_date'] for a in accounts if a['id']==e['account_id']):raise ValueError('Movimento anterior à conta')
        if e.get('kind') not in {'entry','transfer','reconcile'} or not isinstance(e.get('reason'),str) or not 3<=len(e['reason'])<=200:raise ValueError('Descrição de movimento inválida')
        if e.get('kind')=='transfer':transfers.setdefault(e.get('transfer_id'),[]).append(e)
    for group, pair in transfers.items():
        if not group or len(pair)!=2 or pair[0]['account_id']==pair[1]['account_id'] or pair[0]['date']!=pair[1]['date'] or round(sum(e['amount'] for e in pair),2)!=0:raise ValueError('Transferência incompleta')
    if not isinstance(prefs.get('account_requests',{}),dict) or any(not isinstance(k,str) or not isinstance(v,str) for k,v in prefs.get('account_requests',{}).items()):raise ValueError('Operações de conta inválidas')
