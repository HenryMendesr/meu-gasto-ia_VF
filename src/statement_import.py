"""Leitura segura de extratos para revisão antes do lançamento."""
from __future__ import annotations

import csv
from datetime import date
from io import BytesIO, StringIO
import re
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
DEBIT_HEADERS=('debito','debit','valor debito')
SKIP_TERMS=('total da fatura','pagamento recebido','saldo anterior','limite disponivel','vencimento da fatura')


def plain(value:str)->str:
    return ''.join(ch for ch in unicodedata.normalize('NFKD',value.lower()) if not unicodedata.combining(ch)).strip()


def parse_date(value:str)->str:
    value=value.strip().split('T')[0]
    for pattern in (r'^(\d{4})-(\d{2})-(\d{2})$',r'^(\d{2})/(\d{2})/(\d{4})$',r'^(\d{2})-(\d{2})-(\d{4})$'):
        match=re.match(pattern,value)
        if match:
            parts=match.groups();iso=value if pattern.startswith('^(\\d{4}') else f'{parts[2]}-{parts[1]}-{parts[0]}'
            date.fromisoformat(iso)
            return iso
    raise ValueError('Data inválida')


def parse_amount(value:str)->float:
    cleaned=re.sub(r'[^\d,\.\-()]','',value.strip())
    negative=cleaned.startswith('-') or (cleaned.startswith('(') and cleaned.endswith(')'))
    cleaned=cleaned.strip('-()')
    if ',' in cleaned:cleaned=cleaned.replace('.','').replace(',','.')
    elif cleaned.count('.')>1:cleaned=cleaned.replace('.','')
    amount=round(float(cleaned),2)
    return -amount if negative else amount


def suggestion(description:str)->tuple[str,float]:
    text=plain(description)
    for category,terms in CATEGORY_RULES.items():
        if any(term in text for term in terms):return category,.92
    return '',0.0


def item(transaction_date:str,description:str,amount:float)->dict|None:
    description=' '.join(description.split()).strip(' -;')[:100]
    if not description or amount==0 or any(term in plain(description) for term in SKIP_TERMS):return None
    category,confidence=suggestion(description)
    return {'date':parse_date(transaction_date),'amount':abs(round(amount,2)),'where':description,'category':category,'confidence':confidence,'payment':'Crédito','description':'','selected':amount>0}


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
    date_col=_column(fields,DATE_HEADERS);desc_col=_column(fields,DESC_HEADERS);amount_col=_column(fields,AMOUNT_HEADERS) or _column(fields,DEBIT_HEADERS)
    if not all((date_col,desc_col,amount_col)):raise ValueError('O CSV precisa ter colunas de data, descrição e valor')
    result=[]
    for row in reader:
        try:parsed=item(row.get(date_col,'') or '',row.get(desc_col,'') or '',parse_amount(row.get(amount_col,'') or ''))
        except (ValueError,TypeError):continue
        if parsed:
            # Bancos divergem no sinal usado para compras em CSV; a revisão permite desmarcar estornos.
            parsed['selected']=True
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
            parsed['selected']=tag('TRNAMT').strip().startswith('-')
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
    if not result:raise ValueError('Nenhum gasto foi identificado no arquivo')
    return result
