import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src import auth, investments, statement_import, storage


class AppStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.patches = [patch.object(storage, "DATABASE", self.root / "meu_gasto.db"), patch.object(storage, "BACKUPS", self.root / "backups"), patch.object(auth, "AUTH_FILE", self.root / "auth.json")]
        for item in self.patches: item.start()
        storage.initialize()

    def tearDown(self):
        for item in reversed(self.patches): item.stop()
        self.temporary.cleanup()

    def expense(self, **changes):
        payload = {"date": "2026-10-13", "amount": 18.75, "where": "Restaurante", "category": "Alimentação", "payment": "Voucher", "description": "Almoço"}
        payload.update(changes)
        return payload

    def test_expense_income_and_budget_persist_with_backups(self):
        result = storage.add_expense(self.expense())
        storage.set_income({"month": "2026-10", "cash": 4200, "voucher": 850})
        storage.set_budget({"month": "2026-10", "category": "Alimentação", "limit": 700})
        self.assertEqual(18.75, storage.read_expenses()[0]["amount"])
        self.assertEqual({"cash": 4200.0, "voucher": 850.0}, storage.read_incomes()["2026-10"])
        self.assertEqual(700, storage.read_budgets()["2026-10"]["Alimentação"])
        self.assertEqual(result["id"], storage.read_expenses()[0]["id"])
        self.assertGreaterEqual(len(list(storage.BACKUPS.glob("*.db"))), 3)

    def test_duplicate_requires_confirmation(self):
        storage.add_expense(self.expense())
        with self.assertRaises(storage.DuplicateExpenseError): storage.add_expense(self.expense())
        storage.add_expense(self.expense(allow_duplicate=True))
        self.assertEqual(2, len(storage.read_expenses()))

    def test_rejects_invalid_financial_data(self):
        with self.assertRaises(ValueError): storage.add_expense(self.expense(amount=0))
        with self.assertRaises(ValueError): storage.set_income({"month": "errado", "cash": 1, "voucher": 0})
        with self.assertRaises(ValueError): storage.set_budget({"month": "2026-10", "category": "Inventada", "limit": 1})

    def test_investment_crud_and_calculations(self):
        stock = investments.create_investment({"type": "Ações", "symbol": "PETR4", "quantity": 10, "average_price": 30, "purchase_date": "2026-01-10", "current_price": 35})
        self.assertEqual(350, stock["current_value"])
        edited = investments.update_investment(stock["id"], {"type": "Ações", "symbol": "PETR4", "quantity": 12, "average_price": 30, "purchase_date": "2026-01-10", "current_price": 36})
        self.assertEqual(432, edited["current_value"])
        investments.delete_investment(stock["id"])
        self.assertEqual([], investments.portfolio()["investments"])

    def test_refreshes_quote_and_cdi(self):
        fixed = investments.create_investment({"type": "Renda fixa", "name": "CDB", "institution": "Banco", "amount_invested": 1000, "application_date": "2025-01-01", "profitability_type": "CDI", "contracted_rate": 110})
        stock = investments.create_investment({"type": "ETFs", "symbol": "BOVA11", "quantity": 2, "average_price": 100, "purchase_date": "2025-01-01"})
        result = investments.refresh_investments(quote_fetcher=lambda _: {"price": 120, "daily_change_percent": 1.25, "source": "Teste", "updated_at": "2026-10-15T12:00:00Z"}, cdi_fetcher=lambda: {"rate": 14.9, "source": "BCB", "updated_at": "2026-10-15T12:00:00Z"})
        items = {item["id"]: item for item in result["investments"]}
        self.assertGreater(items[fixed["id"]]["current_value"], 1000)
        self.assertEqual(240, items[stock["id"]]["current_value"])

    def test_password_hash_and_signed_session(self):
        auth.setup("uma-senha-segura", "uma-senha-segura")
        self.assertTrue(auth.verify_password("uma-senha-segura"))
        self.assertFalse(auth.verify_password("senha-incorreta"))
        token = auth.create_session(now=1000)
        self.assertTrue(auth.verify_session(token, now=1001))
        self.assertEqual(1, auth.session_user(token, now=1001))
        second_user_token = auth.create_session(42, now=1000)
        self.assertEqual(42, auth.session_user(second_user_token, now=1001))
        self.assertFalse(auth.verify_session(token + "x", now=1001))
        self.assertFalse(auth.verify_session(token, now=1000 + auth.SESSION_SECONDS + 1))

    def test_statement_csv_suggests_categories_and_leaves_unknown_for_review(self):
        raw = "data;descricao;valor\n13/10/2026;SUPERMERCADO CENTRAL;152,30\n14/10/2026;EMPRESA DESCONHECIDA;45,90\n".encode()
        items = statement_import.parse_statement("fatura.csv", raw)
        self.assertEqual(2, len(items))
        self.assertEqual("Mercado", items[0]["category"])
        self.assertEqual("", items[1]["category"])
        self.assertEqual(45.90, items[1]["amount"])

    def test_statement_ofx_marks_only_debits_by_default(self):
        raw = b"<OFX><STMTTRN><DTPOSTED>20261013<TRNAMT>-25.50<NAME>UBER</STMTTRN><STMTTRN><DTPOSTED>20261014<TRNAMT>100.00<NAME>ESTORNO</STMTTRN></OFX>"
        items = statement_import.parse_statement("conta.ofx", raw)
        self.assertEqual("Transporte", items[0]["category"])
        self.assertTrue(items[0]["selected"])
        self.assertFalse(items[1]["selected"])


if __name__ == "__main__": unittest.main()
