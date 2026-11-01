import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.database import connection as db_connection


class DatabaseMigrationTests(unittest.TestCase):
    def test_adds_missing_client_columns_and_preserves_existing_rows(self):
        with tempfile.TemporaryDirectory() as tmp:
            database_path = Path(tmp) / "legacy.sqlite3"
            legacy = sqlite3.connect(database_path)
            legacy.execute(
                """CREATE TABLE clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    name TEXT NOT NULL,
                    phone TEXT,
                    email TEXT,
                    billing_day INTEGER NOT NULL DEFAULT 1,
                    first_billing_date TEXT NOT NULL,
                    is_active INTEGER NOT NULL DEFAULT 1,
                    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
                )"""
            )
            legacy.execute(
                "INSERT INTO clients(name, phone, first_billing_date) VALUES (?, ?, ?)",
                ("Cliente anterior", "0990000000", "2026-01-15"),
            )
            legacy.commit()
            legacy.close()

            with patch.object(db_connection, "DB_PATH", database_path):
                applied = db_connection.initialize_database()
                with db_connection.get_connection() as connection:
                    row = connection.execute(
                        "SELECT id, name, phone, identification, notes FROM clients WHERE id=1"
                    ).fetchone()
                    columns = {
                        item["name"]
                        for item in connection.execute("PRAGMA table_info(clients)").fetchall()
                    }

                self.assertEqual(row["name"], "Cliente anterior")
                self.assertEqual(row["phone"], "0990000000")
                self.assertIsNone(row["identification"])
                self.assertIsNone(row["notes"])
                self.assertIn("clients.identification", applied)
                self.assertIn("clients.notes", applied)
                self.assertIn("identification", columns)
                self.assertTrue(list(Path(tmp).glob("*_antes_actualizacion_*.sqlite3")))

                # Reopening is idempotent and does not create another migration backup.
                second_run = db_connection.initialize_database()
                self.assertEqual(second_run, [])


if __name__ == "__main__":
    unittest.main()
