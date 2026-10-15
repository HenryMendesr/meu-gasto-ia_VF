"""Armazenamento, cálculos e fontes públicas da carteira de investimentos."""

from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from datetime import date, datetime, timedelta, timezone
import json
import math
import mimetypes
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
from typing import Callable
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen
from uuid import uuid4

try:
    from src import runtime_storage as storage
except ImportError:
    import runtime_storage as storage


ROOT = Path(__file__).resolve().parents[1]
VARIABLE_TYPES = {"Ações", "Fundos imobiliários", "ETFs", "Criptomoedas", "Outros"}
ALL_TYPES = VARIABLE_TYPES | {"Renda fixa"}
YAHOO_SUFFIX = ".SA"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def empty_store() -> dict:
    return {"version": 1, "updated_at": None, "investments": [], "history": []}


def load_store(user_id: int | None = None) -> dict:
    data = storage.load_investments(user_id)
    if not isinstance(data, dict) or not isinstance(data.get("investments"), list):
        raise ValueError("O arquivo de investimentos está inválido")
    data.setdefault("history", [])
    data.setdefault("updated_at", None)
    return data


def save_store(data: dict, user_id: int | None = None) -> None:
    storage.save_investments(data, user_id)


def number(value, field: str, *, required: bool = True, minimum: float = 0) -> float | None:
    if value in (None, "") and not required:
        return None
    try:
        result = round(float(value), 8)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field} inválido") from exc
    if not math.isfinite(result) or result < minimum or result > 1_000_000_000:
        raise ValueError(f"{field} inválido")
    return result


def iso_date(value, field: str, *, required: bool = True) -> str | None:
    if value in (None, "") and not required:
        return None
    try:
        return date.fromisoformat(str(value)).isoformat()
    except ValueError as exc:
        raise ValueError(f"{field} inválida") from exc


def normalize_payload(payload: dict, existing: dict | None = None) -> dict:
    investment_type = str(payload.get("type", "")).strip()
    if investment_type not in ALL_TYPES:
        raise ValueError("Tipo de investimento inválido")
    common = {
        "id": (existing or {}).get("id", uuid4().hex),
        "type": investment_type,
        "created_at": (existing or {}).get("created_at", now_iso()),
        "updated_at": now_iso(),
    }
    if investment_type in VARIABLE_TYPES:
        symbol = re.sub(r"\s+", "", str(payload.get("symbol", "")).upper())
        if not re.fullmatch(r"[A-Z0-9.\-]{2,20}", symbol):
            raise ValueError("Código do ativo inválido")
        common.update({
            "symbol": symbol,
            "quantity": number(payload.get("quantity"), "Quantidade", minimum=0.00000001),
            "average_price": number(payload.get("average_price"), "Preço médio", minimum=0.00000001),
            "purchase_date": iso_date(payload.get("purchase_date"), "Data da compra"),
            "current_price": number(payload.get("current_price"), "Cotação manual", required=False),
            "daily_change_percent": number(payload.get("daily_change_percent", (existing or {}).get("daily_change_percent")), "Variação diária", required=False, minimum=-100),
            "quote_source": str(payload.get("quote_source") or (existing or {}).get("quote_source") or "Manual"),
            "quote_updated_at": payload.get("quote_updated_at", (existing or {}).get("quote_updated_at")),
        })
    else:
        profitability_type = str(payload.get("profitability_type", "")).strip()
        if profitability_type not in {"CDI", "Prefixado", "IPCA + taxa", "Outro"}:
            raise ValueError("Tipo de rentabilidade inválido")
        name = str(payload.get("name", "")).strip()
        institution = str(payload.get("institution", "")).strip()
        if not name or len(name) > 120 or not institution or len(institution) > 120:
            raise ValueError("Informe o nome e a instituição financeira")
        common.update({
            "name": name,
            "institution": institution,
            "amount_invested": number(payload.get("amount_invested"), "Valor aplicado", minimum=0.01),
            "application_date": iso_date(payload.get("application_date"), "Data da aplicação"),
            "profitability_type": profitability_type,
            "contracted_rate": number(payload.get("contracted_rate"), "Taxa contratada", minimum=0),
            "maturity_date": iso_date(payload.get("maturity_date"), "Data de vencimento", required=False),
            "current_value_manual": number(payload.get("current_value_manual"), "Saldo atual", required=False),
            "cdi_rate": number(payload.get("cdi_rate", (existing or {}).get("cdi_rate")), "Taxa CDI", required=False),
            "rate_source": str(payload.get("rate_source") or (existing or {}).get("rate_source") or "Manual"),
            "rate_updated_at": payload.get("rate_updated_at", (existing or {}).get("rate_updated_at")),
        })
        if common["maturity_date"] and common["maturity_date"] < common["application_date"]:
            raise ValueError("O vencimento não pode ser anterior à aplicação")
    return common


def fetch_json(url: str, timeout: int = 8) -> dict | list:
    request = Request(url, headers={"User-Agent": "Meu-Gasto-IA/1.0", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError("Fonte externa indisponível") from exc


def fetch_quote(symbol: str) -> dict:
    if re.fullmatch(r"[A-Z]{4}\d{1,2}", symbol):
        try:
            data = fetch_json(f"https://brapi.dev/api/quote/{quote(symbol)}")
            result = data["results"][0]
            return {
                "price": round(float(result["regularMarketPrice"]), 8),
                "daily_change_percent": round(float(result.get("regularMarketChangePercent") or 0), 4),
                "source": "Brapi",
                "updated_at": now_iso(),
            }
        except (ValueError, KeyError, IndexError, TypeError):
            pass
    ticker = symbol if symbol.endswith(YAHOO_SUFFIX) or "-" in symbol else f"{symbol}{YAHOO_SUFFIX}"
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}?interval=1d&range=5d"
    data = fetch_json(url)
    try:
        result = data["chart"]["result"][0]
        meta = result["meta"]
        price = float(meta["regularMarketPrice"])
        previous = float(meta.get("chartPreviousClose") or meta.get("previousClose"))
        change = ((price / previous) - 1) * 100 if previous else 0
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"Cotação de {symbol} não encontrada") from exc
    return {"price": round(price, 8), "daily_change_percent": round(change, 4), "source": "Yahoo Finance", "updated_at": now_iso()}


def fetch_cdi_rate() -> dict:
    end = date.today()
    start = end - timedelta(days=14)
    url = ("https://api.bcb.gov.br/dados/serie/bcdata.sgs.12/dados"
           f"?formato=json&dataInicial={start:%d/%m/%Y}&dataFinal={end:%d/%m/%Y}")
    data = fetch_json(url)
    if not data:
        raise ValueError("Taxa CDI não encontrada")
    try:
        daily = float(str(data[-1]["valor"]).replace(",", ".")) / 100
        annual = ((1 + daily) ** 252 - 1) * 100
    except (KeyError, TypeError, ValueError) as exc:
        raise ValueError("Resposta inválida do Banco Central") from exc
    return {"rate": round(annual, 4), "source": "Banco Central do Brasil — SGS 12", "updated_at": now_iso()}


def calculated(item: dict) -> dict:
    result = dict(item)
    if item["type"] in VARIABLE_TYPES:
        applied = item["quantity"] * item["average_price"]
        current = item["quantity"] * (item.get("current_price") or item["average_price"])
    else:
        applied = item["amount_invested"]
        manual = item.get("current_value_manual")
        if manual is not None:
            current = manual
        else:
            days = max(0, (date.today() - date.fromisoformat(item["application_date"])).days)
            rate = item["contracted_rate"] / 100
            if item["profitability_type"] == "CDI":
                rate *= (item.get("cdi_rate") or 0) / 100
            current = applied * ((1 + rate) ** (days / 365))
    result["amount_applied"] = round(applied, 2)
    result["current_value"] = round(current, 2)
    result["profit_loss"] = round(current - applied, 2)
    result["return_percent"] = round(((current / applied) - 1) * 100, 4) if applied else 0
    return result


def portfolio(user_id: int | None = None) -> dict:
    store = load_store(user_id)
    items = [calculated(item) for item in store["investments"]]
    applied = round(sum(item["amount_applied"] for item in items), 2)
    current = round(sum(item["current_value"] for item in items), 2)
    return {"investments": items, "history": store["history"], "updated_at": store["updated_at"],
            "summary": {"amount_applied": applied, "current_value": current,
                        "profit_loss": round(current - applied, 2),
                        "return_percent": round(((current / applied) - 1) * 100, 4) if applied else 0}}


def record_snapshot(store: dict) -> None:
    items = [calculated(item) for item in store["investments"]]
    current = round(sum(item["current_value"] for item in items), 2)
    applied = round(sum(item["amount_applied"] for item in items), 2)
    today = date.today().isoformat()
    snapshot = {"date": today, "current_value": current, "amount_applied": applied}
    if store["history"] and store["history"][-1].get("date") == today:
        store["history"][-1] = snapshot
    else:
        store["history"].append(snapshot)
    store["history"] = store["history"][-730:]


def create_investment(payload: dict, user_id: int | None = None) -> dict:
    store = load_store(user_id)
    item = normalize_payload(payload)
    store["investments"].append(item)
    store["updated_at"] = now_iso()
    record_snapshot(store)
    save_store(store, user_id)
    return calculated(item)


def update_investment(item_id: str, payload: dict, user_id: int | None = None) -> dict:
    store = load_store(user_id)
    for index, existing in enumerate(store["investments"]):
        if existing["id"] == item_id:
            item = normalize_payload(payload, existing)
            store["investments"][index] = item
            store["updated_at"] = now_iso()
            record_snapshot(store)
            save_store(store, user_id)
            return calculated(item)
    raise KeyError("Investimento não encontrado")


def delete_investment(item_id: str, user_id: int | None = None) -> None:
    store = load_store(user_id)
    before = len(store["investments"])
    store["investments"] = [item for item in store["investments"] if item["id"] != item_id]
    if len(store["investments"]) == before:
        raise KeyError("Investimento não encontrado")
    store["updated_at"] = now_iso()
    record_snapshot(store)
    save_store(store, user_id)


def refresh_investments(quote_fetcher: Callable = fetch_quote, cdi_fetcher: Callable = fetch_cdi_rate, user_id: int | None = None) -> dict:
    store = load_store(user_id)
    errors = []
    cdi = None
    for item in store["investments"]:
        try:
            if item["type"] in VARIABLE_TYPES:
                info = quote_fetcher(item["symbol"])
                item.update({"current_price": info["price"], "daily_change_percent": info["daily_change_percent"],
                             "quote_source": info["source"], "quote_updated_at": info["updated_at"]})
            elif item.get("profitability_type") == "CDI":
                cdi = cdi or cdi_fetcher()
                item.update({"cdi_rate": cdi["rate"], "rate_source": cdi["source"], "rate_updated_at": cdi["updated_at"]})
        except ValueError as exc:
            errors.append({"id": item["id"], "name": item.get("symbol") or item.get("name"), "error": str(exc)})
    store["updated_at"] = now_iso()
    record_snapshot(store)
    save_store(store, user_id)
    result = portfolio(user_id)
    result["errors"] = errors
    return result


def extract_image(data_url: str) -> dict:
    match = re.fullmatch(r"data:(image/(?:png|jpeg|webp));base64,(.+)", data_url, re.DOTALL)
    if not match:
        raise ValueError("Envie uma imagem PNG, JPG ou WebP")
    try:
        raw = b64decode(match.group(2), validate=True)
    except Base64Error as exc:
        raise ValueError("A imagem enviada está inválida") from exc
    if len(raw) > 8_000_000:
        raise ValueError("A imagem deve ter no máximo 8 MB")
    if not shutil.which("tesseract"):
        raise ValueError("Leitura automática de imagem indisponível neste computador; preencha os campos manualmente")
    suffix = mimetypes.guess_extension(match.group(1)) or ".png"
    with tempfile.NamedTemporaryFile(suffix=suffix) as image:
        image.write(raw)
        image.flush()
        process = subprocess.run(["tesseract", image.name, "stdout", "-l", "por"], capture_output=True, text=True, timeout=30)
        if process.returncode and "Failed loading language" in process.stderr:
            process = subprocess.run(["tesseract", image.name, "stdout"], capture_output=True, text=True, timeout=30)
    if process.returncode:
        raise ValueError("Não foi possível ler a imagem")
    text = process.stdout.strip()
    values = re.findall(r"(?:R\$\s*)?([\d.]+,\d{2})", text)
    dates = re.findall(r"\b(\d{2})/(\d{2})/(\d{4})\b", text)
    fields = {}
    if values:
        fields["amount_invested"] = float(values[0].replace(".", "").replace(",", "."))
    if dates:
        day, month, year = dates[0]
        fields["application_date"] = f"{year}-{month}-{day}"
    cdi = re.search(r"(\d+(?:[,.]\d+)?)\s*%\s*(?:do\s*)?CDI", text, re.I)
    if cdi:
        fields.update({"profitability_type": "CDI", "contracted_rate": float(cdi.group(1).replace(",", "."))})
    return {"text": text[:4000], "fields": fields}
