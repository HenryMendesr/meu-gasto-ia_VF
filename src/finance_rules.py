"""Regras financeiras puras compartilhadas pelos bancos local e hospedado."""
from calendar import monthrange
from datetime import date
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from uuid import uuid4


CENT = Decimal("0.01")


def money(value, label: str = "Valor") -> Decimal:
    try:
        result = Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValueError(f"{label} inválido") from exc
    if not result.is_finite() or result <= 0 or result > Decimal("10000000"):
        raise ValueError(f"{label} deve ser maior que zero")
    return result


def add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def interest_rate(value=0) -> Decimal:
    try:
        rate = Decimal(str(value if value not in (None, "") else 0).replace(",", "."))
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Taxa mensal inválida") from exc
    if not rate.is_finite() or rate < 0 or rate > 100:
        raise ValueError("A taxa mensal deve ficar entre 0 e 100%")
    return rate / 100


def installment_plan(total_value, count_value, first_charge, installment_value=None, rate_value=0, system="price", max_count=120, min_count=2) -> list[dict]:
    total = money(total_value, "Valor financiado")
    rate = interest_rate(rate_value)
    if system not in {"price", "sac"}:
        raise ValueError("Sistema de amortização inválido")
    regular = money(installment_value, "Valor da parcela") if installment_value not in (None, "") else None
    try:
        first = date.fromisoformat(str(first_charge))
        if count_value in (None, "") and regular:
            balance, count = total, 0
            while balance > Decimal(count) * Decimal("0.005") and count < max_count:
                balance = (balance * (1 + rate)).quantize(CENT, rounding=ROUND_HALF_UP) - regular
                count += 1
            if balance > Decimal(count) * Decimal("0.005"):
                raise ValueError("A dívida exige mais de 120 parcelas")
        else:
            count = int(count_value)
            if Decimal(str(count_value)) != count:
                raise ValueError()
    except (TypeError, ValueError, InvalidOperation) as exc:
        raise ValueError("Revise a quantidade e a primeira cobrança") from exc
    if count < min_count or count > max_count:
        raise ValueError(f"A quantidade de parcelas deve ficar entre {min_count} e {max_count}")
    if regular is None:
        regular = (total * rate / (1 - (1 + rate) ** -count) if rate else total / count).quantize(CENT, rounding=ROUND_HALF_UP)
    fixed_principal = (total / count).quantize(CENT, rounding=ROUND_HALF_UP)
    group, balance, parts = uuid4().hex, total, []
    for number in range(1, count + 1):
        interest = (balance * rate).quantize(CENT, rounding=ROUND_HALF_UP)
        payment = (fixed_principal + interest if system == "sac" else regular) if number < count else balance + interest
        amortization = payment - interest
        if amortization <= 0 or (number < count and amortization >= balance):
            raise ValueError("Revise as parcelas: devem reduzir a dívida e terminar na quantidade informada")
        balance = (balance - amortization).quantize(CENT, rounding=ROUND_HALF_UP)
        money(payment, "Valor da parcela")
        parts.append({"group": group, "number": number, "count": count, "amount": float(payment),
                      "date": add_months(first, number - 1).isoformat(), "original_total": float(total),
                      "interest_rate": float(rate * 100), "interest": float(interest),
                      "amortization": float(amortization), "balance_after": float(balance)})
    return parts


def expense_finance(payload, expense_date, payment):
    """Validate shared finance metadata for both persistence backends."""
    kind = str(payload.get("financing_kind") or "purchase")
    if kind not in {"purchase", "loan", "asset", "debt"}:
        raise ValueError("Tipo de dívida inválido")
    parcelled = payload.get("installment") in (True, "true", "yes", "sim", "1")
    if parcelled and payment != "Crédito" and kind == "purchase":
        raise ValueError("Selecione Crédito para parcelar uma compra")
    scheduled = payload.get("scheduled") in (True, "true", "yes", "sim", "1")
    details = {"financing_kind": kind} if kind != "purchase" else {}
    if scheduled:
        if payment not in {"Pix", "Transferência"} or parcelled:
            raise ValueError("Agendamento disponível para Pix e transferência sem parcelamento")
        try:
            scheduled_date = date.fromisoformat(str(payload.get("scheduled_date")))
        except (TypeError, ValueError) as exc:
            raise ValueError("Informe a data do agendamento") from exc
        details["scheduled_date"] = scheduled_date.isoformat()
        expense_date = scheduled_date.isoformat()
    # A debt contract shares the expense calendar; metadata keeps the contract
    # and each installment's principal/interest for the debt charts.
    dedicated = payload.get("debt_entry") is True
    if dedicated:
        if kind == "purchase" or not parcelled:
            raise ValueError("Escolha o tipo e as parcelas do compromisso")
        system = str(payload.get("amortization_system") or "price")
        if system not in {"price", "sac"} or (kind != "asset" and system != "price"):
            raise ValueError("Sistema de amortização inválido para este compromisso")
        subtype = str(payload.get("debt_type") or "").strip()
        allowed_types = {
            "loan": {"Pessoal", "Consignado", "Com garantia", "Outro empréstimo"},
            "debt": {"Cartão de crédito", "Cheque especial", "Conta em atraso", "Acordo / renegociação", "Outra dívida"},
            "asset": {"Imóvel", "Veículo", "Outro bem"},
        }
        if subtype not in allowed_types[kind]:
            raise ValueError("Selecione o tipo de empréstimo, dívida ou financiamento")
        details.update(debt_entry=True, debt_type=subtype, amortization_system=system,
                       principal=float(money(payload["amount"])),
                       contract_date=date.fromisoformat(str(payload["date"])).isoformat())
        if kind == "asset":
            asset_name = str(payload.get("asset_name") or "").strip()
            if not asset_name or len(asset_name) > 100:
                raise ValueError("Informe o bem financiado (até 100 caracteres)")
            asset_value = money(payload.get("asset_value"), "Valor do bem")
            try:
                down = Decimal(str(payload.get("down_payment") or 0)).quantize(CENT, rounding=ROUND_HALF_UP)
            except (InvalidOperation, ValueError) as exc:
                raise ValueError("Entrada inválida") from exc
            if not down.is_finite() or down < 0 or down >= asset_value:
                raise ValueError("A entrada deve ser menor que o valor do bem")
            if asset_value - down != money(payload["amount"]):
                raise ValueError("O valor financiado deve ser o valor do bem menos a entrada")
            details.update(asset_name=asset_name, asset_value=float(asset_value), down_payment=float(down))
    parts = None
    if parcelled:
        parts = installment_plan(payload["amount"], payload.get("installment_count"),
                                 payload.get("first_charge_date") or expense_date,
                                 None if dedicated else payload.get("installment_amount"), payload.get("interest_rate", 0),
                                 details.get("amortization_system", "price"),
                                 max_count=600 if dedicated else 120, min_count=1 if dedicated else 2)
        details.update(financing_kind=kind, interest_rate=parts[0]["interest_rate"])
    return expense_date, parts, details
