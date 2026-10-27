"""Versioned, validated financial backups. Credentials never leave the server."""
import copy
import json
import math
import re
from datetime import date, datetime, timezone
from decimal import Decimal

try:
    from src import investments, portfolio_ops as ops
except ImportError:
    import investments
    import portfolio_ops as ops

TABLES = {
    'expenses': ['expense_date','amount','place','category','payment','description','installment_group','installment_number','installment_count','original_total','finance_details'],
    'incomes': ['month','cash','voucher','payday','source'],
    'income_entries': ['entry_date','amount','source','category','description'],
    'budgets': ['month','category','amount'],
    'budget_categories': ['name'],
}
MAX_BYTES = 3_000_000


def safe_json(value):
    if isinstance(value, dict):return {str(k):safe_json(v) for k,v in value.items()}
    if isinstance(value, (list,tuple)):return [safe_json(v) for v in value]
    if isinstance(value, (date,datetime)):return value.isoformat()
    if isinstance(value, Decimal):return float(value)
    return value


def package(tables, portfolio):
    return {'format':'minha-carteira','version':1,'exported_at':datetime.now(timezone.utc).isoformat(),
            'data':{**safe_json(tables),'portfolio':safe_json(portfolio)}}


def amount(value, minimum=0):
    try:number=float(value)
    except (TypeError,ValueError) as exc:raise ValueError('Valor inválido no backup') from exc
    if not math.isfinite(number) or not minimum <= number <= 1e18:
        raise ValueError('Valor inválido no backup')
    return round(number,2)


def day(value):
    return investments.iso_date(value,'Data do backup')


def text(value, maximum, required=False):
    value=str(value or '').strip()
    if len(value)>maximum or required and not value:raise ValueError('Texto inválido no backup')
    return value


def _validate(payload):
    if not isinstance(payload,dict) or payload.get('format')!='minha-carteira' or payload.get('version')!=1:
        raise ValueError('Use um backup JSON da Minha Carteira, versão 1')
    try:encoded=json.dumps(payload,allow_nan=False)
    except (ValueError,TypeError,RecursionError) as exc:raise ValueError('Backup inválido') from exc
    if len(encoded.encode())>MAX_BYTES:raise ValueError('O backup deve ter até 3 MB')
    original=payload.get('data')
    if not isinstance(original,dict):raise ValueError('Dados do backup ausentes')
    data={}
    for table,columns in TABLES.items():
        rows=original.get(table)
        if not isinstance(rows,list) or len(rows)>10000:raise ValueError('Tabelas do backup inválidas')
        data[table]=[]
        for source in rows:
            if not isinstance(source,dict):raise ValueError('Lançamento inválido no backup')
            data[table].append({key:source.get(key) for key in columns})
    categories={text(row['name'],40,True) for row in data['budget_categories']}
    if not categories:raise ValueError('O backup não contém categorias')
    for row in data['budget_categories']:row['name']=text(row['name'],40,True)
    if len(categories)!=len(data['budget_categories']):raise ValueError('Categoria duplicada no backup')
    for table,keys in [('incomes',('month',)),('budgets',('month','category'))]:
        identities=[tuple(row[key] for key in keys) for row in data[table]]
        if len(set(identities))!=len(identities):raise ValueError('Registro duplicado no backup')
    seen_groups=set()
    for row in data['expenses']:
        row['expense_date']=day(row['expense_date']);row['amount']=amount(row['amount'],.01)
        row['place']=text(row['place'],100,True);row['category']=text(row['category'],40,True)
        row['description']=text(row['description'],200)
        if row['category'] not in categories or row['payment'] not in {'Pix','Crédito','Débito','Dinheiro','Transferência','Voucher','Não informado'}:raise ValueError('Categoria ou pagamento inválido no backup')
        finance=row['finance_details']
        if isinstance(finance,str):
            try:finance=json.loads(finance)
            except ValueError as exc:raise ValueError('Dados financeiros inválidos') from exc
        if not isinstance(finance,dict):raise ValueError('Dados financeiros inválidos')
        if finance.get('paid'):
            finance['paid_date']=day(finance.get('paid_date'))
        for key in ('paid','debt_entry'):
            if key in finance and not isinstance(finance[key],bool):raise ValueError('Indicador financeiro inválido')
        for key in ('principal_part','interest_part','principal','monthly_payment','total_payment'):
            if key in finance and finance[key] is not None:finance[key]=amount(finance[key])
        if finance.get('financing_kind') not in {None,'purchase','loan','debt','asset'}:raise ValueError('Tipo de compromisso inválido')
        row['finance_details']=finance
        if row['installment_group']:
            if not re.fullmatch('[a-f0-9]{32}',str(row['installment_group'])):raise ValueError('Grupo de parcelas inválido')
            number,count=int(row['installment_number']),int(row['installment_count'])
            if not 1<=number<=count<=600:raise ValueError('Parcelas inválidas no backup')
            key=(row['installment_group'],number)
            if key in seen_groups:raise ValueError('Parcela duplicada no backup')
            seen_groups.add(key);row['original_total']=amount(row['original_total'],.01)
        else:
            row.update(installment_group=None,installment_number=None,installment_count=None,original_total=None)
    for row in data['incomes']:
        day(str(row['month'])+'-01');row['cash']=amount(row['cash']);row['voucher']=amount(row['voucher'])
        row['source']=text(row['source'],100)
        if row['payday'] is not None and not 1<=int(row['payday'])<=31:raise ValueError('Dia de recebimento inválido')
    for row in data['income_entries']:
        row['entry_date']=day(row['entry_date']);row['amount']=amount(row['amount'],.01)
        row['source']=text(row['source'],100,True);row['category']=text(row['category'],40,True);row['description']=text(row['description'],200)
    for row in data['budgets']:
        day(str(row['month'])+'-01');row['amount']=amount(row['amount'])
        if row['category'] not in categories:raise ValueError('Limite com categoria inválida')
    portfolio=copy.deepcopy(original.get('portfolio'))
    if not isinstance(portfolio,dict) or not isinstance(portfolio.get('investments'),list):raise ValueError('Carteira inválida no backup')
    for key in ('history','wealth_history','goals','audit_log','feedback'):
        if not isinstance(portfolio.get(key,[]),list) or any(not isinstance(entry,dict) for entry in portfolio.get(key,[])):raise ValueError('Histórico inválido no backup')
    prefs=portfolio.get('preferences',{})
    if not isinstance(prefs,dict):raise ValueError('Preferências inválidas')
    for key in ('onboarding_dismissed','analytics_consent'):
        if key in prefs and not isinstance(prefs[key],bool):raise ValueError('Preferência inválida')
    for key in ('income_modes','category_rules'):
        if not isinstance(prefs.get(key,{}),dict):raise ValueError('Preferência inválida')
    for key,value in prefs.get('category_rules',{}).items():
        if not isinstance(value,str) or not 1<=len(value)<=40 or len(key)>100:raise ValueError('Regra de categoria inválida')
    try:from src import recurring
    except ImportError:import recurring
    if 'salary_plan' in prefs:
        plan=prefs['salary_plan']
        if isinstance(plan,dict) and plan.get('enabled') is False and plan.get('payments'):
            prefs['salary_plan']={**recurring.validate_plan({**plan,'enabled':True}),'enabled':False}
        else:prefs['salary_plan']=recurring.validate_plan(plan)
    receipts=prefs.get('salary_receipts',[])
    if not isinstance(receipts,list) or len(receipts)>10000:raise ValueError('Recebimentos inválidos')
    receipt_keys=set()
    for entry in receipts:
        if not isinstance(entry,dict) or not re.fullmatch(r'\d{4}-\d{2}:[12]',str(entry.get('key',''))) or entry['key'] in receipt_keys:raise ValueError('Recebimento duplicado ou inválido')
        receipt_keys.add(entry['key']);entry['date']=day(entry.get('date'))
        if entry.get('month')!=entry['date'][:7] or entry['key'][:7]!=entry['month']:raise ValueError('Data do recebimento inválida')
        if entry.get('status') not in {'scheduled','confirmed','skipped'}:raise ValueError('Estado do recebimento inválido')
        entry['amount']=amount(entry.get('amount'),.01);entry['source']=text(entry.get('source'),100,True)
    cards=prefs.get('credit_cards',[])
    if not isinstance(cards,list) or len(cards)>100:raise ValueError('Cartões inválidos')
    card_ids=set()
    for card in cards:
        if not isinstance(card,dict) or not re.fullmatch('[a-f0-9]{32}',str(card.get('id',''))) or card['id'] in card_ids:raise ValueError('Cartão inválido')
        card_ids.add(card['id']);card.update(recurring.validate_card(card))
    for month,mode in prefs.get('income_modes',{}).items():
        day(month+'-01')
        if mode not in {'auto','declared','imported','scheduled'}:raise ValueError('Base de renda inválida')
    for series in ('history','wealth_history'):
        for entry in portfolio.get(series,[]):
            entry['date']=day(entry.get('date'))
            for key,value in entry.items():
                if key!='date':entry[key]=amount(value,-1e18 if key=='profit_loss' else 0)
    portfolio['cash_balance']=amount(portfolio.get('cash_balance',0))
    ids=set()
    for item in portfolio['investments']:
        if not isinstance(item,dict) or not re.fullmatch('[a-f0-9]{32}',str(item.get('id',''))) or item['id'] in ids:raise ValueError('Ativo inválido ou duplicado no backup')
        ids.add(item['id'])
        if item.get('cash_funded_amount') is not None:item['cash_funded_amount']=amount(item['cash_funded_amount'])
        if item.get('operation_corrected') is not None and not isinstance(item['operation_corrected'],bool):raise ValueError('Operação inválida')
        if item.get('type') not in investments.ALL_TYPES:raise ValueError('Tipo de ativo inválido')
        if item['type'] in investments.VARIABLE_TYPES:
            if not re.fullmatch('[A-Z0-9.\\-]{2,20}',str(item.get('symbol',''))):raise ValueError('Código do ativo inválido')
            item['purchase_date']=day(item.get('purchase_date'))
            if item.get('quote_date') is not None:item['quote_date']=day(item['quote_date'])
            if item.get('previous_close') is not None:item['previous_close']=investments.number(item['previous_close'],'Fechamento anterior',minimum=0)
            item['quantity']=investments.number(item.get('quantity'),'Quantidade',minimum=0)
            item['average_price']=investments.number(item.get('average_price'),'Preço médio',minimum=.00000001)
            if item.get('current_price') is not None:item['current_price']=investments.number(item['current_price'],'Cotação',minimum=0)
            for collection in ('buys','sales','incomes'):
                if not isinstance(item.get(collection,[]),list):raise ValueError('Operações inválidas')
                seen=set()
                for entry in item.get(collection,[]):
                    if not isinstance(entry,dict) or not re.fullmatch('(initial-)?[a-f0-9]{32}',str(entry.get('id',''))) or entry['id'] in seen:raise ValueError('Identificador de operação inválido')
                    seen.add(entry['id']);entry['date']=day(entry.get('date'))
                    for flag in ('reversed','cash_debited','cash_credited','initial'):
                        if flag in entry and not isinstance(entry[flag],bool):raise ValueError('Indicador de operação inválido')
                    if not isinstance(entry.get('sequence',0),int) or not 0<=entry.get('sequence',0)<=1000000:raise ValueError('Sequência inválida')
                    if collection=='incomes':
                        entry['amount']=amount(entry.get('amount'),.01)
                        if entry.get('kind') not in {'Dividendos','JCP','Rendimento de FII','Outros proventos'}:raise ValueError('Provento inválido')
                    else:
                        entry['quantity']=investments.number(entry.get('quantity'),'Quantidade',minimum=.00000001)
                        entry['unit_price']=investments.number(entry.get('unit_price'),'Preço',minimum=.00000001)
                        entry['total']=amount(entry.get('total'),.01);entry['fees']=amount(entry.get('fees',0))
                        gross=float(ops.cents(Decimal(str(entry['quantity']))*Decimal(str(entry['unit_price']))))
                        expected=round(gross+(entry['fees'] if collection=='buys' else 0),2)
                        if abs(entry['total']-expected)>.011:raise ValueError('Total de operação inconsistente')
                        if collection=='sales':
                            if entry['fees']>=entry['total']:raise ValueError('Taxas inválidas')
                            entry['net_total']=round(entry['total']-entry['fees'],2)
            ops.position(item)
        else:
            item.update(investments.normalize_payload(item, item))
        investments.calculated(item)
    for goal in portfolio.get('goals',[]):
        if not re.fullmatch('[a-f0-9]{32}',str(goal.get('id',''))):raise ValueError('Meta inválida')
        goal['name']=text(goal.get('name'),80,True);goal['target_amount']=amount(goal.get('target_amount'),.01)
        goal['current_amount']=amount(goal.get('current_amount',0));goal['target_date']=day(goal.get('target_date'))
    # A restored backup never silently enables optional product metrics.
    portfolio.setdefault('preferences',{})['analytics_consent']=False
    portfolio.pop('usage_metrics',None)
    data['portfolio']=portfolio
    return data


def counts(data):
    return {**{table:len(data[table]) for table in TABLES},'investments':len(data['portfolio']['investments']),
            'goals':len(data['portfolio'].get('goals',[])),'cash_balance':data['portfolio'].get('cash_balance',0)}


def validate(payload):
    try:return _validate(payload)
    except (TypeError,KeyError,AttributeError,OverflowError,ArithmeticError) as exc:
        raise ValueError('Estrutura ou valores inválidos no backup') from exc
