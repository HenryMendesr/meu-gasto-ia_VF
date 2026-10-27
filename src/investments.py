"""Armazenamento, cálculos e fontes públicas da carteira de investimentos."""

from __future__ import annotations

from base64 import b64decode
from binascii import Error as Base64Error
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
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
    from src import runtime_storage as storage, portfolio_ops as ops
except ImportError:
    import runtime_storage as storage
    import portfolio_ops as ops


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
    data.setdefault("cash_balance", 0)
    return data


def save_store(data: dict, user_id: int | None = None) -> None:
    storage.save_investments(data, user_id)


def audit_change(store, kind, subject, before, after, reason):
    try:from src.trust import audit
    except ImportError:from trust import audit
    return audit(store,kind,subject,before,after,reason)


def mutate_store(operation: Callable, user_id: int | None = None):
    def apply(data):
        data.setdefault("cash_balance", 0)
        data.setdefault("history", [])
        result = operation(data)
        items = [calculated(item) for item in data["investments"]]
        day = investment_today().isoformat()
        point = {"date": day, "value": round(sum(item["current_value"] for item in items) + data["cash_balance"], 2)}
        data["wealth_history"] = [entry for entry in data.get("wealth_history", []) if entry["date"] != day][-729:] + [point]
        return result
    return storage.mutate_investments(apply, user_id)


def cash_cost(item: dict) -> Decimal:
    if "buys" in item:
        return sum((ops.cents(buy["total"]) for buy in ops.buys(item)), Decimal(0))
    value = (Decimal(str(item["quantity"])) * Decimal(str(item["average_price"]))
             if item["type"] in VARIABLE_TYPES else Decimal(str(item["amount_invested"])))
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


def adjust_cash(store: dict, debit: Decimal) -> None:
    available = Decimal(str(store.get("cash_balance", 0)))
    if debit > available:
        raise ValueError("Saldo insuficiente no caixa. Ajuste o caixa antes de salvar o investimento")
    store["cash_balance"] = float((available - debit).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    store["cash_updated_at"] = now_iso()


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
        parsed = date.fromisoformat(str(value))
        if parsed.year < 1900:
            raise ValueError("Ano deve ter quatro dígitos e ser a partir de 1900")
        return parsed.isoformat()
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
        common["amount_invested"] = float(Decimal(str(common["amount_invested"])).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
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
    if existing and (existing.get("sales") or len(existing.get("buys", [])) > 1 or existing.get("incomes") or existing.get("operation_corrected")):
        for field in ("type", "symbol", "quantity", "average_price", "purchase_date"):
            if common.get(field) != existing.get(field):
                raise ValueError("Este ativo tem operações registradas. Use Novo aporte para comprar mais; os dados da compra original ficam preservados")
    if existing and common.get("current_price")==existing.get("current_price"):
        for key in ("quote_date","previous_close"):
            if key in existing:common[key]=existing[key]
    if existing:
        for field in ("buys", "sales", "incomes", "operation_corrected"):
            if field in existing:
                common[field] = existing[field]
    return common


def fetch_json(url: str, timeout: int = 8) -> dict | list:
    request = Request(url, headers={"User-Agent": "Minha-Carteira/1.0", "Accept": "application/json"})
    try:
        with urlopen(request, timeout=timeout) as response:
            return json.load(response)
    except (HTTPError, URLError, TimeoutError, json.JSONDecodeError) as exc:
        raise ValueError("Fonte externa indisponível") from exc


def market_date(value):
    try:
        if isinstance(value,str) and not value.isdigit():
            stamp=datetime.fromisoformat(value.replace('Z','+00:00'))
            if stamp.tzinfo is None:return None
        else:stamp=datetime.fromtimestamp(float(value),timezone.utc)
        return stamp.astimezone(ZoneInfo('America/Sao_Paulo')).date().isoformat()
    except (TypeError,ValueError,OverflowError,OSError):return None


def fetch_quote(symbol: str) -> dict:
    if re.fullmatch(r"[A-Z]{4}\d{1,2}", symbol):
        try:
            data = fetch_json(f"https://brapi.dev/api/quote/{quote(symbol)}")
            result = data["results"][0]
            return {
                "price": round(float(result["regularMarketPrice"]), 8),
                "daily_change_percent": round(float(result.get("regularMarketChangePercent") or 0), 4),
                "source": "Brapi",
                "quote_date": market_date(result.get("regularMarketTime")),
                "previous_close": number(result.get("regularMarketPreviousClose"),"Fechamento anterior",required=False),
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
        previous = float(meta.get("previousClose") or meta.get("chartPreviousClose"))
        market_day=market_date(meta.get("regularMarketTime"))
        closes=result.get("indicators",{}).get("quote",[{}])[0].get("close",[])
        earlier=[close for stamp,close in zip(result.get("timestamp",[]),closes) if close is not None and market_date(stamp) and market_date(stamp)<market_day] if market_day else []
        if earlier:previous=float(earlier[-1])
        change = ((price / previous) - 1) * 100 if previous else 0
    except (KeyError, IndexError, TypeError, ValueError, ZeroDivisionError) as exc:
        raise ValueError(f"Cotação de {symbol} não encontrada") from exc
    return {"price": round(price, 8), "daily_change_percent": round(change, 4), "source": "Yahoo Finance", "quote_date": market_day, "previous_close":previous if earlier or meta.get("previousClose") else None,"updated_at": now_iso()}


def fetch_market_history(symbol: str, period: str = "1y") -> dict:
    ranges = {"1m": ("1mo", "1d"), "3m": ("3mo", "1d"), "6m": ("6mo", "1d"),
              "1y": ("1y", "1d"), "5y": ("5y", "1wk"), "all": ("max", "1d")}
    if period not in ranges:
        raise ValueError("Período inválido")
    chart_range, interval = ranges[period]
    ticker = symbol if symbol.endswith(YAHOO_SUFFIX) or "-" in symbol else f"{symbol}{YAHOO_SUFFIX}"
    data = fetch_json(f"https://query1.finance.yahoo.com/v8/finance/chart/{quote(ticker)}?interval={interval}&range={chart_range}")
    try:
        result = data["chart"]["result"][0]
        timestamps = result["timestamp"]
        quote_data = result["indicators"]["quote"][0]["close"]
        points = []
        quote_series = result["indicators"]["quote"][0]
        for index, (stamp, price) in enumerate(zip(timestamps, quote_data)):
            if price is None or not math.isfinite(float(price)) or float(price) <= 0:
                continue
            point = {"date": datetime.fromtimestamp(stamp, timezone.utc).date().isoformat(), "price": round(float(price), 8)}
            for field in ("open", "high", "low", "volume"):
                series = quote_series.get(field, [])
                value = series[index] if index < len(series) else None
                if value is not None and math.isfinite(float(value)) and float(value) >= 0:
                    point[field] = round(float(value), 8)
            points.append(point)
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise ValueError(f"Histórico de {symbol} não encontrado") from exc
    if not points:
        raise ValueError(f"Histórico de {symbol} não encontrado")
    return {"source": "Yahoo Finance", "points": points}


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
    ranges = {"1m": 31, "3m": 92, "6m": 183, "1y": 366, "5y": 1827, "all": None}
    if period not in ranges:
        raise ValueError("Período inválido")
    start, end = date.fromisoformat(item["application_date"]), investment_today()
    if start > end:
        return []
    visible_start = start if period == "all" else max(start, end - timedelta(days=ranges[period]))
    span = (end - visible_start).days
    steps = min(60, span + 1)
    dates = sorted({visible_start + timedelta(days=round(index * span / max(1, steps - 1))) for index in range(steps)})
    return [{"date": current.isoformat(), "value": round(fixed_income_value(item, current), 2)} for current in dates]


def investment_history(item_id: str, period: str = "1y", user_id: int | None = None,
                       market_fetcher: Callable = fetch_market_history) -> dict:
    item = next((entry for entry in load_store(user_id)["investments"] if entry["id"] == item_id), None)
    if not item:
        raise KeyError("Investimento não encontrado")
    if period not in {"1m", "3m", "6m", "1y", "5y", "all"}:
        raise ValueError("Período inválido")
    iso_date(item.get("purchase_date") or item.get("application_date"), "Data da aplicação: edite o investimento e confira o ano")
    calculated_item = calculated(item)
    if item["type"] in VARIABLE_TYPES:
        history = market_fetcher(item["symbol"], period)
        points = [{**point, "value": round(point["price"] * item["quantity"], 2)} for point in history["points"]
                  if point["date"] <= investment_today().isoformat()]
        source = history["source"]
    else:
        points = fixed_income_history(item, period)
        source = "Estimativa pela taxa cadastrada"
    applied = calculated_item["amount_applied"]
    for point in points:
        point["profit_loss"] = round(point["value"] - applied, 2)
        point["return_percent"] = round((point["value"] / applied - 1) * 100, 4) if applied else 0
    gain_points = []
    for point in points:
        if point["date"] < (item.get("purchase_date") or item.get("application_date")):
            continue
        if item["type"] in VARIABLE_TYPES:
            state = ops.position(item, point["date"])
            gain = float(ops.cents(state["quantity"] * Decimal(str(point["price"])) - state["basis"] + state["realized"] + state["income"]))
        else:
            gain = point["profit_loss"]
        gain_points.append({"date": point["date"], "value": round(gain, 2)})
    purchase = item.get("purchase_date") or item.get("application_date")
    if period == "all" and purchase <= investment_today().isoformat() and (not gain_points or gain_points[0]["date"] > purchase):
        gain_points.insert(0, {"date": purchase, "value": 0})
    if item["type"] in VARIABLE_TYPES:
        known = {point["date"]: point["value"] for point in gain_points}
        for income in item.get("incomes", []):
            if not income.get("reversed") and income["date"] <= investment_today().isoformat():
                reference = next((point["price"] for point in reversed(points) if point["date"] <= income["date"]), None)
                state = ops.position(item, income["date"])
                if reference is not None:
                    known[income["date"]] = float(ops.cents(state["quantity"] * Decimal(str(reference)) - state["basis"] + state["realized"] + state["income"]))
                elif not state["quantity"]:
                    known[income["date"]] = float(state["realized"] + state["income"])
        if calculated_item.get("remaining_quantity") == 0 and any(not sale.get("reversed") for sale in item.get("sales", [])):
            closed = max(sale["date"] for sale in item["sales"] if not sale.get("reversed"))
            for day in (closed, investment_today().isoformat()):
                state = ops.position(item, day)
                known[day] = float(state["realized"] + state["income"])
        gain_points = [{"date": day, "value": value} for day, value in sorted(known.items())]
    if period != "all":
        cutoff = (investment_today() - timedelta(days={"1m": 31, "3m": 92, "6m": 183, "1y": 366, "5y": 1827}[period])).isoformat()
        gain_points = [point for point in gain_points if point["date"] >= cutoff]
    if len(gain_points) > 800:
        gain_points = [gain_points[round(index * (len(gain_points) - 1) / 799)] for index in range(800)]
    # Keep both endpoints when reducing long daily histories for the browser.
    if len(points) > 800:
        points = [points[round(index * (len(points) - 1) / 799)] for index in range(800)]
    return {"gain_points": gain_points, "sales": item.get("sales", []), "buys": ops.buys(item) if item["type"] in VARIABLE_TYPES else [], "incomes": item.get("incomes", []), "start_date": item.get("purchase_date") or item.get("application_date"),
            "profit_loss": points[-1]["profit_loss"] if points else None,
            "historical_return_percent": points[-1]["return_percent"] if points else None,
            "id": item_id, "label": item.get("symbol") or item.get("name"), "type": item["type"],
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
        state = ops.position(item)
        remaining = state["quantity"]
        applied = float(state["basis"])
        price = item.get("current_price") if item.get("current_price") is not None else (float(state["average"]) if remaining else item["average_price"])
        current = float(ops.cents(remaining * Decimal(str(price))))
        realized = float(state["realized"])
        result.update(remaining_quantity=float(remaining), average_price=float(state["average"]) if state["average"] > 0 else item["average_price"],
                      realized_profit_loss=realized, income_received=float(state["income"]),
                      sale_proceeds=round(sum(sale.get("net_total", sale["total"]) for sale in item.get("sales", []) if not sale.get("reversed")), 2),
                      total_profit_loss=round(current - applied + realized + float(state["income"]), 2),
                      total_return_percent=round((current - applied + realized + float(state["income"])) / float(cash_cost(item)) * 100, 4) if cash_cost(item) else 0)
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
    realized = round(sum(item.get("realized_profit_loss", 0) for item in items), 2)
    income = round(sum(item.get("income_received", 0) for item in items), 2)
    total_gain = round(current - applied + realized + income, 2)
    original_cost = sum(float(cash_cost(item)) for item in items)
    history = [point for point in store["history"] if point.get("date") != investment_today().isoformat()]
    if items:
        history.append({"date": investment_today().isoformat(), "current_value": current, "amount_applied": applied, "profit_loss": total_gain})
    estimated = bool(items) and all(item["type"] not in VARIABLE_TYPES for item in items)
    if estimated:
        history = fixed_portfolio_history(items)
    try:from src.daily_summary import summaries
    except ImportError:from daily_summary import summaries
    daily=summaries(store, storage.read_expenses(user_id), investment_today().isoformat())
    return {"daily_summary":daily,"investments": items, "history": history[-730:], "history_source": "estimated" if estimated else "snapshots", "updated_at": store["updated_at"],
            "cash_updated_at": store.get("cash_updated_at"), "goals": store.get("goals", []), "preferences": store.get("preferences", {}), "audit_log": store.get("audit_log", [])[-50:],
            "summary": {"cash_balance": store.get("cash_balance", 0), "total_with_cash": round(current + store.get("cash_balance", 0), 2),
                        "amount_applied": applied, "current_value": current,
                        "profit_loss": total_gain, "income_received": income, "unrealized_profit_loss": round(current - applied, 2), "realized_profit_loss": realized,
                        "return_percent": round(total_gain / original_cost * 100, 4) if original_cost else 0,
                        "monthly_estimated_gain": round(sum(item.get("monthly_estimated_gain") or 0 for item in items), 2)}}


def set_cash_balance(payload: dict, user_id: int | None = None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Informe o saldo do caixa")
    value = number(payload.get("amount"), "Saldo do caixa", minimum=0)
    amount = float(Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
    def update(store):
        before=store['cash_balance']
        store["cash_balance"] = amount
        store["cash_updated_at"] = now_iso()
        if before!=amount:audit_change(store,'cash_adjustment','Caixa',{'cash':before},{'cash':amount},'Saldo total informado pelo usuário')
    mutate_store(update, user_id)
    return portfolio(user_id)


def record_snapshot(store: dict) -> None:
    items = [calculated(item) for item in store["investments"]]
    current = round(sum(item["current_value"] for item in items), 2)
    applied = round(sum(item["amount_applied"] for item in items), 2)
    today = investment_today().isoformat()
    snapshot = {"date": today, "current_value": current, "amount_applied": applied,
                "profit_loss": round(current - applied + sum(item.get("realized_profit_loss", 0) + item.get("income_received", 0) for item in items), 2)}
    if store["history"] and store["history"][-1].get("date") == today:
        store["history"][-1] = snapshot
    else:
        store["history"].append(snapshot)
    store["history"] = store["history"][-730:]


def create_investment(payload: dict, user_id: int | None = None) -> dict:
    item = normalize_payload(payload)
    def create(store):
        cost = cash_cost(item)
        adjust_cash(store, cost)
        item["cash_funded_amount"] = float(cost)
        if item["type"] in VARIABLE_TYPES:
            item["buys"] = [{**ops.initial_buy(item), "cash_debited": True}]
            ops.sync(item)
        store["investments"].append(item)
        audit_change(store,'investment_created',item.get('symbol') or item.get('name'),{}, {'cost':float(cost),'cash':store['cash_balance']},'Cadastro de investimento')
        store["updated_at"] = now_iso()
        record_snapshot(store)
        return calculated(item)
    return mutate_store(create, user_id)


def update_investment(item_id: str, payload: dict, user_id: int | None = None) -> dict:
    def update(store):
        for index, existing in enumerate(store["investments"]):
            if existing["id"] == item_id:
                item = normalize_payload(payload, existing)
                if item["type"] in VARIABLE_TYPES and not existing.get("sales") and len(existing.get("buys", [])) <= 1 and not existing.get("incomes") and not existing.get("operation_corrected"):
                    item["buys"] = [{**ops.initial_buy(item), "cash_debited": "cash_funded_amount" in existing}]
                    ops.sync(item)
                if "cash_funded_amount" in existing:
                    cost = sum((ops.cents(buy["total"]) for buy in ops.buys(item) if buy.get("cash_debited",True)), Decimal(0)) if item.get("operation_corrected") and item["type"] in VARIABLE_TYPES else cash_cost(item)
                    adjust_cash(store, cost - Decimal(str(existing["cash_funded_amount"])))
                    item["cash_funded_amount"] = float(cost)
                audit_change(store,'investment_updated',item.get('symbol') or item.get('name'),{'cost':float(cash_cost(existing))},{'cost':float(cash_cost(item))},'Correção do cadastro')
                store["investments"][index] = item
                store["updated_at"] = now_iso()
                record_snapshot(store)
                return calculated(item)
        raise KeyError("Investimento não encontrado")
    return mutate_store(update, user_id)


def sell_investment(item_id: str, payload: dict, user_id: int | None = None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Dados da venda inválidos")
    def sell(store):
        item = next((entry for entry in store["investments"] if entry["id"] == item_id), None)
        if not item:
            raise KeyError("Investimento não encontrado")
        if item["type"] not in VARIABLE_TYPES:
            raise ValueError("Vendas disponíveis apenas para renda variável")
        request_id = str(payload.get("request_id", ""))
        if request_id:
            previous = next((sale for sale in item.get("sales", []) if sale.get("request_id") == request_id), None)
            if previous:
                return {"sale": previous, "investment": calculated(item)}
        quantity = Decimal(str(number(payload.get("quantity"), "Quantidade vendida", minimum=0.00000001)))
        item.setdefault("buys", [ops.initial_buy(item)])
        remaining = ops.position(item)["quantity"]
        if quantity > remaining:
            raise ValueError("Quantidade vendida maior que a posição disponível")
        sale_date = iso_date(payload.get("date"), "Data da venda")
        if not item["purchase_date"] <= sale_date <= investment_today().isoformat():
            raise ValueError("A venda deve ocorrer entre a compra e hoje")
        mode = payload.get("mode", "unit")
        value = Decimal(str(number(payload.get("value"), "Valor da venda", minimum=0.00000001)))
        if mode not in {"unit", "total"}:
            raise ValueError("Informe preço por ação ou valor total")
        total = (quantity * value if mode == "unit" else value).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        if total <= 0:
            raise ValueError("Valor total da venda deve ser positivo")
        fees = ops.cents(number(payload.get("fees") or 0, "Taxas da venda", minimum=0))
        if fees >= total:
            raise ValueError("As taxas devem ser menores que o total da venda")
        last_day = ops.latest_date(item)
        if sale_date < last_day:
            raise ValueError("Registre a venda em ordem cronológica, após a última operação")
        unit = value if mode == "unit" else total / quantity
        sale = {"id": uuid4().hex, "request_id": request_id, "date": sale_date, "quantity": float(quantity), "unit_price": float(unit),
                "total": float(total), "fees": float(fees), "net_total": float(total - fees),
                "sequence": ops.sequence(item), "created_at": now_iso()}
        item.setdefault("sales", []).append(sale)
        item["sales"].sort(key=lambda entry: (entry["date"], entry.get("sequence", 0)))
        ops.sync(item)
        adjust_cash(store, -(total - fees))
        sale["cash_credited"] = True
        item["updated_at"] = store["updated_at"] = now_iso()
        record_snapshot(store)
        return {"sale": sale, "investment": calculated(item)}
    return mutate_store(sell, user_id)


def add_buy(item_id: str, payload: dict, user_id: int | None = None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Dados da operação inválidos")
    def buy(store):
        item = next((entry for entry in store["investments"] if entry["id"] == item_id), None)
        if not item or item["type"] not in VARIABLE_TYPES:
            raise ValueError("Escolha um ativo de renda variável para registrar o aporte")
        request_id = str(payload.get("request_id", ""))
        existing = next((entry for entry in item.get("buys", []) if request_id and entry.get("request_id") == request_id), None)
        if existing:
            return {"buy": existing, "investment": calculated(item)}
        day = iso_date(payload.get("date"), "Data da compra")
        last = ops.latest_date(item)
        if not last <= day <= investment_today().isoformat():
            raise ValueError("Registre os aportes em ordem cronológica, até a data de hoje")
        quantity = number(payload.get("quantity"), "Quantidade", minimum=0.00000001)
        price = number(payload.get("unit_price"), "Preço por unidade", minimum=0.00000001)
        fees = ops.cents(number(payload.get("fees") or 0, "Taxas", minimum=0))
        total = ops.cents(Decimal(str(quantity)) * Decimal(str(price))) + fees
        if total <= 0:
            raise ValueError("O total do aporte deve ser positivo")
        adjust_cash(store, total)
        item.setdefault("buys", [ops.initial_buy(item)])
        entry = {"id": uuid4().hex, "request_id": request_id, "date": day, "quantity": quantity,
                 "unit_price": price, "fees": float(fees), "total": float(total), "sequence": ops.sequence(item), "cash_debited": True}
        item["buys"].append(entry)
        item["cash_funded_amount"] = float(ops.cents(item.get("cash_funded_amount", 0)) + total)
        ops.sync(item)
        if item.get("current_price") is None:
            item["current_price"] = price
            item["quote_source"] = "Última compra"
        item["updated_at"] = store["updated_at"] = now_iso()
        record_snapshot(store)
        return {"buy": entry, "investment": calculated(item)}
    return mutate_store(buy, user_id)


def add_investment_income(item_id: str, payload: dict, user_id: int | None = None) -> dict:
    if not isinstance(payload, dict):
        raise ValueError("Dados da operação inválidos")
    def receive(store):
        item = next((entry for entry in store["investments"] if entry["id"] == item_id), None)
        if not item or item["type"] not in VARIABLE_TYPES:
            raise ValueError("Escolha um ativo de renda variável para registrar o provento")
        request_id = str(payload.get("request_id", ""))
        existing = next((entry for entry in item.get("incomes", []) if request_id and entry.get("request_id") == request_id), None)
        if existing:
            return {"income": existing, "investment": calculated(item)}
        day = iso_date(payload.get("date"), "Data do recebimento")
        if not item["purchase_date"] <= day <= investment_today().isoformat():
            raise ValueError("Informe uma data entre a primeira compra e hoje")
        kind = str(payload.get("kind", ""))
        if kind not in {"Dividendos", "JCP", "Rendimento de FII", "Outros proventos"}:
            raise ValueError("Escolha o tipo do provento")
        amount = ops.cents(number(payload.get("amount"), "Valor líquido recebido", minimum=0.01))
        entry = {"id": uuid4().hex, "request_id": request_id, "date": day, "kind": kind, "amount": float(amount)}
        entry['cash_credited'] = True
        item.setdefault("incomes", []).append(entry)
        item.setdefault("buys", [ops.initial_buy(item)])
        ops.sync(item)
        adjust_cash(store, -amount)
        item["updated_at"] = store["updated_at"] = now_iso()
        record_snapshot(store)
        return {"income": entry, "investment": calculated(item)}
    return mutate_store(receive, user_id)


def delete_investment(item_id: str, user_id: int | None = None) -> None:
    def delete(store):
        existing = next((item for item in store["investments"] if item["id"] == item_id), None)
        if not existing:
            raise KeyError("Investimento não encontrado")
        if existing.get("sales") or existing.get("incomes"):
            raise ValueError("Ativo com vendas registradas: mantenha-o para preservar o resultado realizado")
        if "cash_funded_amount" in existing:
            adjust_cash(store, -Decimal(str(existing["cash_funded_amount"])))
        store["investments"] = [item for item in store["investments"] if item["id"] != item_id]
        store["updated_at"] = now_iso()
        record_snapshot(store)
    mutate_store(delete, user_id)


def refresh_investments(quote_fetcher: Callable = fetch_quote, cdi_fetcher: Callable = fetch_cdi_rate, user_id: int | None = None) -> dict:
    store = load_store(user_id)
    errors = []
    cdi = None
    updates = {}
    identities = {item["id"]: (item["type"], item.get("symbol"), item.get("profitability_type")) for item in store["investments"]}
    for item in store["investments"]:
        try:
            if item["type"] in VARIABLE_TYPES:
                info = quote_fetcher(item["symbol"])
                updates[item["id"]] = {"current_price": info["price"], "daily_change_percent": info["daily_change_percent"],
                                       "quote_source": info["source"], "quote_updated_at": info["updated_at"],
                                       "quote_date":info.get("quote_date"),"previous_close":info.get("previous_close")}
            elif item.get("profitability_type") == "CDI":
                cdi = cdi or cdi_fetcher()
                updates[item["id"]] = {"cdi_rate": cdi["rate"], "rate_source": cdi["source"], "rate_updated_at": cdi["updated_at"]}
        except ValueError as exc:
            errors.append({"id": item["id"], "name": item.get("symbol") or item.get("name"), "error": str(exc)})
    def merge(current):
        for item in current["investments"]:
            if identities.get(item["id"]) == (item["type"], item.get("symbol"), item.get("profitability_type")):
                item.update(updates.get(item["id"], {}))
        current["updated_at"] = now_iso()
        record_snapshot(current)
    mutate_store(merge, user_id)
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
