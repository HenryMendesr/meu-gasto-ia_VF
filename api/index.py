"""Aplicação ASGI para Vercel."""

from html import escape
from pathlib import Path
import re

from fastapi import FastAPI, Form, Request
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse

from src import auth, investments, runtime_storage as storage


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "public"
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)


def session(request: Request) -> bool:
    return auth.verify_session(request.cookies.get(auth.COOKIE_NAME))


def json_error(status: int, message: str) -> JSONResponse:
    return JSONResponse({"ok": False, "error": message}, status_code=status, headers={"Cache-Control": "no-store"})


def protected(request: Request):
    return None if session(request) else json_error(401, "Faça login para continuar")


def auth_html(error: str = "") -> HTMLResponse:
    template = (WEB / "auth.html").read_text(encoding="utf-8")
    fields = '<label>Senha<input name="password" type="password" autocomplete="current-password" required autofocus></label>'
    values = {"__TITLE__":"Entrar","__SUBTITLE__":"Acesse seu controle financeiro","__ACTION__":"/login","__FIELDS__":fields,"__BUTTON__":"Entrar","__ERROR__":f'<div class="error">{escape(error)}</div>' if error else ""}
    for key,value in values.items(): template=template.replace(key,value)
    return HTMLResponse(template,headers={"Cache-Control":"no-store"})


@app.get("/")
def home(request: Request):
    if not session(request): return RedirectResponse("/login",303)
    return FileResponse(WEB / "index.html",headers={"Cache-Control":"no-store"})


@app.get("/login")
def login_page(request: Request):
    return RedirectResponse("/",303) if session(request) else auth_html()


@app.post("/login")
def login(password: str = Form(...)):
    if not auth.verify_password(password): return auth_html("Senha incorreta")
    response=RedirectResponse("/",303)
    response.set_cookie(auth.COOKIE_NAME,auth.create_session(),max_age=auth.SESSION_SECONDS,httponly=True,secure=True,samesite="strict",path="/")
    return response


@app.post("/logout")
def logout():
    response=RedirectResponse("/login",303); response.delete_cookie(auth.COOKIE_NAME,path="/"); return response


@app.get("/api/health")
def health(request: Request):
    if denied:=protected(request): return denied
    return {"ok":True,"service":"meu-gasto-ia","database":True,"expenses":len(storage.read_expenses()),"investments":len(investments.portfolio()["investments"])}


@app.get("/api/bootstrap")
def bootstrap(request: Request):
    if denied:=protected(request): return denied
    return {"ok":True,"expenses":storage.read_expenses(),"incomes":storage.read_incomes(),"budgets":storage.read_budgets(),"portfolio":investments.portfolio()}


@app.get("/api/{resource}")
def read_resource(resource: str, request: Request):
    if denied:=protected(request): return denied
    if resource=="expenses": return {"ok":True,"expenses":storage.read_expenses()}
    if resource=="incomes": return {"ok":True,"incomes":storage.read_incomes()}
    if resource=="budgets": return {"ok":True,"budgets":storage.read_budgets()}
    if resource=="investments": return {"ok":True,**investments.portfolio()}
    return json_error(404,"Rota não encontrada")


@app.post("/api/{resource}")
async def create_resource(resource: str, request: Request):
    if denied:=protected(request): return denied
    try:
        payload=await request.json()
        if resource=="expenses": return JSONResponse({"ok":True,**storage.add_expense(payload)},status_code=201)
        if resource=="incomes": return {"ok":True,**storage.set_income(payload)}
        if resource=="budgets": return {"ok":True,**storage.set_budget(payload)}
        if resource=="investments": return JSONResponse({"ok":True,"investment":investments.create_investment(payload)},status_code=201)
        return json_error(404,"Rota não encontrada")
    except storage.DuplicateExpenseError as exc: return JSONResponse({"ok":False,"code":"duplicate","error":str(exc)},status_code=409)
    except (ValueError,KeyError) as exc: return json_error(400,str(exc).strip("'"))


@app.post("/api/investments/refresh")
def refresh(request: Request):
    if denied:=protected(request): return denied
    try: return {"ok":True,**investments.refresh_investments()}
    except ValueError as exc: return json_error(400,str(exc))


@app.post("/api/investments/extract-image")
async def extract_image(request: Request):
    if denied:=protected(request): return denied
    try: return {"ok":True,**investments.extract_image(str((await request.json()).get("image","")))}
    except ValueError as exc: return json_error(400,str(exc))


@app.put("/api/investments/{item_id}")
async def update_investment(item_id: str, request: Request):
    if denied:=protected(request): return denied
    if not re.fullmatch(r"[a-f0-9]{32}",item_id): return json_error(404,"Investimento não encontrado")
    try: return {"ok":True,"investment":investments.update_investment(item_id,await request.json())}
    except KeyError as exc: return json_error(404,str(exc).strip("'"))
    except ValueError as exc: return json_error(400,str(exc))


@app.delete("/api/investments/{item_id}")
def remove_investment(item_id: str, request: Request):
    if denied:=protected(request): return denied
    try: investments.delete_investment(item_id); return {"ok":True}
    except KeyError as exc: return json_error(404,str(exc).strip("'"))
