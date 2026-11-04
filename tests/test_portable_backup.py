import sqlite3
import tempfile
import unittest
import zipfile
import json
from pathlib import Path
from unittest.mock import patch

from src.database import connection as db_connection
from src.services import backup_service
from src.services.finance_service import create_client, create_movement


class PortableBackupTests(unittest.TestCase):
    def test_backup_restores_database_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            db_path = data / "gestor.sqlite3"
            evidence = data / "evidencias"
            evidence.mkdir()
            backups = data / "backups"
            with patch.object(db_connection, "DB_PATH", db_path), \
                 patch.object(backup_service, "DB_PATH", db_path), \
                 patch.object(backup_service, "DATA_DIR", data), \
                 patch.object(backup_service, "EVIDENCE_DIR", evidence), \
                 patch.object(backup_service, "BACKUP_DIR", backups):
                db_connection.initialize_database()
                client_id = create_client("Cliente traslado", 2300, "2026-01-01")
                create_movement(
                    direction="income", counterparty="Cliente traslado", reason="Mensualidad",
                    amount_cents=2300, payment_date="2026-11-01", payment_method="Transferencia",
                    client_id=client_id, apply_to_monthly=True,
                )
                attachment = evidence / "income" / "voucher.txt"
                attachment.parent.mkdir(parents=True)
                attachment.write_text("voucher original", encoding="utf-8")
                package = root / "traslado.gfbak"
                backup_service.create_portable_backup(package)

                create_movement(
                    direction="expense", counterparty="Proveedor", reason="Pago posterior",
                    amount_cents=500, payment_date="2026-11-02", payment_method="Efectivo",
                )
                attachment.write_text("contenido modificado", encoding="utf-8")

                result = backup_service.restore_portable_backup(package)
                with db_connection.get_connection() as connection:
                    movements = connection.execute("SELECT COUNT(*) FROM movements").fetchone()[0]
                    client_count = connection.execute("SELECT COUNT(*) FROM clients").fetchone()[0]
                self.assertEqual(movements, 1)
                self.assertEqual(client_count, 1)
                self.assertEqual(attachment.read_text(encoding="utf-8"), "voucher original")
                self.assertTrue(result["rollback_backup"])
                self.assertTrue(Path(result["rollback_backup"]).exists())

    def test_rejects_path_traversal_in_backup_manifest(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.gfbak"
            with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                archive.writestr("database.sqlite3", b"not a database")
                manifest = {
                    "format": backup_service.FORMAT_NAME,
                    "format_version": backup_service.FORMAT_VERSION,
                    "database": {"sha256": "invalid"},
                    "evidence": [{"path": "../outside.txt", "size": 1, "sha256": "x"}],
                }
                archive.writestr("manifest.json", json.dumps(manifest))
            with self.assertRaises(ValueError):
                backup_service.inspect_portable_backup(path)

    def test_failed_restore_rolls_back_database_and_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            data = root / "data"
            data.mkdir()
            db_path = data / "gestor.sqlite3"
            evidence = data / "evidencias"
            evidence.mkdir()
            backups = data / "backups"
            with patch.object(db_connection, "DB_PATH", db_path), \
                 patch.object(backup_service, "DB_PATH", db_path), \
                 patch.object(backup_service, "DATA_DIR", data), \
                 patch.object(backup_service, "EVIDENCE_DIR", evidence), \
                 patch.object(backup_service, "BACKUP_DIR", backups):
                db_connection.initialize_database()
                create_movement(
                    direction="expense", counterparty="Proveedor original", reason="Pago original",
                    amount_cents=1000, payment_date="2026-11-01", payment_method="Efectivo",
                )
                original_file = evidence / "original.txt"
                original_file.write_text("archivo original", encoding="utf-8")
                package = root / "restore.gfbak"
                backup_service.create_portable_backup(package)

                create_movement(
                    direction="expense", counterparty="Proveedor actual", reason="No perder",
                    amount_cents=2000, payment_date="2026-11-02", payment_method="Transferencia",
                )
                original_file.write_text("archivo actual", encoding="utf-8")

                real_replace = backup_service.os.replace
                calls = {"count": 0}
                def fail_database_swap(source, destination):
                    calls["count"] += 1
                    if calls["count"] == 3:
                        raise OSError("Fallo simulado al reemplazar la base de datos")
                    return real_replace(source, destination)

                with patch.object(backup_service.os, "replace", side_effect=fail_database_swap):
                    with self.assertRaises(OSError):
                        backup_service.restore_portable_backup(package)

                with db_connection.get_connection() as connection:
                    count = connection.execute("SELECT COUNT(*) FROM movements").fetchone()[0]
                self.assertEqual(count, 2)
                self.assertEqual(original_file.read_text(encoding="utf-8"), "archivo actual")


if __name__ == "__main__":
    unittest.main()
