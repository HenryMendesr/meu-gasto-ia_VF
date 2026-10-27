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
        self.assertEqual({"cash": 4200.0, "voucher": 850.0, "payday": None, "source": ""}, storage.read_incomes()["2026-10"])
        self.assertEqual(700, storage.read_budgets()["2026-10"]["Alimentação"])
        self.assertEqual(result["id"], storage.read_expenses()[0]["id"])
        self.assertGreaterEqual(len(list(storage.BACKUPS.glob("*.db"))), 3)

    def test_duplicate_requires_confirmation(self):
        storage.add_expense(self.expense())
        with self.assertRaises(storage.DuplicateExpenseError): storage.add_expense(self.expense())
        storage.add_expense(self.expense(allow_duplicate=True))
        self.assertEqual(2, len(storage.read_expenses()))

    def test_credit_installments_follow_months_and_preserve_total(self):
        result = storage.add_expense(self.expense(
            amount=100, payment="Crédito", installment=True, installment_count=3,
            installment_amount=33.33, first_charge_date="2026-01-31",
        ))
        items = storage.read_expenses()
        self.assertEqual(3, len(items))
        self.assertEqual(["2026-01-31", "2026-02-28", "2026-03-31"], [item["date"] for item in items])
        self.assertEqual(100, round(sum(item["amount"] for item in items), 2))
        self.assertEqual([1, 2, 3], [item["installment_number"] for item in items])
        self.assertTrue(result["installment_group"])

    def test_financed_loan_preserves_rate_and_includes_interest(self):
        storage.add_expense(self.expense(amount=1000, payment="Transferência", financing_kind="loan",
                            installment=True, installment_count=12, interest_rate="2,5"))
        items = storage.read_expenses()
        self.assertEqual(12, len(items))
        self.assertAlmostEqual(97.49, items[0]["amount"])
        self.assertGreater(sum(item["amount"] for item in items), 1000)
        self.assertEqual({"financing_kind": "loan", "interest_rate": 2.5}, items[0]["finance"])
        self.assertTrue(all(item["original_total"] == 1000 for item in items))

    def test_scheduled_pix_is_saved_on_scheduled_date_and_can_be_changed(self):
        payload = self.expense(payment="Pix", scheduled=True, scheduled_date="2027-01-15")
        result = storage.add_expense(payload)
        item = storage.read_expenses()[0]
        self.assertEqual("2027-01-15", item["date"])
        self.assertEqual("2027-01-15", item["finance"]["scheduled_date"])
        storage.update_expense(result["id"], {**payload, "scheduled_date": "2027-02-01"})
        self.assertEqual("2027-02-01", storage.read_expenses()[0]["date"])
        storage.update_expense(result["id"], {**payload, "scheduled": False})
        self.assertEqual({}, storage.read_expenses()[0]["finance"])

    def test_rejects_schedule_with_invalid_date_or_incompatible_payment(self):
        for changes in ({"payment": "Pix", "scheduled_date": "invalid"},
                        {"payment": "Crédito", "scheduled_date": "2027-01-01"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                storage.add_expense(self.expense(scheduled=True, **changes))

    def test_debt_contract_saves_breakdown_and_automatically_populates_calendar(self):
        created = storage.add_expense(self.expense(
            amount=240000, payment="Transferência", financing_kind="asset",
            debt_entry=True, debt_type="Imóvel", asset_name="Apartamento",
            asset_value=300000, down_payment=60000, amortization_system="sac",
            installment=True, installment_count=360, interest_rate="0,8",
            first_charge_date="2027-01-31"))
        items = storage.read_expenses()
        self.assertEqual(360, len(items))
        self.assertEqual("2027-02-28", items[1]["date"])
        self.assertEqual(1920, items[0]["finance"]["interest_part"])
        self.assertEqual(666.67, items[0]["finance"]["principal_part"])
        self.assertEqual(0, items[-1]["finance"]["balance_after"])
        self.assertEqual(60000, items[0]["finance"]["down_payment"])
        self.assertEqual(240000, round(sum(item["finance"]["principal_part"] for item in items), 2))
        storage.delete_expense(created["id"], scope="all")
        self.assertEqual([], storage.read_expenses())

    def test_installment_update_and_delete_can_affect_series(self):
        storage.add_expense(self.expense(amount=90, payment="Crédito", installment=True, installment_count=3, first_charge_date="2026-10-13"))
        second = storage.read_expenses()[1]
        storage.update_expense(second["id"], self.expense(amount=31, payment="Crédito", description="Editado", scope="all"))
        self.assertEqual([31, 31, 31], [item["amount"] for item in storage.read_expenses()])
        storage.delete_expense(second["id"], scope="all")
        self.assertEqual([], storage.read_expenses())

    def test_rejects_invalid_financial_data(self):
        with self.assertRaises(ValueError): storage.add_expense(self.expense(amount=0))
        with self.assertRaises(ValueError): storage.set_income({"month": "errado", "cash": 1, "voucher": 0})
        with self.assertRaises(ValueError): storage.set_budget({"month": "2026-10", "category": "Inventada", "limit": 1})

    def test_budget_category_and_expense_changes_recalculate_source_data(self):
        storage.add_category("Gasolina")
        self.assertIn("Gasolina", storage.read_categories())
        storage.set_budget({"month": "2026-10", "category": "Gasolina", "limit": 500})
        created = storage.add_expense(self.expense(category="Gasolina", amount=320, payment="Crédito"))
        storage.rename_category("Gasolina", "Combustível")
        self.assertIn("Combustível", storage.read_categories())
        storage.update_expense(created["id"], self.expense(category="Combustível", amount=450, payment="Crédito"))
        month_expenses = [item for item in storage.read_expenses() if item["date"].startswith("2026-10")]
        self.assertEqual(450, sum(item["amount"] for item in month_expenses if item["category"] == "Combustível"))
        storage.delete_expense(created["id"])
        self.assertEqual([], storage.read_expenses())
        storage.delete_budget("2026-10", "Combustível")
        self.assertNotIn("Combustível", storage.read_budgets().get("2026-10", {}))
        storage.delete_category("Combustível")
        self.assertNotIn("Combustível", storage.read_categories())

    def test_category_with_expenses_cannot_be_deleted(self):
        storage.add_category("Gasolina")
        storage.add_expense(self.expense(category="Gasolina"))
        with self.assertRaises(ValueError):
            storage.delete_category("Gasolina")

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

    def test_individual_investment_history_is_calculated(self):
        stock = investments.create_investment({"type": "Ações", "symbol": "PETR4", "quantity": 2, "average_price": 30, "purchase_date": "2025-01-01"})
        history = investments.investment_history(stock["id"], "1m", market_fetcher=lambda symbol, period: {
            "source": "Teste", "points": [{"date": "2026-10-01", "price": 31}, {"date": "2026-10-15", "price": 34}],
        })
        self.assertEqual("PETR4", history["label"])
        self.assertEqual(68, history["points"][-1]["value"])
        fixed = investments.create_investment({"type": "Renda fixa", "name": "CDB", "institution": "Banco", "amount_invested": 1000, "application_date": "2025-01-01", "profitability_type": "Prefixado", "contracted_rate": 12})
        fixed_history = investments.investment_history(fixed["id"], "1y")
        self.assertGreaterEqual(len(fixed_history["points"]), 2)
        self.assertGreater(fixed_history["points"][-1]["value"], fixed_history["points"][0]["value"])

    def test_stock_market_history_is_independent_of_purchase_and_gains_start_at_purchase(self):
        stock = investments.create_investment({"type": "Ações", "symbol": "PETR4", "quantity": 2, "average_price": 30, "purchase_date": "2025-01-02"})
        def history(symbol, period):
            self.assertEqual("all", period)
            return {"source": "Teste", "points": [
                {"date": "2025-01-01", "price": 20},
                {"date": "2025-01-02", "price": 30},
                {"date": "2025-01-03", "price": 33},
                {"date": "2099-01-01", "price": 99}]}
        result = investments.investment_history(stock["id"], "all", market_fetcher=history)
        self.assertEqual(["2025-01-01", "2025-01-02", "2025-01-03"], [point["date"] for point in result["points"]])
        self.assertEqual(["2025-01-02", "2025-01-03"], [point["date"] for point in result["gain_points"]])
        self.assertEqual(66, result["points"][-1]["value"])
        self.assertEqual(6, result["profit_loss"])
        self.assertEqual(10, result["historical_return_percent"])
        with self.assertRaises(ValueError):
            investments.investment_history(stock["id"], "invalid", market_fetcher=history)

    def test_investment_rejects_accidentally_truncated_year(self):
        with self.assertRaises(ValueError):
            investments.iso_date("0026-10-27", "Data da compra")
        self.assertEqual("2026-10-27", investments.iso_date("2026-10-27", "Data da compra"))

    def test_fixed_history_all_starts_at_application(self):
        item = {"application_date": "2010-01-01", "amount_invested": 1000,
                "profitability_type": "Prefixado", "contracted_rate": 10}
        points = investments.fixed_income_history(item, "all")
        self.assertEqual("2010-01-01", points[0]["date"])
        self.assertEqual(1000, points[0]["value"])
        self.assertEqual(investments.investment_today().isoformat(), points[-1]["date"])

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
        self.assertEqual("expense", items[0]["kind"])
        self.assertEqual("income", items[1]["kind"])
        self.assertTrue(items[1]["selected"])

    def test_statement_ignores_daily_balance_and_classifies_income(self):
        raw = b"<OFX><STMTTRN><DTPOSTED>20261013<TRNAMT>2500.00<NAME>SALARIO</STMTTRN><STMTTRN><DTPOSTED>20261013<TRNAMT>4321.10<NAME>SALDO DO DIA</STMTTRN></OFX>"
        items = statement_import.parse_statement("conta.ofx", raw)
        self.assertEqual(1, len(items))
        self.assertEqual("income", items[0]["kind"])
        self.assertEqual("Salário", items[0]["category"])

    def test_statement_analysis_finds_income_recurring_and_own_transfer(self):
        items = [
            statement_import.item("2026-09-05", "SALARIO EMPRESA XPTO", 3000),
            statement_import.item("2026-10-05", "SALARIO EMPRESA XPTO", 3150),
            statement_import.item("2026-09-10", "NETFLIX", -39.90),
            statement_import.item("2026-10-10", "NETFLIX", -39.90),
            statement_import.item("2026-10-12", "PIX ENTRE CONTAS", -500),
        ]
        analysis = statement_import.analyze([item for item in items if item])
        self.assertEqual(5, analysis["income_suggestion"]["day"])
        self.assertTrue(analysis["income_suggestion"]["varies"])
        self.assertTrue(any(item["recurring"] for item in analysis["items"] if "NETFLIX" in item["where"]))
        transfer = next(item for item in analysis["items"] if "ENTRE CONTAS" in item["where"])
        self.assertEqual("transfer", transfer["kind"])
        self.assertFalse(transfer["selected"])

    def test_statement_reads_separate_debit_and_credit_columns(self):
        raw = "data;descricao;debito;credito\n05/10/26;SALARIO EMPRESA;;3000,00\n06/10/26;MERCADO;120,50;\n".encode()
        items = statement_import.parse_statement("conta.csv", raw)
        self.assertEqual(["income", "expense"], [item["kind"] for item in items])

    def test_income_entry_is_stored_separately_from_expenses(self):
        storage.add_income_entry({"date": "2026-10-13", "amount": 2500, "where": "Empresa", "category": "Salário", "description": "Folha"})
        self.assertEqual([], storage.read_expenses())
        self.assertEqual("Salário", storage.read_income_entries()[0]["category"])


if __name__ == "__main__": unittest.main()
