"""Aplicação ASGI multiusuário para Vercel."""
from html import escape
from datetime import datetime, timedelta, timezone
import os
from pathlib import Path
import re
from threading import Lock
import time
from urllib.parse import urlsplit

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from src import auth, investments, runtime_storage as storage, statement_import

ROOT=Path(__file__).resolve().parents[1]
TEMPLATES=ROOT/'templates'
MULTI_USER=bool(os.environ.get('DATABASE_URL'))
_AUTH_ATTEMPTS:dict[str,list[float]]={}
_AUTH_LOCK=Lock()
_AUTH_WINDOW_SECONDS=15*60
_AUTH_MAX_ATTEMPTS=8


fastapi_app=FastAPI(docs_url=None,redoc_url=None,openapi_url=None)
app=fastapi_app


@fastapi_app.middleware('http')
async def reject_cross_site_writes(request:Request,call_next):
    """Bloqueia CSRF sem expor um token ao JavaScript da aplicação."""
    if request.method not in {'GET','HEAD','OPTIONS'}:
        fetch_site=request.headers.get('sec-fetch-site','').lower()
        if fetch_site=='cross-site':
            return json_error(403,'Origem da requisição não permitida')
        origin=request.headers.get('origin')
        # Navegadores modernos informam a relação real entre a página e a
        # requisição. Na Vercel, Host/Origin podem apontar para aliases distintos.
        if origin and not fetch_site:
            parsed=urlsplit(origin)
            public_hosts={request.headers.get('host','').lower()}
            public_hosts.update(host.strip().lower() for host in request.headers.get('x-forwarded-host','').split(',') if host.strip())
            if parsed.scheme not in {'http','https'} or parsed.netloc.lower() not in public_hosts:
                return json_error(403,'Origem da requisição não permitida')
        content_length=request.headers.get('content-length')
        if content_length and content_length.isdigit() and int(content_length)>9_000_000:
            return json_error(413,'Arquivo ou requisição muito grande')
    return await call_next(request)


def current_user_id(request:Request)->int|None:return auth.session_user(request.cookies.get(auth.COOKIE_NAME))
def json_error(status:int,message:str)->JSONResponse:return JSONResponse({'ok':False,'error':message},status_code=status,headers={'Cache-Control':'no-store'})
def protected(request:Request):
    user_id=current_user_id(request)
    return user_id if user_id is not None else json_error(401,'Faça login para continuar')

def auth_attempt_key(request:Request,identity:str)->str:
    forwarded=request.headers.get('x-forwarded-for','').split(',')[0].strip()
    address=forwarded or (request.client.host if request.client else 'unknown')
    return f'{address}:{identity.strip().lower()[:254]}'

def auth_is_limited(key:str)->bool:
    cutoff=time.monotonic()-_AUTH_WINDOW_SECONDS
    with _AUTH_LOCK:
        recent=[stamp for stamp in _AUTH_ATTEMPTS.get(key,[]) if stamp>cutoff]
        if recent:_AUTH_ATTEMPTS[key]=recent
        else:_AUTH_ATTEMPTS.pop(key,None)
        return len(recent)>=_AUTH_MAX_ATTEMPTS

def auth_record_failure(key:str)->None:
    with _AUTH_LOCK:
        if len(_AUTH_ATTEMPTS)>5_000:
            cutoff=time.monotonic()-_AUTH_WINDOW_SECONDS
            stale=[item for item,attempts in _AUTH_ATTEMPTS.items() if not attempts or attempts[-1]<=cutoff]
            for item in stale:_AUTH_ATTEMPTS.pop(item,None)
        _AUTH_ATTEMPTS.setdefault(key,[]).append(time.monotonic())

def auth_clear_failures(key:str)->None:
    with _AUTH_LOCK:_AUTH_ATTEMPTS.pop(key,None)

def auth_html(*,register:bool=False,error:str='')->HTMLResponse:
    template=(TEMPLATES/'auth.html').read_text(encoding='utf-8')
    if register:
        fields=''.join([
            '<label>Nome<input name="name" maxlength="80" autocomplete="name" required autofocus></label>',
            '<label>E-mail<input name="email" type="email" maxlength="254" autocomplete="email" required></label>',
            '<label>Senha<input name="password" type="password" minlength="10" maxlength="200" autocomplete="new-password" required></label>',
            '<label>Código de convite<input name="invitation_code" type="password" maxlength="200" autocomplete="off" required></label>',
        ])
        values={'__TITLE__':'Criar conta','__SUBTITLE__':'Seus dados serão privados e separados','__ACTION__':'/register','__FIELDS__':fields,'__BUTTON__':'Criar minha conta','__FOOTER__':'Já possui uma conta? <a href="/login">Entrar</a>'}
    else:
        email='<label>E-mail<input id="username" name="email" type="email" inputmode="email" maxlength="254" autocomplete="username" required autofocus></label>' if MULTI_USER else ''
        fields=email+'<label>Senha<input id="password" name="password" type="password" autocomplete="current-password" required></label><label class="remember-access"><input name="remember" type="checkbox" value="1" checked><span><strong>Continuar conectado</strong><small>Manter esta conta aberta por 30 dias neste aparelho</small></span></label><div class="password-manager-hint">Para preencher a senha automaticamente, aceite a opção “Salvar senha” oferecida pelo navegador.</div>'
        footer='<a href="/register">Criar uma conta com convite</a>' if MULTI_USER else ''
        values={'__TITLE__':'Entrar','__SUBTITLE__':'Acesse seu controle financeiro','__ACTION__':'/login','__FIELDS__':fields,'__BUTTON__':'Entrar','__FOOTER__':footer}
    values['__ERROR__']=f'<div class="error">{escape(error)}</div>' if error else ''
    for key,value in values.items():template=template.replace(key,value)
    return HTMLResponse(template,headers={'Cache-Control':'no-store'})

def set_session(response:RedirectResponse,user_id:int,persistent:bool=True)->RedirectResponse:
    cookie_options={'max_age':auth.SESSION_SECONDS,'expires':datetime.now(timezone.utc)+timedelta(seconds=auth.SESSION_SECONDS)} if persistent else {}
    response.set_cookie(auth.COOKIE_NAME,auth.create_session(user_id),httponly=True,secure=True,samesite='strict',path='/',**cookie_options)
    return response

@fastapi_app.get('/')
def home(request:Request):return FileResponse(TEMPLATES/'index.html',headers={'Cache-Control':'no-store'}) if current_user_id(request) else RedirectResponse('/login',303)
@fastapi_app.get('/login')
def login_page(request:Request):return RedirectResponse('/',303) if current_user_id(request) else auth_html()
@fastapi_app.post('/login')
def login(request:Request,password:str=Form(...),email:str=Form(''),remember:str=Form('')):
    key=auth_attempt_key(request,email or 'legacy')
    if auth_is_limited(key):return auth_html(error='Muitas tentativas. Aguarde 15 minutos e tente novamente')
    if MULTI_USER:
        user=storage.authenticate_user(email,password)
        if not user:auth_record_failure(key);return auth_html(error='E-mail ou senha incorretos')
        auth_clear_failures(key)
        return set_session(RedirectResponse('/',303),user['id'],persistent=remember=='1')
    if not auth.verify_password(password):auth_record_failure(key);return auth_html(error='Senha incorreta')
    auth_clear_failures(key)
    return set_session(RedirectResponse('/',303),1,persistent=remember=='1')
@fastapi_app.get('/register')
def register_page(request:Request):
    if not MULTI_USER:return RedirectResponse('/login',303)
    return RedirectResponse('/',303) if current_user_id(request) else auth_html(register=True)
@fastapi_app.post('/register')
def register(request:Request,name:str=Form(...),email:str=Form(...),password:str=Form(...),invitation_code:str=Form(...)):
    if not MULTI_USER:return RedirectResponse('/login',303)
    key=auth_attempt_key(request,'register')
    if auth_is_limited(key):return auth_html(register=True,error='Muitas tentativas. Aguarde 15 minutos e tente novamente')
    try:user=storage.register_user(name,email,password,invitation_code)
    except ValueError as exc:auth_record_failure(key);return auth_html(register=True,error=str(exc))
    auth_clear_failures(key)
    return set_session(RedirectResponse('/',303),user['id'])
@fastapi_app.post('/logout')
def logout():
    response=RedirectResponse('/login',303);response.delete_cookie(auth.COOKIE_NAME,path='/');return response

@fastapi_app.get('/api/health')
def health(request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    return {'ok':True,'service':'minha-carteira','database':True,'expenses':len(storage.read_expenses(uid)),'investments':len(investments.portfolio(uid)['investments'])}
@fastapi_app.get('/api/bootstrap')
def bootstrap(request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    user=storage.get_user(uid) if MULTI_USER else {'id':1,'name':'Você','email':''}
    return {'ok':True,'user':user,'expenses':storage.read_expenses(uid),'incomes':storage.read_incomes(uid),'budgets':storage.read_budgets(uid),'categories':storage.read_categories(uid),'portfolio':investments.portfolio(uid)}
@fastapi_app.get('/api/{resource}')
def read_resource(resource:str,request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    if resource=='expenses':return {'ok':True,'expenses':storage.read_expenses(uid)}
    if resource=='incomes':return {'ok':True,'incomes':storage.read_incomes(uid)}
    if resource=='budgets':return {'ok':True,'budgets':storage.read_budgets(uid)}
    if resource=='categories':return {'ok':True,'categories':storage.read_categories(uid)}
    if resource=='investments':return {'ok':True,**investments.portfolio(uid)}
    return json_error(404,'Rota não encontrada')
@fastapi_app.post('/api/{resource}')
async def create_resource(resource:str,request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    try:
        payload=await request.json()
        if resource=='expenses':return JSONResponse({'ok':True,**storage.add_expense(payload,uid)},status_code=201)
        if resource=='incomes':return {'ok':True,**storage.set_income(payload,uid)}
        if resource=='budgets':return {'ok':True,**storage.set_budget(payload,uid)}
        if resource=='categories':return JSONResponse({'ok':True,'category':storage.add_category(payload.get('name',''),uid)},status_code=201)
        if resource=='investments':return JSONResponse({'ok':True,'investment':investments.create_investment(payload,uid)},status_code=201)
        return json_error(404,'Rota não encontrada')
    except storage.DuplicateExpenseError as exc:return JSONResponse({'ok':False,'code':'duplicate','error':str(exc)},status_code=409)
    except (ValueError,KeyError) as exc:return json_error(400,str(exc).strip("'"))
@fastapi_app.post('/api/investments/refresh')
def refresh(request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    try:return {'ok':True,**investments.refresh_investments(user_id=uid)}
    except ValueError as exc:return json_error(400,str(exc))
@fastapi_app.post('/api/investments/extract-image')
async def extract_image(request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    try:return {'ok':True,**investments.extract_image(str((await request.json()).get('image','')))}
    except ValueError as exc:return json_error(400,str(exc))

@fastapi_app.get('/api/investments/{item_id}/history')
def investment_history(item_id:str,request:Request,period:str='1y'):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    if not re.fullmatch(r'[a-f0-9]{32}',item_id):return json_error(404,'Investimento não encontrado')
    try:return {'ok':True,**investments.investment_history(item_id,period,uid)}
    except KeyError as exc:return json_error(404,str(exc).strip("'"))
    except ValueError as exc:return json_error(400,str(exc))

@fastapi_app.post('/api/statements/preview')
async def preview_statement(request:Request,file:UploadFile=File(...)):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    try:
        raw=await file.read(statement_import.MAX_FILE_SIZE+1)
        items=statement_import.parse_statement(file.filename or '',raw)
        return {'ok':True,'items':items,'count':len(items),'needs_review':sum(not item['category'] for item in items)}
    except ValueError as exc:return json_error(400,str(exc))

@fastapi_app.post('/api/statements/import')
async def import_statement(request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    try:payload=await request.json();items=payload.get('items',[])
    except (ValueError,TypeError):return json_error(400,'Dados do extrato inválidos')
    if not isinstance(items,list) or not items or len(items)>statement_import.MAX_ITEMS:return json_error(400,'Selecione de 1 a 500 lançamentos')
    imported=skipped=0;errors=[]
    for position,item in enumerate(items,1):
        if not isinstance(item,dict) or item.get('selected') is False:continue
        if not str(item.get('category','')).strip():errors.append({'line':position,'error':'Escolha uma categoria'});continue
        expense={'date':item.get('date'),'amount':item.get('amount'),'where':item.get('where'),'category':item.get('category'),'payment':item.get('payment','Crédito'),'description':item.get('description','')}
        try:storage.add_expense(expense,uid);imported+=1
        except storage.DuplicateExpenseError:skipped+=1
        except ValueError as exc:errors.append({'line':position,'error':str(exc)})
    return {'ok':not errors,'imported':imported,'skipped':skipped,'errors':errors}
@fastapi_app.put('/api/investments/{item_id}')
async def update_investment(item_id:str,request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    if not re.fullmatch(r'[a-f0-9]{32}',item_id):return json_error(404,'Investimento não encontrado')
    try:return {'ok':True,'investment':investments.update_investment(item_id,await request.json(),uid)}
    except KeyError as exc:return json_error(404,str(exc).strip("'"))
    except ValueError as exc:return json_error(400,str(exc))
@fastapi_app.delete('/api/investments/{item_id}')
def remove_investment(item_id:str,request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    try:investments.delete_investment(item_id,uid);return {'ok':True}
    except KeyError as exc:return json_error(404,str(exc).strip("'"))

@fastapi_app.put('/api/expenses/{item_id}')
async def update_expense(item_id:int,request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    try:return {'ok':True,**storage.update_expense(item_id,await request.json(),uid)}
    except KeyError as exc:return json_error(404,str(exc).strip("'"))
    except ValueError as exc:return json_error(400,str(exc))

@fastapi_app.delete('/api/expenses/{item_id}')
def remove_expense(item_id:int,request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    try:storage.delete_expense(item_id,uid);return {'ok':True}
    except KeyError as exc:return json_error(404,str(exc).strip("'"))

@fastapi_app.delete('/api/budgets/{month}/{category}')
def remove_budget(month:str,category:str,request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    try:storage.delete_budget(month,category,uid);return {'ok':True}
    except ValueError as exc:return json_error(400,str(exc))

@fastapi_app.delete('/api/categories/{category}')
def remove_category(category:str,request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    try:storage.delete_category(category,uid);return {'ok':True}
    except ValueError as exc:return json_error(400,str(exc))

@fastapi_app.put('/api/categories/{category}')
async def rename_category(category:str,request:Request):
    uid=protected(request)
    if isinstance(uid,JSONResponse):return uid
    try:return {'ok':True,'category':storage.rename_category(category,(await request.json()).get('name',''),uid)}
    except KeyError as exc:return json_error(404,str(exc).strip("'"))
    except ValueError as exc:return json_error(400,str(exc))
