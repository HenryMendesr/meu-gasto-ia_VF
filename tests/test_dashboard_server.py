import shutil
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from zipfile import ZipFile

from src import dashboard_server as server


class DashboardStorageTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.root = Path(self.temporary.name)
        self.workbook = self.root / "Controle_Gastos_Automatico.xlsm"
        shutil.copy2(server.ROOT / "excel/Controle_Gastos_Automatico.xlsm", self.workbook)
        self.xlsm_patch = patch.object(server, "XLSM", self.workbook)
        self.backup_patch = patch.object(server, "BACKUPS", self.root / "backups")
        self.run_patch = patch.object(server.subprocess, "run")
        self.xlsm_patch.start()
        self.backup_patch.start()
        self.run_patch.start()

    def tearDown(self):
        self.run_patch.stop()
        self.backup_patch.stop()
        self.xlsm_patch.stop()
        self.temporary.cleanup()

    def payload(self, **changes):
        data = {
            "date": "2026-10-13",
            "amount": 18.75,
            "where": "Restaurante de teste",
            "category": "Alimentação",
            "payment": "Voucher",
            "description": "Almoço",
        }
        data.update(changes)
        return data

    def test_adds_expense_and_creates_valid_backup(self):
        before = len(server.read_expenses())
        result = server.add_expense(self.payload())
        after = server.read_expenses()

        self.assertEqual(before + 1, len(after))
        self.assertEqual("Voucher", after[-1]["payment"])
        self.assertEqual(18.75, after[-1]["amount"])
        self.assertEqual(result["row"], after[-1]["row"])
        backup = server.BACKUPS / result["backup"]
        self.assertTrue(backup.is_file())
        with ZipFile(backup) as archive:
            self.assertIsNone(archive.testzip())

    def test_rejects_exact_duplicate_unless_confirmed(self):
        payload = self.payload(where="Mesmo gasto", amount=27.30)
        server.add_expense(payload)
        with self.assertRaises(server.DuplicateExpenseError):
            server.add_expense(payload)

        payload["allow_duplicate"] = True
        server.add_expense(payload)
        matches = [item for item in server.read_expenses() if item["where"] == "Mesmo gasto"]
        self.assertEqual(2, len(matches))

    def test_rejects_invalid_category_and_amount(self):
        with self.assertRaises(ValueError):
            server.add_expense(self.payload(category="Categoria inventada"))
        with self.assertRaises(ValueError):
            server.add_expense(self.payload(amount=0))

    def test_persists_cash_and_voucher_income_in_excel(self):
        result = server.set_income({"month": "2026-11", "cash": 4200, "voucher": 850})
        incomes = server.read_incomes()

        self.assertEqual({"cash": 4200.0, "voucher": 850.0}, incomes["2026-11"])
        self.assertTrue((server.BACKUPS / result["backup"]).is_file())

    def test_income_and_voucher_expense_survive_sequential_saves(self):
        server.set_income({"month": "2026-12", "cash": 5100, "voucher": 920})
        server.add_expense(self.payload(date="2026-12-08", amount=32.40))

        self.assertEqual(
            {"cash": 5100.0, "voucher": 920.0},
            server.read_incomes()["2026-12"],
        )
        saved = [item for item in server.read_expenses() if item["date"] == "2026-12-08"]
        self.assertEqual(1, len(saved))
        self.assertEqual("Voucher", saved[0]["payment"])
        self.assertEqual(32.40, saved[0]["amount"])

    def test_rejects_invalid_income(self):
        with self.assertRaises(ValueError):
            server.set_income({"month": "novembro", "cash": 1000, "voucher": 0})
        with self.assertRaises(ValueError):
            server.set_income({"month": "2026-11", "cash": -1, "voucher": 0})

    def test_persists_monthly_category_budget(self):
        result = server.set_budget({"month": "2026-10", "category": "Alimentação", "limit": 700})
        budgets = server.read_budgets()

        self.assertEqual(700.0, budgets["2026-10"]["Alimentação"])
        self.assertEqual("Alimentação", result["category"])
        self.assertTrue((server.BACKUPS / result["backup"]).is_file())

    def test_rejects_invalid_budget(self):
        with self.assertRaises(ValueError):
            server.set_budget({"month": "2026-10", "category": "Inventada", "limit": 100})
        with self.assertRaises(ValueError):
            server.set_budget({"month": "2026-10", "category": "Lazer", "limit": -1})


if __name__ == "__main__":
    unittest.main()
