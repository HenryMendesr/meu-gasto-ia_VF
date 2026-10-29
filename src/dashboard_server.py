"""Servidor local autenticado do Minha Carteira."""

from argparse import ArgumentParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from html import escape
from email import policy
from email.parser import BytesParser
import json
from pathlib import Path
import re
import subprocess
import sys
from threading import Timer
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

try:
    from src import auth, investments, runtime_storage as storage, statement_import, planning, trust, account_service, account_security, recurring, cards, bank_accounts
except ImportError:  # execução direta: python src/dashboard_server.py
    import auth, investments, runtime_storage as storage, statement_import, planning, trust, account_service, account_security, recurring, cards, bank_accounts


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "public"
TEMPLATES = ROOT / "templates"
BUILD_DASHBOARD = ROOT / "src/build_dashboard.py"
read_expenses = storage.read_expenses
read_incomes = storage.read_incomes
read_budgets = storage.read_budgets
add_expense = storage.add_expense
set_income = storage.set_income
set_budget = storage.set_budget
DuplicateExpenseError = storage.DuplicateExpenseError


def rebuild_dashboard() -> None:
    subprocess.run([sys.executable, str(BUILD_DASHBOARD)], cwd=ROOT, check=True)


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def end_headers(self) -> None:
        self.send_header("X-Content-Type-Options", "nosniff")
        self.send_header("X-Frame-Options", "DENY")
        self.send_header("Referrer-Policy", "no-referrer")
        self.send_header("Permissions-Policy", "camera=(), microphone=(), geolocation=()")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self' 'unsafe-inline'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; connect-src 'self'; object-src 'none'; base-uri 'none'; frame-ancestors 'none'; form-action 'self'")
        super().end_headers()

    def session_token(self) -> str | None:
        cookie = SimpleCookie(self.headers.get("Cookie", ""))
        value = cookie.get(auth.COOKIE_NAME)
        return value.value if value else None

    def authenticated(self) -> bool:
        return auth.verify_session(self.session_token())

    def secure_cookie(self) -> bool:
        host = self.headers.get("Host", "").split(":", 1)[0]
        return self.headers.get("X-Forwarded-Proto") == "https" or host not in {"127.0.0.1", "localhost", "::1"}

    def set_session_cookie(self, token: str) -> None:
        secure = "; Secure" if self.secure_cookie() else ""
        self.send_header("Set-Cookie", f"{auth.COOKIE_NAME}={token}; Path=/; HttpOnly; SameSite=Strict; Max-Age={auth.SESSION_SECONDS}{secure}")

    def clear_session_cookie(self) -> None:
        secure = "; Secure" if self.secure_cookie() else ""
        self.send_header("Set-Cookie", f"{auth.COOKIE_NAME}=; Path=/; HttpOnly; SameSite=Strict; Max-Age=0{secure}")

    def redirect(self, location: str, token: str | None = None, clear: bool = False) -> None:
        self.send_response(303)
        if token:
            self.set_session_cookie(token)
        if clear:
            self.clear_session_cookie()
        self.send_header("Location", location)
        self.send_header("Cache-Control", "no-store")
        self.end_headers()

    def auth_page(self, setup: bool, error: str = "") -> None:
        template = (TEMPLATES / "auth.html").read_text(encoding="utf-8")
        if setup:
            fields = '<label>Crie sua senha<input name="password" type="password" minlength="10" autocomplete="new-password" required></label><label>Confirme a senha<input name="confirmation" type="password" minlength="10" autocomplete="new-password" required></label>'
            values = {"__TITLE__": "Primeiro acesso", "__SUBTITLE__": "Proteja seus dados com uma senha", "__ACTION__": "/setup", "__FIELDS__": fields, "__BUTTON__": "Criar acesso", "__FOOTER__": ""}
        else:
            fields = '<label>Senha<input name="password" type="password" autocomplete="current-password" required autofocus></label>'
            values = {"__TITLE__": "Entrar", "__SUBTITLE__": "Acesse seu controle financeiro", "__ACTION__": "/login", "__FIELDS__": fields, "__BUTTON__": "Entrar", "__FOOTER__": '<a href="/recover">Recuperar acesso com código</a>'}
        values["__ERROR__"] = f'<div class="error">{escape(error)}</div>' if error else ""
        for key, value in values.items():
            template = template.replace(key, value)
        body = template.encode("utf-8")
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def recovery_page(self, error=""):
        template=(TEMPLATES / "auth.html").read_text(encoding="utf-8")
        values={"__TITLE__":"Recuperar acesso","__SUBTITLE__":"Use um dos códigos que você guardou fora do app", "__ACTION__":"/recover", "__FIELDS__":'<label>Código de recuperação<input name="code" autocomplete="off" required></label><label>Nova senha<input name="password" type="password" minlength="10" maxlength="200" autocomplete="new-password" required></label><label>Confirme a senha<input name="confirmation" type="password" minlength="10" maxlength="200" autocomplete="new-password" required></label>', "__BUTTON__":"Alterar senha", "__FOOTER__":'<a href="/login">Voltar para entrar</a>', "__ERROR__":f'<div class="error">{escape(error)}</div>' if error else ''}
        for key,value in values.items():template=template.replace(key,value)
        body=template.encode();self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(body)));self.send_header("Cache-Control","no-store");self.end_headers();self.wfile.write(body)

    def require_auth(self) -> bool:
        if self.authenticated():
            return True
        if urlparse(self.path).path.startswith("/api/"):
            self.respond(401, {"ok": False, "error": "Faça login para continuar"})
        else:
            self.redirect("/setup" if not auth.configured() else "/login")
        return False

    def valid_request_origin(self) -> bool:
        fetch_site = self.headers.get("Sec-Fetch-Site")
        return fetch_site in (None, "same-origin", "none")

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path in {"/manifest.webmanifest", "/service-worker.js", "/offline.html"} or path.startswith("/icons/") or path == "/app.css":
            super().do_GET()
            return
        if path == "/recover":
            self.recovery_page();return
        if path == "/setup":
            if auth.configured():
                self.redirect("/login")
            else:
                self.auth_page(True)
            return
        if path == "/login":
            if self.authenticated():
                self.redirect("/")
            else:
                self.auth_page(False)
            return
        if not self.require_auth():
            return
        if path == "/":
            body = (TEMPLATES / "index.html").read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return
        if path=="/api/cards":
            try:self.respond(200,{"ok":True,**cards.status(parse_qs(urlparse(self.path).query).get("month",[""])[0])})
            except ValueError as exc:self.respond(400,{"error":str(exc)})
            return
        if path=="/api/recurring":
            try:self.respond(200,{"ok":True,**recurring.status(parse_qs(urlparse(self.path).query).get("month",[""])[0])})
            except ValueError as exc:self.respond(400,{"error":str(exc)})
            return
        if path=="/api/bank-accounts":
            self.respond(200,{"ok":True,**bank_accounts.status()})
            return
        if path in {"/api/insights","/api/account/status","/api/account/export","/api/account/previous-backup","/api/support/status"}:
            try:
                if path=="/api/insights":result=trust.insights(parse_qs(urlparse(self.path).query).get("month",[""])[0])
                elif path=="/api/account/status":result=account_service.status()
                elif path=="/api/account/export":result=storage.export_financial_data()
                elif path=="/api/account/previous-backup":
                    result=storage.previous_financial_backup()
                    if not result:self.respond(404,{"error":"Nenhuma cópia anterior disponível"});return
                else:result=account_service.diagnostic()
                self.respond(200,result)
            except ValueError as exc:self.respond(400,{"error":str(exc)})
            return
        if path == "/api/health":
            self.respond(200, {
                "ok": True,
                "service": "minha-carteira",
                "database": storage.DATABASE.is_file(),
                "expenses": len(read_expenses()),
                "investments": len(investments.portfolio()["investments"]),
            })
            return
        if path == "/api/bootstrap":
            recurring.process_due()
            self.respond(200, {"ok": True, "expenses": cards.planned_expenses(read_expenses(),investments.load_store().get("preferences",{})), "incomes": read_incomes(), "income_entries": storage.read_income_entries(), "budgets": read_budgets(), "categories": storage.read_categories(), "portfolio": investments.portfolio()})
            return
        if path == "/api/expenses":
            self.respond(200, {"ok": True, "expenses": read_expenses()})
            return
        if path == "/api/incomes":
            self.respond(200, {"ok": True, "incomes": read_incomes()})
            return
        if path == "/api/budgets":
            self.respond(200, {"ok": True, "budgets": read_budgets()})
            return
        if path == "/api/categories":
            self.respond(200, {"ok": True, "categories": storage.read_categories()})
            return
        if path == "/api/reports/monthly":
            try:self.respond(200, {"ok": True, **planning.monthly_report(parse_qs(urlparse(self.path).query).get("month", [""])[0])})
            except ValueError as exc:self.respond(400, {"ok": False, "error": str(exc)})
            return
        history_match = re.fullmatch(r"/api/investments/([a-f0-9]{32})/history", path)
        if history_match:
            try:self.respond(200, {"ok": True, **investments.investment_history(history_match.group(1), parse_qs(urlparse(self.path).query).get("period", ["3m"])[0])})
            except (ValueError, KeyError) as exc:self.respond(400, {"ok": False, "error": str(exc)})
            return
        if path == "/api/investments":
            self.respond(200, {"ok": True, **investments.portfolio()})
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path == "/recover":
            if not self.valid_request_origin():self.send_error(403);return
            values=parse_qs(self.rfile.read(min(int(self.headers.get("Content-Length","0")),4096)).decode())
            try:
                if values.get("password",[""])[0]!=values.get("confirmation",[""])[0]:raise ValueError("As senhas não coincidem")
                account_security.recover('',values.get("code",[""])[0],values.get("password",[""])[0]);self.redirect("/login",clear=True)
            except ValueError as exc:self.recovery_page(str(exc))
            return
        if path in {"/setup", "/login"}:
            if not self.valid_request_origin():
                self.send_error(403)
                return
            length = int(self.headers.get("Content-Length", "0"))
            values = parse_qs(self.rfile.read(min(length, 4096)).decode("utf-8"))
            password = values.get("password", [""])[0]
            if path == "/setup":
                try:
                    auth.setup(password, values.get("confirmation", [""])[0])
                    self.redirect("/", auth.create_session())
                except ValueError as exc:
                    self.auth_page(True, str(exc))
            elif auth.verify_password(password):
                self.redirect("/", auth.create_session())
            else:
                self.auth_page(False, "Senha incorreta")
            return
        if path == "/logout":
            self.redirect("/login", clear=True)
            return
        if not self.valid_request_origin():
            self.respond(403, {"ok": False, "error": "Origem não autorizada"})
            return
        if not self.require_auth():
            return
        operation_match=re.fullmatch(r"/api/investments/([a-f0-9]{32})/operations/((?:initial-)?[a-f0-9]{32})/(preview|confirm)",path)
        extra_path=path in {"/api/preferences","/api/product/events","/api/product/feedback","/api/investments/reconcile"} or path.startswith('/api/account/') or path.startswith('/api/recurring/') or path.startswith('/api/cards/') or path.startswith('/api/bank-accounts/') or bool(re.fullmatch(r'/api/investments/[a-f0-9]{32}/redemptions',path))
        sale_match = re.fullmatch(r"/api/investments/([a-f0-9]{32})/sales", path)
        buy_match = re.fullmatch(r"/api/investments/([a-f0-9]{32})/buys", path)
        income_match = re.fullmatch(r"/api/investments/([a-f0-9]{32})/incomes", path)
        payment_match = re.fullmatch(r"/api/debts/(\d+)/payment", path)
        if not (sale_match or buy_match or income_match or payment_match or operation_match or extra_path) and path not in {"/api/expenses", "/api/goals", "/api/incomes", "/api/budgets", "/api/categories", "/api/investments", "/api/investments/cash", "/api/investments/refresh", "/api/investments/extract-image", "/api/statements/preview", "/api/statements/import"}:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            maximum = 3_100_000 if path.startswith("/api/account/") else statement_import.MAX_FILE_SIZE+200_000 if path == "/api/statements/preview" else 12_000_000 if path == "/api/investments/extract-image" else 2_000_000 if path == "/api/statements/import" else 65_536
            if length <= 0 or length > maximum:
                raise ValueError("Requisição inválida")
            raw_body = self.rfile.read(length)
            if path == "/api/statements/preview":
                header = f"Content-Type: {self.headers.get('Content-Type','')}\r\nMIME-Version: 1.0\r\n\r\n".encode()
                message = BytesParser(policy=policy.default).parsebytes(header + raw_body)
                file_part = next((part for part in message.iter_parts() if part.get_filename()), None)
                if not file_part: raise ValueError("Escolha um arquivo")
                items = statement_import.parse_statement(file_part.get_filename() or "", file_part.get_payload(decode=True) or b"")
                analysis = statement_import.analyze(items, read_expenses(), storage.read_income_entries(), investments.load_store().get("preferences",{}).get("category_rules",{}))
                self.respond(200, {"ok": True, **analysis, "count": len(items), "needs_review": sum(not item["category"] or item.get("needs_review") for item in items)})
                return
            payload = json.loads(raw_body)
            if operation_match or extra_path:
                if operation_match:result=trust.operation_change(operation_match.group(1),operation_match.group(2),payload,preview=operation_match.group(3)=='preview')
                elif path=='/api/cards/purchase':result={'purchase':cards.purchase(payload)}
                elif path=='/api/cards/purchase-delete':result=cards.delete_purchase(str(payload.get('id','')))
                elif path.startswith('/api/bank-accounts/'):result=bank_accounts.action(path.rsplit('/',1)[1],payload)
                elif path.endswith('/redemptions'):result={'redemption':(investments.reverse_redemption if payload.get('action')=='reverse' else investments.redeem_fixed)(path.split('/')[3],payload)}
                elif path=='/api/cards/refund-reverse':result={'refund':cards.reverse_refund(payload)}
                elif path=='/api/cards/refund':result={'refund':cards.refund(payload)}
                elif path=='/api/cards/review':result={'review':cards.review(payload)}
                elif path=='/api/cards/pay':result={'payment':cards.pay(payload)}
                elif path=='/api/cards/payment-reverse':result={'payment':cards.reverse_payment(str(payload.get('id','')))}
                elif path=='/api/recurring/salary':result=recurring.save_plan(payload)
                elif path=='/api/recurring/card':result={'card':recurring.save_card(payload)}
                elif path=='/api/recurring/card-delete':result=recurring.delete_card(str(payload.get('id','')))
                elif path=='/api/recurring/receipt':result={'receipt':recurring.receipt_action(str(payload.get('key','')),payload)}
                elif path=='/api/preferences':result={'preferences':trust.preferences(payload)}
                elif path=='/api/product/events':result=trust.usage_event(payload)
                elif path=='/api/product/feedback':result=trust.feedback(payload)
                elif path=='/api/investments/reconcile':result=trust.reconcile_cash(payload)
                elif path=='/api/account/restore-preview':result=account_service.preview_restore(payload)
                elif path=='/api/account/restore':result=account_service.restore(payload)
                elif path=='/api/account/delete':
                    result=account_service.delete(payload)
                elif path=='/api/account/recovery-codes':result={'codes':account_security.generate_codes(payload.get('password'))}
                elif path=='/api/account/password':
                    account_security.change_password(payload.get('current_password'),payload.get('new_password'))
                    self.send_response(200);self.set_session_cookie(auth.create_session());self.send_header('Content-Type','application/json');self.end_headers();self.wfile.write(b'{"ok":true}');return
                else:self.send_error(404);return
                self.respond(200,{'ok':True,**result});return
            if path == "/api/goals":
                result = planning.save_goal(payload)
                self.respond(200, {"ok": True, "goal": result})
                return
            if buy_match or income_match or payment_match:
                result = investments.add_buy(buy_match.group(1), payload) if buy_match else investments.add_investment_income(income_match.group(1), payload) if income_match else storage.set_debt_payment(int(payment_match.group(1)), payload)
                rebuild_dashboard()
                self.respond(200, {"ok": True, **result})
                return
            if sale_match:
                result = investments.sell_investment(sale_match.group(1), payload)
                rebuild_dashboard()
                self.respond(201, {"ok": True, **result})
                return
            if path == "/api/statements/import":
                result=statement_import.commit_items(payload)
                rebuild_dashboard();self.respond(200,result);return
            if path == "/api/incomes":
                result = set_income(payload)
                rebuild_dashboard()
                self.respond(200, {"ok": True, **result})
                return
            if path == "/api/budgets":
                result = set_budget(payload)
                rebuild_dashboard()
                self.respond(200, {"ok": True, **result})
                return
            if path == "/api/categories":
                name = storage.add_category(payload.get("name", ""))
                rebuild_dashboard()
                self.respond(201, {"ok": True, "category": name})
                return
            if path == "/api/investments":
                item = investments.create_investment(payload)
                rebuild_dashboard()
                self.respond(201, {"ok": True, "investment": item})
                return
            if path == "/api/investments/cash":
                result = investments.set_cash_balance(payload)
                rebuild_dashboard()
                self.respond(200, {"ok": True, **result})
                return
            if path == "/api/investments/refresh":
                result = investments.refresh_investments()
                rebuild_dashboard()
                self.respond(200, {"ok": True, **result})
                return
            if path == "/api/investments/extract-image":
                result = investments.extract_image(str(payload.get("image", "")))
                self.respond(200, {"ok": True, **result})
                return
            result = add_expense(payload)
            rebuild_dashboard()
            self.respond(201, {"ok": True, **result})
        except DuplicateExpenseError as exc:
            self.respond(409, {"ok": False, "code": "duplicate", "error": str(exc)})
        except (ValueError, json.JSONDecodeError) as exc:
            self.respond(400, {"ok": False, "error": str(exc)})
        except KeyError as exc:
            self.respond(404, {"ok": False, "error": str(exc).strip("'")})
        except Exception:
            self.respond(500, {"ok": False, "error": "Não foi possível concluir a operação"})

    def do_PUT(self) -> None:
        if not self.valid_request_origin():
            self.respond(403, {"ok": False, "error": "Origem não autorizada"})
            return
        if not self.require_auth():
            return
        path = urlparse(self.path).path
        investment_match = re.fullmatch(r"/api/investments/([a-f0-9]{32})", path)
        expense_match = re.fullmatch(r"/api/expenses/(\d+)", path)
        debt_match = re.fullmatch(r"/api/debts/(\d+)", path)
        category_match = re.fullmatch(r"/api/categories/(.+)", path)
        if not investment_match and not expense_match and not debt_match and not category_match:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65_536:
                raise ValueError("Requisição inválida")
            payload = json.loads(self.rfile.read(length))
            if debt_match:
                item = storage.update_debt(int(debt_match.group(1)), payload)
                rebuild_dashboard()
                self.respond(200, {"ok": True, **item})
                return
            if category_match:cards.ensure_category_editable(unquote(category_match.group(1)))
            if expense_match:cards.ensure_original_editable(int(expense_match.group(1)))
            item = investments.update_investment(investment_match.group(1), payload) if investment_match else storage.update_expense(int(expense_match.group(1)), payload) if expense_match else storage.rename_category(unquote(category_match.group(1)), payload.get("name", ""))
            rebuild_dashboard()
            self.respond(200, {"ok": True, "investment": item} if investment_match else {"ok": True, **item} if expense_match else {"ok": True, "category": item})
        except KeyError as exc:
            self.respond(404, {"ok": False, "error": str(exc).strip("'")})
        except (ValueError, json.JSONDecodeError) as exc:
            self.respond(400, {"ok": False, "error": str(exc)})
        except Exception:
            self.respond(500, {"ok": False, "error": "Não foi possível editar o investimento"})

    def do_DELETE(self) -> None:
        if not self.valid_request_origin():
            self.respond(403, {"ok": False, "error": "Origem não autorizada"})
            return
        if not self.require_auth():
            return
        path = urlparse(self.path).path
        goal_match = re.fullmatch(r"/api/goals/([a-f0-9]{32})", path)
        if goal_match:
            try:planning.delete_goal(goal_match.group(1));self.respond(200, {"ok": True})
            except KeyError as exc:self.respond(404, {"ok": False, "error": str(exc)})
            return
        investment_match = re.fullmatch(r"/api/investments/([a-f0-9]{32})", path)
        expense_match = re.fullmatch(r"/api/expenses/(\d+)", path)
        budget_match = re.fullmatch(r"/api/budgets/(\d{4}-\d{2})/(.+)", path)
        category_match = re.fullmatch(r"/api/categories/(.+)", path)
        if not any((investment_match, expense_match, budget_match, category_match)):
            self.send_error(404)
            return
        try:
            if investment_match: investments.delete_investment(investment_match.group(1))
            elif expense_match:
                cards.ensure_original_editable(int(expense_match.group(1)))
                storage.delete_expense(int(expense_match.group(1)),scope=parse_qs(urlparse(self.path).query).get("scope",["single"])[0])
            elif budget_match: storage.delete_budget(budget_match.group(1), unquote(budget_match.group(2)))
            else:
                cards.ensure_category_editable(unquote(category_match.group(1)))
                storage.delete_category(unquote(category_match.group(1)))
            rebuild_dashboard()
            self.respond(200, {"ok": True})
        except KeyError as exc:
            self.respond(404, {"ok": False, "error": str(exc).strip("'")})
        except Exception:
            self.respond(500, {"ok": False, "error": "Não foi possível excluir o investimento"})

    def respond(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    parser = ArgumentParser(description="Abre o painel local do Minha Carteira")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    options = parser.parse_args()
    subprocess.run([sys.executable, str(BUILD_DASHBOARD)], cwd=ROOT, check=True)
    server = ThreadingHTTPServer((options.host, options.port), Handler)
    print(f"Minha Carteira disponível em http://{options.host}:{options.port}")
    print("Pressione Ctrl+C para encerrar.")
    if not options.no_browser:
        browser_host = "127.0.0.1" if options.host == "0.0.0.0" else options.host
        Timer(0.8, webbrowser.open, args=(f"http://{browser_host}:{options.port}",)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
