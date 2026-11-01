import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.database import connection as db_connection
from src.domain.monthly_calculator import add_months
from src.services.finance_service import (
    client_debt_summary, create_client, create_movement, list_client_charges,
)


class MonthlyCalculatorTests(unittest.TestCase):
    def test_month_end_clamping(self):
        from datetime import date
        self.assertEqual(add_months(date(2026, 1, 31), 1, 31).isoformat(), "2026-02-28")
        self.assertEqual(add_months(date(2026, 2, 28), 1, 31).isoformat(), "2026-03-31")

    def test_payment_of_25_covers_two_months_and_partial_third(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(db_connection, "DB_PATH", Path(tmp) / "test.sqlite3"):
                db_connection.initialize_database()
                client_id = create_client("Cliente de prueba", 1000, "2026-11-01")
                movement_id = create_movement(
                    direction="income", counterparty="Cliente de prueba",
                    reason="Mensualidad", amount_cents=2500,
                    payment_date="2026-10-31", payment_method="Transferencia",
                    client_id=client_id, voucher_number="TEST-001", apply_to_monthly=True,
                )
                charges = list_client_charges(client_id, "2026-10-31")
                summary = client_debt_summary(client_id, "2026-10-31")
                self.assertEqual(len(charges), 3)
                self.assertEqual([c["remaining_cents"] for c in charges], [0, 0, 500])
                self.assertEqual(summary["fully_paid_months"], 2)
                self.assertEqual(summary["partial_months"], 1)
                self.assertEqual(summary["future_applied_cents"], 2500)
                self.assertEqual(summary["pending_cents"], 500)
                with db_connection.get_connection() as connection:
                    row = connection.execute("SELECT amount_cents FROM movements WHERE id=?", (movement_id,)).fetchone()
                self.assertEqual(row["amount_cents"], 2500)

    def test_expense_does_not_create_monthly_allocations(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(db_connection, "DB_PATH", Path(tmp) / "test.sqlite3"):
                db_connection.initialize_database()
                movement_id = create_movement(
                    direction="expense", counterparty="Proveedor", reason="Compra",
                    amount_cents=900, payment_date="2026-10-31",
                    payment_method="Efectivo",
                )
                with db_connection.get_connection() as connection:
                    count = connection.execute("SELECT COUNT(*) FROM payment_allocations WHERE movement_id=?", (movement_id,)).fetchone()[0]
                self.assertEqual(count, 0)

    def test_voided_payment_reopens_the_monthly_balance(self):
        from src.services.finance_service import void_movement
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(db_connection, "DB_PATH", Path(tmp) / "test.sqlite3"):
                db_connection.initialize_database()
                client_id = create_client("Cliente anulación", 1000, "2026-10-01")
                movement_id = create_movement(
                    direction="income", counterparty="Cliente anulación",
                    reason="Mensualidad", amount_cents=1000,
                    payment_date="2026-10-10", payment_method="Transferencia",
                    client_id=client_id, apply_to_monthly=True,
                )
                void_movement(movement_id, "Registro duplicado")
                charges = list_client_charges(client_id, "2026-10-31")
                self.assertEqual(charges[0]["remaining_cents"], 1000)

    def test_new_rate_applies_to_future_cycle_without_rewriting_paid_partial_periods(self):
        from src.services.finance_service import set_client_rate, generate_charges
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(db_connection, "DB_PATH", Path(tmp) / "test.sqlite3"):
                db_connection.initialize_database()
                client_id = create_client("Cliente tarifa", 1000, "2026-11-01")
                create_movement(
                    direction="income", counterparty="Cliente tarifa",
                    reason="Pago adelantado", amount_cents=2500,
                    payment_date="2026-10-31", payment_method="Transferencia",
                    client_id=client_id, apply_to_monthly=True,
                )
                set_client_rate(client_id, 1200, "2027-02-01")
                generate_charges(client_id, "2027-02-01")
                charges = list_client_charges(client_id, "2027-02-01")
                self.assertEqual(charges[0]["amount_due_cents"], 1000)
                self.assertEqual(charges[2]["amount_due_cents"], 1000)
                self.assertEqual(charges[2]["remaining_cents"], 500)
                self.assertEqual(charges[3]["amount_due_cents"], 1200)


if __name__ == "__main__":
    unittest.main()
