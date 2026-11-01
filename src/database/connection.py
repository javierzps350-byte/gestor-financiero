from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path

from src.config import DB_PATH, ROOT_DIR

SCHEMA_PATH = ROOT_DIR / "src" / "database" / "schema.sql"

# Column additions are safe, additive migrations. They preserve existing rows.
# This matters because CREATE TABLE IF NOT EXISTS does not update an older table.
MIGRATIONS: dict[str, dict[str, str]] = {
    "clients": {
        "identification": "TEXT",
        "notes": "TEXT",
    },
    "movements": {
        "apply_to_monthly": "INTEGER NOT NULL DEFAULT 0",
        "status": "TEXT NOT NULL DEFAULT 'active'",
        "void_reason": "TEXT",
        "voided_at": "TEXT",
    },
    "monthly_charges": {
        "created_at": "TEXT",
    },
    "payment_allocations": {
        "created_at": "TEXT",
    },
    "evidence_files": {
        "stored_name": "TEXT",
        "relative_path": "TEXT",
        "mime_type": "TEXT",
        "file_size_bytes": "INTEGER",
        "sha256": "TEXT",
        "added_at": "TEXT",
    },
}


def connect() -> sqlite3.Connection:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(DB_PATH, timeout=15)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    connection.execute("PRAGMA busy_timeout = 15000")
    connection.execute("PRAGMA journal_mode = WAL")
    return connection


@contextmanager
def get_connection():
    connection = connect()
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()


def _table_columns(connection: sqlite3.Connection, table: str) -> set[str]:
    rows = connection.execute(f'PRAGMA table_info("{table}")').fetchall()
    return {str(row["name"]) for row in rows}


def _missing_migrations(connection: sqlite3.Connection) -> dict[str, dict[str, str]]:
    missing: dict[str, dict[str, str]] = {}
    existing_tables = {
        row["name"]
        for row in connection.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()
    }
    for table, columns in MIGRATIONS.items():
        if table not in existing_tables:
            continue
        existing_columns = _table_columns(connection, table)
        absent = {name: sql_type for name, sql_type in columns.items() if name not in existing_columns}
        if absent:
            missing[table] = absent
    return missing


def _backup_before_migration(connection: sqlite3.Connection) -> Path:
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = DB_PATH.parent / f"{DB_PATH.stem}_antes_actualizacion_{stamp}.sqlite3"
    # sqlite backup API also produces a consistent copy when WAL is enabled.
    destination = sqlite3.connect(backup_path)
    try:
        connection.backup(destination)
    finally:
        destination.close()
    return backup_path


def _apply_migrations(connection: sqlite3.Connection) -> list[str]:
    missing = _missing_migrations(connection)
    if not missing:
        return []

    backup_path = _backup_before_migration(connection)
    applied: list[str] = []

    for table, columns in missing.items():
        for column, sql_type in columns.items():
            connection.execute(
                f'ALTER TABLE "{table}" ADD COLUMN "{column}" {sql_type}'
            )
            applied.append(f"{table}.{column}")

    # Older builds stored the evidence path under stored_path. Copy that value
    # into the current column so existing attachments continue to resolve.
    evidence_columns = _table_columns(connection, "evidence_files") if "evidence_files" in missing or connection.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='evidence_files'"
    ).fetchone() else set()
    if "relative_path" in evidence_columns and "stored_path" in evidence_columns:
        connection.execute(
            "UPDATE evidence_files SET relative_path=stored_path "
            "WHERE (relative_path IS NULL OR relative_path='') "
            "AND stored_path IS NOT NULL"
        )

    # Preserve a legacy filename field when older builds used one.
    if "stored_name" in evidence_columns and "original_name" in evidence_columns:
        connection.execute(
            "UPDATE evidence_files SET stored_name=original_name "
            "WHERE stored_name IS NULL OR stored_name=''"
        )

    applied.insert(0, f"Respaldo creado: {backup_path.name}")
    return applied


def initialize_database() -> list[str]:
    """Create the current schema and safely upgrade older local databases.

    Returns a list of applied migrations (empty when already up to date).
    Existing rows are never deleted or rewritten except for copying legacy
    evidence paths into their new equivalent column.
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with get_connection() as connection:
        connection.executescript(schema)
        applied = _apply_migrations(connection)
        connection.execute("PRAGMA user_version = 2")
        return applied
