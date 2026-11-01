import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.database import connection as db_connection
from src.domain.monthly_calculator import add_months
from src.services.finance_service import (
    client_debt_summary, client_payment_history, create_client, create_movement,
    find_voucher_matches, list_client_charges,
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

    def test_late_entered_backdated_payment_rebuilds_allocations_in_payment_date_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(db_connection, "DB_PATH", Path(tmp) / "test.sqlite3"):
                db_connection.initialize_database()
                client_id = create_client("Cliente orden", 1000, "2026-10-01")
                later_payment = create_movement(
                    direction="income", counterparty="Cliente orden", reason="Pago noviembre",
                    amount_cents=1000, payment_date="2026-11-10", payment_method="Transferencia",
                    client_id=client_id, apply_to_monthly=True,
                )
                earlier_payment = create_movement(
                    direction="income", counterparty="Cliente orden", reason="Pago octubre ingresado tarde",
                    amount_cents=1000, payment_date="2026-10-10", payment_method="Transferencia",
                    client_id=client_id, apply_to_monthly=True,
                )
                with db_connection.get_connection() as connection:
                    allocations = connection.execute(
                        """SELECT pa.movement_id, ch.period_start, pa.amount_allocated_cents
                           FROM payment_allocations pa
                           JOIN monthly_charges ch ON ch.id=pa.charge_id
                           WHERE pa.movement_id IN (?, ?)""",
                        (later_payment, earlier_payment),
                    ).fetchall()
                allocation_map = {int(row["movement_id"]): row["period_start"] for row in allocations}
                self.assertEqual(allocation_map[earlier_payment], "2026-10-01")
                self.assertEqual(allocation_map[later_payment], "2026-11-01")

    def test_voiding_older_payment_reallocates_later_payment_to_oldest_due_month(self):
        from src.services.finance_service import void_movement
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(db_connection, "DB_PATH", Path(tmp) / "test.sqlite3"):
                db_connection.initialize_database()
                client_id = create_client("Cliente mover", 1000, "2026-10-01")
                old_payment = create_movement(
                    direction="income", counterparty="Cliente mover", reason="Pago octubre",
                    amount_cents=1000, payment_date="2026-10-10", payment_method="Transferencia",
                    client_id=client_id, apply_to_monthly=True,
                )
                new_payment = create_movement(
                    direction="income", counterparty="Cliente mover", reason="Pago noviembre",
                    amount_cents=1000, payment_date="2026-11-10", payment_method="Transferencia",
                    client_id=client_id, apply_to_monthly=True,
                )
                void_movement(old_payment, "Pago duplicado")
                charges = list_client_charges(client_id, "2026-11-30")
                self.assertEqual([row["remaining_cents"] for row in charges[:2]], [0, 1000])
                with db_connection.get_connection() as connection:
                    allocation = connection.execute(
                        """SELECT ch.period_start FROM payment_allocations pa
                           JOIN monthly_charges ch ON ch.id=pa.charge_id
                           WHERE pa.movement_id=?""",
                        (new_payment,),
                    ).fetchone()
                self.assertEqual(allocation["period_start"], "2026-10-01")

    def test_historical_balance_ignores_payments_with_later_payment_dates(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(db_connection, "DB_PATH", Path(tmp) / "test.sqlite3"):
                db_connection.initialize_database()
                client_id = create_client("Cliente histórico", 1000, "2026-10-01")
                create_movement(
                    direction="income", counterparty="Cliente histórico", reason="Pago octubre",
                    amount_cents=1000, payment_date="2026-10-10", payment_method="Transferencia",
                    client_id=client_id, apply_to_monthly=True,
                )
                create_movement(
                    direction="income", counterparty="Cliente histórico", reason="Pago noviembre",
                    amount_cents=1000, payment_date="2026-11-10", payment_method="Transferencia",
                    client_id=client_id, apply_to_monthly=True,
                )
                october = client_debt_summary(client_id, "2026-10-31")
                november = client_debt_summary(client_id, "2026-11-30")
                self.assertEqual(october["total_received_cents"], 1000)
                self.assertEqual(october["fully_paid_months"], 1)
                self.assertEqual(october["pending_cents"], 0)
                self.assertEqual(november["total_received_cents"], 2000)
                self.assertEqual(november["fully_paid_months"], 2)
                self.assertEqual(len(client_payment_history(client_id, "2026-10-31")), 1)

    def test_duplicate_voucher_lookup_is_case_insensitive(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(db_connection, "DB_PATH", Path(tmp) / "test.sqlite3"):
                db_connection.initialize_database()
                create_movement(
                    direction="expense", counterparty="Proveedor", reason="Pago",
                    amount_cents=500, payment_date="2026-10-10", payment_method="Transferencia",
                    voucher_number="AbC-123",
                )
                matches = find_voucher_matches(" abc-123 ")
                self.assertEqual(len(matches), 1)
                self.assertEqual(matches[0]["voucher_number"], "AbC-123")

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
