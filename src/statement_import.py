"""Leitura segura de extratos para revisão antes do lançamento."""
from __future__ import annotations

import csv
from datetime import date
from io import BytesIO, StringIO
import re
from statistics import median
import unicodedata

MAX_FILE_SIZE=6_000_000
MAX_ITEMS=500
MAX_PDF_PAGES=40
MAX_PDF_TEXT=2_000_000

CATEGORY_RULES={
    'Alimentação':('restaurante','lanchonete','ifood','rappi','padaria','cafe','cafeteria','burger','pizza','mcdonald','subway'),
    'Mercado':('mercado','supermerc','atacadao','assai','carrefour','pao de acucar','hortifruti','acougue'),
    'Transporte':('uber','99app','posto','combustivel','shell','ipiranga','estacionamento','pedagio','metro','mobilidade'),
    'Moradia':('aluguel','condominio','imobiliaria','material de construcao'),
    'Saúde':('farmacia','drogaria','hospital','clinica','laboratorio','medico','dentista'),
    'Educação':('escola','faculdade','curso','livraria','udemy'),
    'Lazer':('cinema','netflix','spotify','steam','playstation','evento','ingresso'),
    'Compras':('amazon','shopee','mercado livre','magalu','magazine luiza','loja','shopping'),
    'Assinaturas':('assinatura','google one','icloud','adobe','microsoft','youtube premium'),
    'Contas':('energia','eletricidade','agua','internet','telefone','claro','vivo','tim','seguro'),
    'Viagem':('hotel','booking','airbnb','latam','gol linhas','azul linhas','passagem'),
    'Presentes':('presente','floricultura'),
}
DATE_HEADERS=('data','date','data da compra','data compra','data de lancamento','data lancamento')
DESC_HEADERS=('descricao','description','titulo','title','estabelecimento','historico','memo','detalhes')
AMOUNT_HEADERS=('valor','amount','valor da compra','valor compra','total')
DEBIT_HEADERS=('debito','debit','valor debito','saidas','saida')
CREDIT_HEADERS=('credito','credit','valor credito','entradas','entrada')
SKIP_TERMS=('total da fatura','saldo anterior','saldo do dia','saldo diario','saldo atual','saldo em conta','saldo disponivel','saldo final','saldo inicial','saldo bloqueado','vencimento da fatura')
INCOME_CATEGORIES=('Salário','Pagamento recebido','Transferência recebida','Reembolso','Rendimentos','Outras entradas')
INCOME_RULES={
    'Salário':('salario','folha de pagamento','pagamento salario','proventos'),
    'Pagamento recebido':('pagamento recebido','recebimento','deposito','credito em conta'),
    'Transferência recebida':('pix recebido','ted recebida','transferencia recebida','doc recebido'),
    'Reembolso':('reembolso','estorno','devolucao'),
    'Rendimentos':('rendimento','juros','dividendo','provento'),
}
TRANSFER_OWN_TERMS=('entre contas','mesma titularidade','transferencia interna','resgate automatico','aplicacao automatica')
FEE_TERMS=('tarifa','taxa bancaria','cesta de servicos','anuidade','encargos')
INTEREST_TERMS=('juros','mora','rotativo','iof')
REFUND_TERMS=('estorno','reembolso','devolucao','credito compra')


def plain(value:str)->str:
    return ''.join(ch for ch in unicodedata.normalize('NFKD',value.lower()) if not unicodedata.combining(ch)).strip()


def parse_date(value:str)->str:
    value=value.strip().split('T')[0]
    for pattern in (r'^(\d{4})-(\d{2})-(\d{2})$',r'^(\d{2})/(\d{2})/(\d{4})$',r'^(\d{2})-(\d{2})-(\d{4})$',r'^(\d{2})/(\d{2})/(\d{2})$'):
        match=re.match(pattern,value)
        if match:
            parts=match.groups();year=('20'+parts[2]) if len(parts[2])==2 else parts[2];iso=value if pattern.startswith('^(\\d{4}') else f'{year}-{parts[1]}-{parts[0]}'
            date.fromisoformat(iso)
            return iso
    raise ValueError('Data inválida')


def parse_amount(value:str)->float:
    marker=plain(value)[-1:] if value.strip() else ''
    cleaned=re.sub(r'[^\d,\.\-()]','',value.strip())
    negative=cleaned.startswith('-') or (cleaned.startswith('(') and cleaned.endswith(')'))
    cleaned=cleaned.strip('-()')
    if ',' in cleaned:cleaned=cleaned.replace('.','').replace(',','.')
    elif cleaned.count('.')>1:cleaned=cleaned.replace('.','')
    amount=round(float(cleaned),2)
    return -amount if negative or marker=='d' else amount


def suggestion(description:str)->tuple[str,float]:
    text=plain(description)
    for category,terms in CATEGORY_RULES.items():
        if any(term in text for term in terms):return category,.92
    return '',0.0


def income_suggestion(description:str)->tuple[str,float]:
    text=plain(description)
    for category,terms in INCOME_RULES.items():
        if any(term in text for term in terms):return category,.94
    return 'Outras entradas',.45


def item(transaction_date:str,description:str,amount:float)->dict|None:
    description=' '.join(description.split()).strip(' -;')[:100]
    if not description or amount==0 or any(term in plain(description) for term in SKIP_TERMS):return None
    expense_category,expense_confidence=suggestion(description)
    income_category,income_confidence=income_suggestion(description)
    is_income=amount>0 and income_confidence>.5
    text=plain(description);flags=[]
    if any(term in text for term in FEE_TERMS):expense_category,expense_confidence='Contas',.9;flags.append('tarifa')
    if any(term in text for term in INTEREST_TERMS):expense_category,expense_confidence='Contas',.9;flags.append('juros')
    if any(term in text for term in REFUND_TERMS):income_category,income_confidence,is_income='Reembolso',.94,True;flags.append('estorno/reembolso')
    installment_match=re.search(r'(?:parc(?:ela)?\s*)?(\d{1,3})\s*(?:/|de)\s*(\d{1,3})',text)
    installment={"number":int(installment_match.group(1)),"count":int(installment_match.group(2))} if installment_match and int(installment_match.group(2))>1 else None
    if installment:flags.append('compra parcelada')
    return {'date':parse_date(transaction_date),'amount':abs(round(amount,2)),'where':description,'kind':'income' if is_income else 'expense','category':income_category if is_income else expense_category,'confidence':income_confidence if is_income else expense_confidence,'payment':'Crédito','description':'','selected':True,'flags':flags,'installment':installment,'needs_review':expense_confidence<.7 if not is_income else income_confidence<.7}


def merchant_key(description:str)->str:
    text=plain(description)
    text=re.sub(r'\b(?:pix|ted|doc|compra|debito|credito|pagamento|parcela|parc)\b',' ',text)
    text=re.sub(r'\b\d{1,3}\s*(?:/|de)\s*\d{1,3}\b|\d+',' ',text)
    return ' '.join(text.split())[:60]


def analyze(items:list[dict],existing_expenses:list[dict]|None=None,income_entries:list[dict]|None=None, rules:dict|None=None)->dict:
    existing_expenses=existing_expenses or [];income_entries=income_entries or []
    existing={(entry['date'],round(float(entry['amount']),2),plain(entry.get('where',''))) for entry in existing_expenses}
    existing_income={(entry['date'],round(float(entry['amount']),2),plain(entry.get('source',''))) for entry in income_entries}
    groups={}
    for entry in items:groups.setdefault(merchant_key(entry['where']),[]).append(entry)
    for entry in items:
        text=plain(entry['where']);entry['duplicate']=(entry['date'],entry['amount'],text) in (existing_income if entry['kind']=='income' else existing)
        if entry['duplicate']:entry['flags'].append('possível duplicidade');entry['needs_review']=True
        if any(term in text for term in TRANSFER_OWN_TERMS):entry.update(kind='transfer',category='Transferência própria',confidence=.96,selected=False,needs_review=True);entry['flags'].append('transferência própria')
        peers=groups.get(merchant_key(entry['where']),[]);months={peer['date'][:7] for peer in peers};amounts=[peer['amount'] for peer in peers]
        if len(months)>=2 and max(amounts)-min(amounts)<=max(1,median(amounts)*.08):
            entry['recurring']=True;entry['flags'].append('recorrente')
            if entry['kind']=='expense' and not entry['category']:entry['category']='Assinaturas';entry['confidence']=max(entry['confidence'],.78)
        else:entry['recurring']=False
        saved=(rules or {}).get(entry['kind']+':'+merchant_key(entry['where'])[:80])
        if saved and entry['kind'] in {'expense','income'}:
            entry['category']=str(saved);entry['confidence']=1;entry['flags'].append('categoria escolhida anteriormente')
    # Pares de mesmo valor e data próxima são candidatos a transferência entre contas próprias.
    for index,left in enumerate(items):
        for right in items[index+1:]:
            if left['kind']==right['kind'] or abs(left['amount']-right['amount'])>.009:continue
            if abs((date.fromisoformat(left['date'])-date.fromisoformat(right['date'])).days)>1:continue
            if any(term in plain(left['where']+' '+right['where']) for term in ('pix','ted','transfer')):
                for entry in (left,right):entry.update(kind='transfer',category='Transferência própria',selected=False,needs_review=True,confidence=.82);entry['flags'].append('possível transferência própria')
    salaries=[entry for entry in items if entry['kind']=='income' and entry['category']=='Salário']
    income_suggestion=None
    if salaries:
        values=[entry['amount'] for entry in salaries];days=[int(entry['date'][8:10]) for entry in salaries];origins=[entry['where'] for entry in salaries]
        typical=round(float(median(values)),2);spread=max(values)-min(values) if len(values)>1 else 0
        income_suggestion={'day':round(float(median(days))), 'amount':typical, 'source':max(set(origins),key=origins.count),
                           'varies':spread>max(1,typical*.03),'samples':len(salaries),'confidence':'alta' if len(salaries)>=2 else 'média',
                           'month':salaries[-1]['date'][:7]}
    recurring=[{'name':key,'kind':entries[0]['kind'],'amount':round(float(median([entry['amount'] for entry in entries])),2),'months':len({entry['date'][:7] for entry in entries})} for key,entries in groups.items() if len({entry['date'][:7] for entry in entries})>=2]
    return {'items':items,'income_suggestion':income_suggestion,'recurring':recurring,'review_count':sum(entry['needs_review'] for entry in items),'duplicates':sum(entry['duplicate'] for entry in items),'transfers':sum(entry['kind']=='transfer' for entry in items)}


def _column(fieldnames:list[str],candidates:tuple[str,...])->str|None:
    normalized={plain(name):name for name in fieldnames if name}
    return next((normalized[name] for name in candidates if name in normalized),None)


def parse_csv(raw:bytes)->list[dict]:
    text=None
    for encoding in ('utf-8-sig','cp1252','latin-1'):
        try:text=raw.decode(encoding);break
        except UnicodeDecodeError:pass
    if not text:raise ValueError('Não foi possível ler o CSV')
    try:dialect=csv.Sniffer().sniff(text[:4096],delimiters=',;\t')
    except csv.Error:dialect=csv.excel
    reader=csv.DictReader(StringIO(text),dialect=dialect)
    fields=reader.fieldnames or []
    date_col=_column(fields,DATE_HEADERS);desc_col=_column(fields,DESC_HEADERS);amount_col=_column(fields,AMOUNT_HEADERS);debit_col=_column(fields,DEBIT_HEADERS);credit_col=_column(fields,CREDIT_HEADERS)
    if not date_col or not desc_col or not (amount_col or debit_col or credit_col):raise ValueError('O CSV precisa ter colunas de data, descrição e valor')
    result=[]
    for row in reader:
        try:
            if amount_col:amount=parse_amount(row.get(amount_col,'') or '')
            elif row.get(debit_col or '','').strip():amount=-abs(parse_amount(row.get(debit_col,'') or ''))
            else:amount=abs(parse_amount(row.get(credit_col or '','') or ''))
            parsed=item(row.get(date_col,'') or '',row.get(desc_col,'') or '',amount)
        except (ValueError,TypeError):continue
        if parsed:
            result.append(parsed)
    return result


def parse_ofx(raw:bytes)->list[dict]:
    text=raw.decode('cp1252',errors='replace')
    result=[]
    for block in re.findall(r'<STMTTRN>(.*?)(?:</STMTTRN>|(?=<STMTTRN>)|</BANKTRANLIST>)',text,re.I|re.S):
        def tag(name):
            match=re.search(fr'<{name}>([^<\r\n]+)',block,re.I);return match.group(1).strip() if match else ''
        try:
            raw_date=tag('DTPOSTED')[:8];transaction_date=f'{raw_date[:4]}-{raw_date[4:6]}-{raw_date[6:8]}'
            description=tag('MEMO') or tag('NAME');parsed=item(transaction_date,description,parse_amount(tag('TRNAMT')))
        except (ValueError,TypeError):continue
        if parsed:
            result.append(parsed)
    return result


def parse_pdf(raw:bytes)->list[dict]:
    try:
        from pypdf import PdfReader
        reader=PdfReader(BytesIO(raw),strict=True)
        if len(reader.pages)>MAX_PDF_PAGES:raise ValueError('O PDF deve ter no máximo 40 páginas')
        parts=[];size=0
        for page in reader.pages:
            content=page.extract_text() or '';size+=len(content)
            if size>MAX_PDF_TEXT:raise ValueError('O conteúdo do PDF é muito grande')
            parts.append(content)
        text='\n'.join(parts)
    except ValueError:raise
    except Exception as exc:raise ValueError('Não foi possível ler este PDF. Tente baixar o extrato em CSV ou OFX.') from exc
    result=[]
    pattern=re.compile(r'(?m)^\s*(\d{2}/\d{2}(?:/\d{2,4})?)\s+(.+?)\s+(?:R\$\s*)?(-?[\d.]+,\d{2})\s*$')
    current_year=date.today().year
    for raw_date,description,raw_amount in pattern.findall(text):
        if len(raw_date)==5:raw_date=f'{raw_date}/{current_year}'
        elif len(raw_date)==8:raw_date=raw_date[:6]+'20'+raw_date[6:]
        try:parsed=item(raw_date,description,parse_amount(raw_amount))
        except ValueError:continue
        if parsed:result.append(parsed)
    return result


def parse_statement(filename:str,raw:bytes)->list[dict]:
    if not raw:raise ValueError('Escolha um arquivo')
    if len(raw)>MAX_FILE_SIZE:raise ValueError('O arquivo deve ter no máximo 6 MB')
    suffix=filename.lower().rsplit('.',1)[-1] if '.' in filename else ''
    parsers={'csv':parse_csv,'ofx':parse_ofx,'pdf':parse_pdf}
    if suffix not in parsers:raise ValueError('Envie um arquivo CSV, OFX ou PDF')
    result=parsers[suffix](raw)[:MAX_ITEMS]
    if not result:raise ValueError('Nenhum lançamento foi identificado no arquivo')
    return result


def commit_items(payload, user_id=None):
    try:from src import runtime_storage as storage, investments
    except ImportError:
        import runtime_storage as storage
        import investments
    if not isinstance(payload,dict):raise ValueError('Dados do extrato inválidos')
    items=payload.get('items',[])
    if not isinstance(items,list) or not items or len(items)>MAX_ITEMS:raise ValueError('Selecione de 1 a 500 lançamentos')
    imported=income_imported=skipped=transfers=0;errors=[];processed=[];learned={}
    for index,entry in enumerate(items):
        if not isinstance(entry,dict) or entry.get('selected') is False:continue
        if entry.get('kind')=='transfer':transfers+=1;processed.append(index);continue
        if entry.get('kind') not in {'income','expense'}:errors.append({'line':index+1,'error':'Escolha entrada, saída ou transferência'});continue
        if not str(entry.get('category','')).strip():errors.append({'line':index+1,'error':'Escolha uma categoria'});continue
        data={'date':entry.get('date'),'amount':entry.get('amount'),'where':entry.get('where'),
              'category':entry.get('category'),'payment':entry.get('payment','Crédito'),'description':entry.get('description','')}
        try:
            if entry['kind']=='income':storage.add_income_entry(data,user_id);income_imported+=1
            else:storage.add_expense(data,user_id);imported+=1
            if payload.get('remember_categories',True) is True:
                learned[entry['kind']+':'+merchant_key(str(entry.get('where','')))[:80]]=entry['category']
            processed.append(index)
        except storage.DuplicateExpenseError:skipped+=1;processed.append(index)
        except (ValueError,TypeError,KeyError) as exc:errors.append({'line':index+1,'error':str(exc)})
    suggestion=payload.get('income_suggestion') if payload.get('confirm_income_suggestion') is True else None
    updated=False
    if isinstance(suggestion,dict):
        current=storage.read_incomes(user_id).get(str(suggestion.get('month','')), {})
        try:
            storage.set_income({'month':suggestion.get('month'),'cash':suggestion.get('amount'),'voucher':current.get('voucher',0),'payday':suggestion.get('day'),'source':suggestion.get('source','')},user_id);updated=True
        except (ValueError,TypeError) as exc:errors.append({'line':0,'error':str(exc)})
    def remember(store):
        prefs=store.setdefault('preferences',{})
        rules=prefs.setdefault('category_rules',{});rules.update(learned)
        for key in list(rules)[:-500]:rules.pop(key,None)
        prefs['last_import']={'date':investments.now_iso(),'expenses':imported,'incomes':income_imported,'duplicates':skipped,'errors':len(errors)}
    investments.mutate_store(remember,user_id)
    return {'ok':not errors,'imported':imported,'income_imported':income_imported,'skipped':skipped,
            'transfers':transfers,'processed':processed,'income_updated':updated,'errors':errors}
