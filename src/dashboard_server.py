"""Servidor local do Meu Gasto IA: formulário web -> XLSM -> dashboard."""

from argparse import ArgumentParser
from datetime import date
from datetime import datetime
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from threading import Lock, Timer
from urllib.parse import urlparse
import webbrowser
from zipfile import ZIP_DEFLATED, ZipFile
import xml.etree.ElementTree as ET


ROOT = Path(__file__).resolve().parents[1]
WEB = ROOT / "web"
XLSM = ROOT / "excel/Controle_Gastos_Automatico.xlsm"
BUILD_DASHBOARD = ROOT / "src/build_dashboard.py"
VALIDATE = ROOT / "src/validate_xlsm.py"
BACKUPS = ROOT / "backups"
NS = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
ET.register_namespace("", NS)

CATEGORIES = {
    "Alimentação", "Mercado", "Transporte", "Moradia", "Saúde",
    "Educação", "Lazer", "Compras", "Assinaturas", "Contas",
    "Viagem", "Presentes", "Outros",
}
PAYMENTS = {"Pix", "Crédito", "Débito", "Dinheiro", "Transferência", "Voucher", "Não informado"}
WRITE_LOCK = Lock()


class DuplicateExpenseError(ValueError):
    pass


def set_value(sheet: ET.Element, row: int, column: str, value: str, kind: str) -> None:
    cell = sheet.find(f'.//{{{NS}}}c[@r="{column}{row}"]')
    if cell is None:
        raise ValueError(f"Célula {column}{row} não encontrada")
    for child in list(cell):
        cell.remove(child)
    cell.set("t", kind)
    node = ET.SubElement(cell, f"{{{NS}}}v")
    node.text = value


def cell_value(sheet: ET.Element, row: int, column: str) -> str | None:
    cell = sheet.find(f'.//{{{NS}}}c[@r="{column}{row}"]')
    if cell is None:
        return None
    return cell.findtext(f"{{{NS}}}v")


def read_expenses() -> list[dict]:
    with ZipFile(XLSM) as source:
        sheet = ET.fromstring(source.read("xl/worksheets/sheet1.xml"))
    result = []
    for row in range(51, 551):
        stamp, amount = cell_value(sheet, row, "A"), cell_value(sheet, row, "F")
        if not stamp or not amount:
            continue
        result.append({
            "row": row,
            "date": stamp[:10],
            "where": cell_value(sheet, row, "B") or "",
            "category": cell_value(sheet, row, "C") or "",
            "payment": cell_value(sheet, row, "D") or "",
            "description": cell_value(sheet, row, "E") or "",
            "amount": round(float(amount), 2),
        })
    return result


def create_backup() -> Path:
    BACKUPS.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    destination = BACKUPS / f"Controle_Gastos_Automatico-{stamp}.xlsm"
    destination.write_bytes(XLSM.read_bytes())
    backups = sorted(BACKUPS.glob("Controle_Gastos_Automatico-*.xlsm"), reverse=True)
    for old in backups[20:]:
        old.unlink()
    return destination


def save_workbook(parts: dict[str, bytes]) -> Path:
    handle, temporary_name = tempfile.mkstemp(
        prefix="controle-gastos-", suffix=".xlsm", dir=XLSM.parent
    )
    os.close(handle)
    temporary = Path(temporary_name)
    try:
        with ZipFile(temporary, "w", ZIP_DEFLATED) as destination:
            for name, data in parts.items():
                destination.writestr(name, data)
        with ZipFile(temporary) as check:
            if check.testzip() is not None:
                raise ValueError("A planilha gerada ficou corrompida")
        backup = create_backup()
        os.replace(temporary, XLSM)
    finally:
        temporary.unlink(missing_ok=True)
    subprocess.run([sys.executable, str(VALIDATE)], cwd=ROOT, check=True)
    subprocess.run([sys.executable, str(BUILD_DASHBOARD)], cwd=ROOT, check=True)
    return backup


def read_incomes() -> dict[str, dict[str, float]]:
    with ZipFile(XLSM) as source:
        sheet = ET.fromstring(source.read("xl/worksheets/sheet1.xml"))
    result = {}
    for row in range(2, 101):
        month = cell_value(sheet, row, "X")
        if not month:
            continue
        result[month] = {
            "cash": round(float(cell_value(sheet, row, "Y") or 0), 2),
            "voucher": round(float(cell_value(sheet, row, "Z") or 0), 2),
        }
    return result


def set_income(payload: dict) -> dict:
    month = str(payload.get("month", ""))
    try:
        date.fromisoformat(f"{month}-01")
        cash = round(float(payload.get("cash", 0)), 2)
        voucher = round(float(payload.get("voucher", 0)), 2)
    except (TypeError, ValueError) as exc:
        raise ValueError("Mês ou valores de renda inválidos") from exc
    if cash < 0 or voucher < 0 or cash > 10_000_000 or voucher > 10_000_000:
        raise ValueError("Os valores de renda precisam ser positivos")

    with WRITE_LOCK:
        with ZipFile(XLSM) as source:
            parts = {name: source.read(name) for name in source.namelist()}
        sheet = ET.fromstring(parts["xl/worksheets/sheet1.xml"])
        target_row = None
        for row in range(2, 101):
            saved_month = cell_value(sheet, row, "X")
            if saved_month == month or (saved_month is None and target_row is None):
                target_row = row
                if saved_month == month:
                    break
        if target_row is None:
            raise ValueError("Não há espaço para cadastrar outro mês")
        set_value(sheet, target_row, "X", month, "str")
        set_value(sheet, target_row, "Y", f"{cash:.2f}", "n")
        set_value(sheet, target_row, "Z", f"{voucher:.2f}", "n")
        parts["xl/worksheets/sheet1.xml"] = ET.tostring(
            sheet, encoding="utf-8", xml_declaration=True
        )
        backup = save_workbook(parts)
    return {"month": month, "cash": cash, "voucher": voucher, "backup": backup.name}


def add_expense(payload: dict) -> dict:
    try:
        expense_date = date.fromisoformat(str(payload["date"]))
        amount = round(float(payload["amount"]), 2)
        where = str(payload["where"]).strip()
        category = str(payload["category"]).strip()
        payment = str(payload["payment"]).strip()
        description = str(payload.get("description", "")).strip()
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Preencha data, valor, local, categoria e pagamento") from exc

    if amount <= 0 or amount > 10_000_000:
        raise ValueError("O valor deve ser maior que zero")
    if not where or len(where) > 100 or len(description) > 200:
        raise ValueError("Revise o local ou a descrição")
    if category not in CATEGORIES or payment not in PAYMENTS:
        raise ValueError("Categoria ou pagamento inválido")

    allow_duplicate = payload.get("allow_duplicate") is True

    with WRITE_LOCK:
        with ZipFile(XLSM) as source:
            parts = {name: source.read(name) for name in source.namelist()}
        sheet = ET.fromstring(parts["xl/worksheets/sheet1.xml"])

        normalized = (
            expense_date.isoformat(), where.casefold(), category, payment,
            description.casefold(), amount,
        )
        for existing in read_expenses():
            candidate = (
                existing["date"], existing["where"].casefold(), existing["category"],
                existing["payment"], existing["description"].casefold(), existing["amount"],
            )
            if candidate == normalized and not allow_duplicate:
                raise DuplicateExpenseError(
                    f"Este gasto já existe na linha {existing['row']}"
                )

        target_row = None
        for row in range(51, 551):
            cell = sheet.find(f'.//{{{NS}}}c[@r="A{row}"]')
            if cell is not None and cell.find(f"{{{NS}}}v") is None:
                target_row = row
                break
        if target_row is None:
            raise ValueError("O histórico atingiu o limite de 500 lançamentos")

        stamp = f"{expense_date.isoformat()}T12:00:00.000Z"
        set_value(sheet, target_row, "A", stamp, "d")
        set_value(sheet, target_row, "B", where, "str")
        set_value(sheet, target_row, "C", category, "str")
        set_value(sheet, target_row, "D", payment, "str")
        set_value(sheet, target_row, "E", description, "str")
        set_value(sheet, target_row, "F", f"{amount:.2f}", "n")
        parts["xl/worksheets/sheet1.xml"] = ET.tostring(
            sheet, encoding="utf-8", xml_declaration=True
        )

        backup = save_workbook(parts)
        return {"row": target_row, "backup": backup.name}


class Handler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(WEB), **kwargs)

    def do_GET(self) -> None:
        path = urlparse(self.path).path
        if path == "/api/health":
            self.respond(200, {
                "ok": True,
                "service": "meu-gasto-ia",
                "excel": XLSM.is_file(),
                "expenses": len(read_expenses()),
            })
            return
        if path == "/api/expenses":
            self.respond(200, {"ok": True, "expenses": read_expenses()})
            return
        if path == "/api/incomes":
            self.respond(200, {"ok": True, "incomes": read_incomes()})
            return
        super().do_GET()

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        if path not in {"/api/expenses", "/api/incomes"}:
            self.send_error(404)
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > 16_384:
                raise ValueError("Requisição inválida")
            payload = json.loads(self.rfile.read(length))
            if path == "/api/incomes":
                result = set_income(payload)
                self.respond(200, {"ok": True, **result})
                return
            result = add_expense(payload)
            self.respond(201, {"ok": True, **result})
        except DuplicateExpenseError as exc:
            self.respond(409, {"ok": False, "code": "duplicate", "error": str(exc)})
        except (ValueError, json.JSONDecodeError) as exc:
            self.respond(400, {"ok": False, "error": str(exc)})
        except Exception:
            self.respond(500, {"ok": False, "error": "Não foi possível salvar o gasto"})

    def respond(self, status: int, payload: dict) -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)


if __name__ == "__main__":
    parser = ArgumentParser(description="Abre o painel local do Meu Gasto IA")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-browser", action="store_true")
    options = parser.parse_args()
    subprocess.run([sys.executable, str(BUILD_DASHBOARD)], cwd=ROOT, check=True)
    server = ThreadingHTTPServer((options.host, options.port), Handler)
    print(f"Meu Gasto IA disponível em http://{options.host}:{options.port}")
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
