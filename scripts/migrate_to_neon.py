"""Migra uma única vez o banco SQLite local para o Neon."""

from argparse import ArgumentParser
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src import cloud_storage, storage  # noqa: E402


def main() -> None:
    parser = ArgumentParser(description="Migra os dados locais para o Neon")
    parser.add_argument("--allow-existing", action="store_true", help="Permite migrar para um banco que já contém lançamentos")
    options = parser.parse_args()
    if not os.environ.get("DATABASE_URL"):
        raise SystemExit("Defina DATABASE_URL somente neste terminal antes de executar a migração.")
    if not storage.DATABASE.exists():
        raise SystemExit(f"Banco local não encontrado: {storage.DATABASE}")
    cloud_storage.initialize()
    existing = cloud_storage.read_expenses()
    if existing and not options.allow_existing:
        raise SystemExit("O Neon já possui lançamentos. Migração cancelada para evitar duplicidade.")
    expenses = storage.read_expenses()
    for item in expenses:
        payload = {"date": item["date"], "amount": item["amount"], "where": item["where"], "category": item["category"], "payment": item["payment"], "description": item["description"], "allow_duplicate": True}
        cloud_storage.add_expense(payload)
    for month, values in storage.read_incomes().items():
        cloud_storage.set_income({"month": month, **values})
    for month, categories in storage.read_budgets().items():
        for category, limit in categories.items():
            cloud_storage.set_budget({"month": month, "category": category, "limit": limit})
    cloud_storage.save_investments(storage.load_investments())
    print(f"Migração concluída: {len(expenses)} gastos, {len(storage.read_incomes())} meses de renda e {len(storage.load_investments().get('investments', []))} investimentos.")


if __name__ == "__main__":
    main()
