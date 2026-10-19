"""Servidor local autenticado do Minha Carteira."""

from argparse import ArgumentParser
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from http.cookies import SimpleCookie
from html import escape
import json
from pathlib import Path
import re
import subprocess
import sys
from threading import Timer
from urllib.parse import parse_qs, unquote, urlparse
import webbrowser

try:
    from src import auth, investments, runtime_storage as storage
except ImportError:  # execução direta: python src/dashboard_server.py
    import auth, investments, runtime_storage as storage


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
            values = {"__TITLE__": "Entrar", "__SUBTITLE__": "Acesse seu controle financeiro", "__ACTION__": "/login", "__FIELDS__": fields, "__BUTTON__": "Entrar", "__FOOTER__": ""}
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
        if path in {"/manifest.webmanifest", "/service-worker.js", "/offline.html"} or path.startswith("/icons/"):
            super().do_GET()
            return
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
            self.respond(200, {"ok": True, "expenses": read_expenses(), "incomes": read_incomes(), "income_entries": storage.read_income_entries(), "budgets": read_budgets(), "categories": storage.read_categories(), "portfolio": investments.portfolio()})
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
        if path == "/api/investments":
            self.respond(200, {"ok": True, **investments.portfolio()})
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
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
        if path not in {"/api/expenses", "/api/incomes", "/api/budgets", "/api/categories", "/api/investments", "/api/investments/refresh", "/api/investments/extract-image"}:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            maximum = 12_000_000 if path == "/api/investments/extract-image" else 65_536
            if length <= 0 or length > maximum:
                raise ValueError("Requisição inválida")
            payload = json.loads(self.rfile.read(length))
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
        category_match = re.fullmatch(r"/api/categories/(.+)", path)
        if not investment_match and not expense_match and not category_match:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 65_536:
                raise ValueError("Requisição inválida")
            payload = json.loads(self.rfile.read(length))
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
        investment_match = re.fullmatch(r"/api/investments/([a-f0-9]{32})", path)
        expense_match = re.fullmatch(r"/api/expenses/(\d+)", path)
        budget_match = re.fullmatch(r"/api/budgets/(\d{4}-\d{2})/(.+)", path)
        category_match = re.fullmatch(r"/api/categories/(.+)", path)
        if not any((investment_match, expense_match, budget_match, category_match)):
            self.send_error(404)
            return
        try:
            if investment_match: investments.delete_investment(investment_match.group(1))
            elif expense_match: storage.delete_expense(int(expense_match.group(1)))
            elif budget_match: storage.delete_budget(budget_match.group(1), unquote(budget_match.group(2)))
            else: storage.delete_category(unquote(category_match.group(1)))
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
