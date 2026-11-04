import tempfile
import unittest
from datetime import date
from pathlib import Path
from unittest.mock import patch

from src.database import connection as db_connection
from src.services.finance_service import create_client, create_movement, dashboard_visual_data, search_movements


class DashboardVisualDataTests(unittest.TestCase):
    def test_dashboard_aggregates_monthly_trends_and_expense_categories(self):
        today = date.today()
        month = today.strftime("%Y-%m")
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(db_connection, "DB_PATH", Path(tmp) / "dashboard.sqlite3"):
                db_connection.initialize_database()
                create_movement(
                    direction="income", counterparty="Cliente A", reason="Servicio",
                    amount_cents=12500, payment_date=today.isoformat(),
                    payment_method="Transferencia", category="Ingresos",
                )
                create_movement(
                    direction="expense", counterparty="Supermercado", reason="Compra de alimentos",
                    amount_cents=4500, payment_date=today.isoformat(),
                    payment_method="Tarjeta", category="Comida",
                )
                create_movement(
                    direction="expense", counterparty="Gasolinera", reason="Combustible",
                    amount_cents=2500, payment_date=today.isoformat(),
                    payment_method="Tarjeta", category="Transporte",
                )

                data = dashboard_visual_data(chart_month=month)
                self.assertEqual(data["balance_cents"], 5500)
                self.assertEqual(data["income_month_cents"], 12500)
                self.assertEqual(data["expenses_month_cents"], 7000)
                current = next(item for item in data["series"] if item["month"] == month)
                self.assertEqual(current["income_cents"], 12500)
                self.assertEqual(current["expenses_cents"], 7000)
                self.assertEqual(
                    data["categories"],
                    [
                        {"category": "Comida", "amount_cents": 4500},
                        {"category": "Transporte", "amount_cents": 2500},
                    ],
                )
                filtered = dashboard_visual_data(
                    chart_month=month, table_month=month, category="Comida"
                )
                self.assertEqual(len(filtered["recent"]), 1)
                self.assertEqual(filtered["recent"][0]["counterparty"], "Supermercado")

    def test_legacy_database_gets_default_category_without_losing_movements(self):
        with tempfile.TemporaryDirectory() as tmp:
            db_path = Path(tmp) / "legacy.sqlite3"
            legacy_schema = Path(tmp) / "legacy_schema.sql"
            current_schema = db_connection.SCHEMA_PATH.read_text(encoding="utf-8")
            legacy_schema.write_text(
                current_schema.replace("    category TEXT NOT NULL DEFAULT 'Otros',\n", ""),
                encoding="utf-8",
            )
            with patch.object(db_connection, "DB_PATH", db_path):
                with patch.object(db_connection, "SCHEMA_PATH", legacy_schema):
                    first_migrations = db_connection.initialize_database()
                    with db_connection.get_connection() as connection:
                        cursor = connection.execute(
                            """INSERT INTO movements
                               (direction, counterparty, reason, amount_cents, payment_date, payment_method)
                               VALUES ('expense','Proveedor','Factura anterior',1000,?,'Transferencia')""",
                            (date.today().isoformat(),),
                        )
                        movement_id = cursor.lastrowid
                self.assertTrue(any("movements.category" in item for item in first_migrations))
                with patch.object(db_connection, "SCHEMA_PATH", Path(__file__).resolve().parents[1] / "src" / "database" / "schema.sql"):
                    db_connection.initialize_database()
                with db_connection.get_connection() as connection:
                    row = connection.execute(
                        "SELECT id, category FROM movements WHERE id=?", (movement_id,)
                    ).fetchone()
                self.assertEqual(row["category"], "Otros")

    def test_movement_search_filters_by_client_category_and_date_range(self):
        with tempfile.TemporaryDirectory() as tmp:
            with patch.object(db_connection, "DB_PATH", Path(tmp) / "search.sqlite3"):
                db_connection.initialize_database()
                client_id = create_client("Cliente filtro", 2300, "2026-01-01")
                other_client_id = create_client("Otro cliente", 1500, "2026-01-01")
                create_movement(
                    direction="income", counterparty="Cliente filtro", reason="Mensualidad noviembre",
                    amount_cents=2300, payment_date="2026-11-03", payment_method="Transferencia",
                    client_id=client_id, category="Ingresos",
                )
                create_movement(
                    direction="income", counterparty="Otro cliente", reason="Mensualidad noviembre",
                    amount_cents=1500, payment_date="2026-11-04", payment_method="Transferencia",
                    client_id=other_client_id, category="Ingresos",
                )
                create_movement(
                    direction="expense", counterparty="Supermercado", reason="Compra",
                    amount_cents=500, payment_date="2026-11-05", payment_method="Tarjeta",
                    category="Comida",
                )
                rows = search_movements(
                    client_id=client_id, category="Ingresos",
                    date_from="2026-11-01", date_to="2026-11-30", include_void=True,
                )
                self.assertEqual(len(rows), 1)
                self.assertEqual(rows[0]["counterparty"], "Cliente filtro")

                outside_period = search_movements(
                    category="Comida", date_from="2026-12-01", date_to="2026-12-31", include_void=True,
                )
                self.assertEqual(outside_period, [])


if __name__ == "__main__":
    unittest.main()
