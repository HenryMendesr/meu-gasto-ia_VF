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
    if result <= 0 or result > Decimal("10000000"):
        raise ValueError(f"{label} deve ser maior que zero")
    return result


def add_months(value: date, months: int) -> date:
    index = value.year * 12 + value.month - 1 + months
    year, month_index = divmod(index, 12)
    month = month_index + 1
    return date(year, month, min(value.day, monthrange(year, month)[1]))


def installment_plan(total_value, count_value, first_charge, installment_value=None) -> list[dict]:
    total = money(total_value, "Valor total")
    try:
        count = int(count_value)
        first = date.fromisoformat(str(first_charge))
    except (TypeError, ValueError) as exc:
        raise ValueError("Revise a quantidade e a primeira cobrança") from exc
    if count < 2 or count > 120:
        raise ValueError("A quantidade de parcelas deve ficar entre 2 e 120")
    regular = money(installment_value, "Valor da parcela") if installment_value not in (None, "") else (total / count).quantize(CENT, rounding=ROUND_HALF_UP)
    last = total - regular * (count - 1)
    if last <= 0:
        raise ValueError("O valor das parcelas ultrapassa o total da compra")
    group = uuid4().hex
    return [{"group": group, "number": number, "count": count, "amount": float(regular if number < count else last),
             "date": add_months(first, number - 1).isoformat(), "original_total": float(total)} for number in range(1, count + 1)]
