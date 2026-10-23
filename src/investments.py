"""Armazenamento, cálculos e fontes públicas da carteira de investimentos."""

from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from datetime import date, datetime, timedelta, timezone
from zoneinfo import ZoneInfo
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
        period = str(payload.get("rate_period", (existing or {}).get("rate_period", "year")))
        if period not in {"year", "month"}:
            raise ValueError("Escolha taxa ao mês ou ao ano")
        if profitability_type in {"CDI", "IPCA + taxa"}:
            period = "year"
        mode = str(payload.get("valuation_mode") or (existing or {}).get("valuation_mode") or
                   ("balance" if common["current_value_manual"] is not None else "automatic"))
        if mode not in {"automatic", "balance", "manual"}:
            raise ValueError("Forma de cálculo inválida")
        balance_date = payload.get("current_value_date") or (existing or {}).get("current_value_date") or (existing or {}).get("updated_at", investment_today().isoformat())[:10]
        common.update(rate_period=period, valuation_mode=mode,
                      current_value_date=iso_date(balance_date, "Data do saldo"),
                      ipca_rate=number(payload.get("ipca_rate", (existing or {}).get("ipca_rate")), "IPCA anual", required=False))
        if common["contracted_rate"] > (100 if period == "month" else 1000):
            raise ValueError("Revise a taxa contratada")
        if mode == "automatic":
            common["current_value_manual"] = None
        elif common["current_value_manual"] is None:
            raise ValueError("Informe o saldo de referência")
        elif common["current_value_date"] < common["application_date"] or common["current_value_date"] > investment_today().isoformat():
            raise ValueError("A data do saldo deve ficar entre a aplicação e hoje")
        if common["maturity_date"] and common["maturity_date"] < common["application_date"]:
            raise ValueError("O vencimento não pode ser anterior à aplicação")
    return common


def fetch_json(url: str, timeout: int = 8) -> dict | list:
    request = Request(url, headers={"User-Agent": "Minha-Carteira/1.0", "Accept": "application/json"})
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


def fetch_market_history(symbol: str, period: str = "1y") -> dict:
    ranges = {"1m": ("1mo", "1d"), "3m": ("3mo", "1d"), "6m": ("6mo", "1d"),
              "1y": ("1y", "1d"), "5y": ("5y", "1wk")}
    if period not in ranges:
        raise ValueError("Período inválido")
    chart_range, interval = ranges[period]
    ticker = symbol if symbol.endswith(YAHOO_SUFFIX) or "-" in symbol else f"{symbol}{YAHOO_SUFFIX}"
    data = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}?interval={interval}&range={chart_range}")
    try:
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote_data = result["indicators"]["quote"][0]["close"]
        points = [{"date": datetime.fromtimestamp(stamp, timezone.utc).date().isoformat(), "price": round(float(price), 8)}
                  for stamp, price in zip(timestamps, quote_data) if price is not None]
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError(f"Histórico de {symbol} não encontrado") from exc
    if not points:
        raise ValueError(f"Histórico de {symbol} não encontrado")
    return {"source": "Yahoo Finance", "points": points[-260:]}


def investment_today() -> date:
    return datetime.now(ZoneInfo("America/Sao_Paulo")).date()


def fixed_mode(item: dict) -> str:
    return item.get("valuation_mode") or ("balance" if item.get("current_value_manual") is not None else "automatic")


def fixed_annual_rate(item: dict) -> float | None:
    rate = item["contracted_rate"] / 100
    kind = item["profitability_type"]
    if kind == "CDI":
        if item.get("cdi_rate") is None:
            return None
        daily = math.expm1(math.log1p(item["cdi_rate"] / 100) / 252)
        return math.expm1(252 * math.log1p(daily * rate))
    if kind == "IPCA + taxa":
        if item.get("ipca_rate") is None:
            return None
        return (1 + item["ipca_rate"] / 100) * (1 + rate) - 1
    return math.expm1(12 * math.log1p(rate)) if item.get("rate_period", "year") == "month" else rate


def fixed_income_value(item: dict, as_of: date | None = None) -> float:
    as_of = as_of or investment_today()
    start = date.fromisoformat(item["application_date"])
    maturity = date.fromisoformat(item["maturity_date"]) if item.get("maturity_date") else None
    end = min(as_of, maturity) if maturity else as_of
    mode, rate = fixed_mode(item), fixed_annual_rate(item)
    applied, manual = item["amount_invested"], item.get("current_value_manual")
    if as_of < start:
        return applied
    if mode in {"balance", "manual"} and manual is not None:
        reference = date.fromisoformat(item.get("current_value_date") or item.get("updated_at", item["application_date"])[:10])
        if mode == "manual" and as_of >= reference:
            return manual
        if end < reference:
            # The path to an observed balance is an estimate, not a market history.
            span = (reference - start).days
            fraction = min(1, max(0, (end - start).days / span)) if span else 0
            return applied * (manual / applied) ** fraction
        if mode == "manual" or rate is None:
            return manual
        return manual * math.exp(math.log1p(rate) * max(0, (end - reference).days) / 365)
    return applied if rate is None else applied * math.exp(math.log1p(rate) * max(0, (end - start).days) / 365)


def fixed_income_history(item: dict, period: str) -> list[dict]:
    ranges = {"1m": 31, "3m": 92, "6m": 183, "1y": 366, "5y": 1827}
    if period not in ranges:
        raise ValueError("Período inválido")
    start, end = date.fromisoformat(item["application_date"]), investment_today()
    if start > end:
        return []
    visible_start = max(start, end - timedelta(days=ranges[period]))
    span = (end - visible_start).days
    steps = min(60, span + 1)
    dates = sorted({visible_start + timedelta(days=round(index * span / max(1, steps - 1))) for index in range(steps)})
    return [{"date": current.isoformat(), "value": round(fixed_income_value(item, current), 2)} for current in dates]


def investment_history(item_id: str, period: str = "1y", user_id: int | None = None,
                       market_fetcher: Callable = fetch_market_history) -> dict:
    item = next((entry for entry in load_store(user_id)["investments"] if entry["id"] == item_id), None)
    if not item:
        raise KeyError("Investimento não encontrado")
    calculated_item = calculated(item)
    if item["type"] in VARIABLE_TYPES:
        history = market_fetcher(item["symbol"], period)
        points = [{**point, "value": round(point["price"] * item["quantity"], 2)} for point in history["points"]]
        source = history["source"]
    else:
        points = fixed_income_history(item, period)
        source = "Estimativa pela taxa cadastrada"
    return {"id": item_id, "label": item.get("symbol") or item.get("name"), "type": item["type"],
            "period": period, "source": source, "average_price": item.get("average_price"),
            "amount_applied": calculated_item["amount_applied"], "current_value": calculated_item["current_value"],
            "return_percent": calculated_item["return_percent"], "points": points}


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
        current = fixed_income_value(item)
        annual = fixed_annual_rate(item)
        today = investment_today()
        mode = fixed_mode(item)
        active = today >= date.fromisoformat(item["application_date"]) and (not item.get("maturity_date") or today < date.fromisoformat(item["maturity_date"]))
        monthly = math.expm1(math.log1p(annual) / 12) if annual is not None else None
        result.update(valuation_mode=mode, rate_period=item.get("rate_period", "year"),
                      annual_rate_percent=round(annual * 100, 6) if annual is not None else None,
                      monthly_rate_percent=round(monthly * 100, 6) if monthly is not None else None,
                      monthly_estimated_gain=round(current * monthly, 2) if active and monthly is not None and mode != "manual" else None,
                      calculation_status="manual" if mode == "manual" else "pending_rate" if annual is None else "matured" if not active and item.get("maturity_date") and today >= date.fromisoformat(item["maturity_date"]) else "estimated",
                      calculated_on=today.isoformat())
    result["amount_applied"] = round(applied, 2)
    result["current_value"] = round(current, 2)
    result["profit_loss"] = round(current - applied, 2)
    result["return_percent"] = round(((current / applied) - 1) * 100, 4) if applied else 0
    return result


def fixed_portfolio_history(items: list[dict]) -> list[dict]:
    today = investment_today()
    eligible = [item for item in items if item["application_date"] <= today.isoformat()]
    if not eligible:
        return []
    start = max(min(date.fromisoformat(item["application_date"]) for item in eligible), today - timedelta(days=365))
    span = (today - start).days
    steps = min(60, span + 1)
    dates = sorted({start + timedelta(days=round(index * span / max(1, steps - 1))) for index in range(steps)})
    return [{"date": current.isoformat(),
             "current_value": round(sum(fixed_income_value(item, current) for item in eligible if item["application_date"] <= current.isoformat()), 2),
             "amount_applied": round(sum(item["amount_invested"] for item in eligible if item["application_date"] <= current.isoformat()), 2)} for current in dates]


def portfolio(user_id: int | None = None) -> dict:
    store = load_store(user_id)
    items = [calculated(item) for item in store["investments"]]
    applied = round(sum(item["amount_applied"] for item in items), 2)
    current = round(sum(item["current_value"] for item in items), 2)
    history = [point for point in store["history"] if point.get("date") != investment_today().isoformat()]
    if items:
        history.append({"date": investment_today().isoformat(), "current_value": current, "amount_applied": applied})
    estimated = bool(items) and all(item["type"] not in VARIABLE_TYPES for item in items)
    if estimated:
        history = fixed_portfolio_history(items)
    return {"investments": items, "history": history[-730:], "history_source": "estimated" if estimated else "snapshots", "updated_at": store["updated_at"],
            "summary": {"amount_applied": applied, "current_value": current,
                        "profit_loss": round(current - applied, 2),
                        "return_percent": round(((current / applied) - 1) * 100, 4) if applied else 0,
                        "monthly_estimated_gain": round(sum(item.get("monthly_estimated_gain") or 0 for item in items), 2)}}


def record_snapshot(store: dict) -> None:
    items = [calculated(item) for item in store["investments"]]
    current = round(sum(item["current_value"] for item in items), 2)
    applied = round(sum(item["amount_applied"] for item in items), 2)
    today = investment_today().isoformat()
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
