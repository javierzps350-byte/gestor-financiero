"""Portable, verifiable full-data backup and restore (.gfbak)."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import datetime
from pathlib import Path, PurePosixPath

from src.config import APP_VERSION, BACKUP_DIR, DATA_DIR, DB_PATH, EVIDENCE_DIR

FORMAT_NAME = "gestor-financiero-portable-backup"
FORMAT_VERSION = 1
REQUIRED_TABLES = {
    "clients", "client_rates", "movements", "monthly_charges",
    "payment_allocations", "evidence_files", "audit_log",
}


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _safe_archive_path(name: str) -> PurePosixPath:
    path = PurePosixPath(name)
    if path.is_absolute() or not path.parts or any(part in ("", ".", "..") for part in path.parts):
        raise ValueError(f"La ruta del respaldo no es válida: {name}")
    if "\\" in name or ":" in name:
        raise ValueError(f"La ruta del respaldo contiene caracteres no permitidos: {name}")
    return path


def _database_backup(destination: Path) -> None:
    if not DB_PATH.exists():
        raise FileNotFoundError("No existe la base de datos para respaldar.")
    source = sqlite3.connect(DB_PATH, timeout=20)
    target = sqlite3.connect(destination)
    try:
        source.backup(target)
        check = target.execute("PRAGMA quick_check").fetchone()[0]
        if check != "ok":
            raise ValueError(f"La base de datos no superó la comprobación de integridad: {check}")
    finally:
        target.close()
        source.close()


def create_portable_backup(destination: str | Path) -> Path:
    """Create a self-contained archive with database, evidence and SHA-256s."""
    destination = Path(destination)
    destination.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="gestor_backup_") as temp:
        temp_root = Path(temp)
        db_copy = temp_root / "database.sqlite3"
        _database_backup(db_copy)
        evidence_entries = []
        evidence_files = []
        if EVIDENCE_DIR.exists():
            evidence_root = EVIDENCE_DIR.resolve()
            for candidate in EVIDENCE_DIR.rglob("*"):
                if candidate.is_symlink() or not candidate.is_file():
                    continue
                resolved = candidate.resolve()
                if not resolved.is_relative_to(evidence_root):
                    raise ValueError(f"La evidencia sale de la carpeta permitida: {candidate.name}")
                evidence_files.append(candidate)
        evidence_files.sort()
        for file_path in evidence_files:
            relative = file_path.relative_to(EVIDENCE_DIR).as_posix()
            safe = _safe_archive_path(relative)
            evidence_entries.append({
                "path": safe.as_posix(),
                "size": file_path.stat().st_size,
                "sha256": _sha256(file_path),
            })
        manifest = {
            "format": FORMAT_NAME,
            "format_version": FORMAT_VERSION,
            "app_version": APP_VERSION,
            "created_at": datetime.now().astimezone().isoformat(timespec="seconds"),
            "database": {"path": "database.sqlite3", "size": db_copy.stat().st_size, "sha256": _sha256(db_copy)},
            "evidence": evidence_entries,
            "evidence_count": len(evidence_entries),
        }
        manifest_path = temp_root / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
        with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as archive:
            archive.write(manifest_path, "manifest.json")
            archive.write(db_copy, "database.sqlite3")
            for file_path in evidence_files:
                relative = file_path.relative_to(EVIDENCE_DIR).as_posix()
                archive.write(file_path, f"evidence/{relative}")
    return destination


def _validate_database(path: Path) -> None:
    connection = sqlite3.connect(f"file:{path.as_posix()}?mode=ro", uri=True)
    try:
        result = connection.execute("PRAGMA quick_check").fetchone()
        if not result or result[0] != "ok":
            raise ValueError("La base de datos del paquete está dañada.")
        tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        missing = REQUIRED_TABLES - tables
        if missing:
            raise ValueError("El paquete no contiene las tablas necesarias: " + ", ".join(sorted(missing)))
    finally:
        connection.close()


def inspect_portable_backup(source: str | Path) -> dict:
    """Validate archive structure and checksums without changing local data."""
    source = Path(source)
    with zipfile.ZipFile(source, "r") as archive:
        infos = archive.infolist()
        names = [info.filename for info in infos]
        if len(names) != len(set(names)):
            raise ValueError("El paquete contiene nombres de archivo duplicados.")
        if "manifest.json" not in names or "database.sqlite3" not in names:
            raise ValueError("El archivo no es un paquete de traslado de Gestor Financiero.")
        total_size = sum(info.file_size for info in infos)
        if total_size > 8 * 1024 * 1024 * 1024:
            raise ValueError("El paquete supera el límite de tamaño admitido (8 GB).")
        for info in infos:
            _safe_archive_path(info.filename)
            unix_mode = info.external_attr >> 16
            if unix_mode & 0o170000 == 0o120000:
                raise ValueError("El paquete contiene un enlace simbólico no permitido.")
        manifest = json.loads(archive.read("manifest.json").decode("utf-8"))
        if manifest.get("format") != FORMAT_NAME or manifest.get("format_version") != FORMAT_VERSION:
            raise ValueError("El formato o la versión del paquete no son compatibles.")
        db_info = manifest.get("database", {})
        db_bytes = archive.read("database.sqlite3")
        if hashlib.sha256(db_bytes).hexdigest() != db_info.get("sha256"):
            raise ValueError("La comprobación SHA-256 de la base de datos no coincide.")
        expected = {item["path"]: item for item in manifest.get("evidence", [])}
        archive_evidence = {name[len("evidence/"):] for name in names if name.startswith("evidence/")}
        if archive_evidence != set(expected):
            raise ValueError("La lista de evidencias del paquete no coincide con los archivos incluidos.")
        for relative, item in expected.items():
            safe = _safe_archive_path(relative)
            file_bytes = archive.read(f"evidence/{safe.as_posix()}")
            if len(file_bytes) != int(item.get("size", -1)) or hashlib.sha256(file_bytes).hexdigest() != item.get("sha256"):
                raise ValueError(f"La evidencia {relative} no superó la verificación de integridad.")
        with tempfile.TemporaryDirectory(prefix="gestor_validate_") as temp:
            temp_db = Path(temp) / "database.sqlite3"
            temp_db.write_bytes(db_bytes)
            _validate_database(temp_db)
        return manifest


def restore_portable_backup(source: str | Path) -> dict:
    """Restore a verified portable package, first creating a rollback package."""
    source = Path(source)
    manifest = inspect_portable_backup(source)
    BACKUP_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    rollback_path = BACKUP_DIR / f"antes_de_restaurar_{stamp}.gfbak"
    if DB_PATH.exists():
        create_portable_backup(rollback_path)

    stage_root = Path(tempfile.mkdtemp(prefix="gestor_restore_", dir=DATA_DIR))
    stage_db = stage_root / "database.sqlite3"
    stage_evidence = stage_root / "evidence"
    old_evidence = BACKUP_DIR / f"evidencias_anteriores_{stamp}"
    old_db = stage_root / "database_before.sqlite3"
    moved_old_evidence = False
    installed_new_evidence = False
    replaced_db = False
    try:
        with zipfile.ZipFile(source, "r") as archive:
            stage_db.write_bytes(archive.read("database.sqlite3"))
            _validate_database(stage_db)
            stage_evidence.mkdir(parents=True, exist_ok=True)
            for item in manifest.get("evidence", []):
                relative = _safe_archive_path(item["path"])
                target = stage_evidence.joinpath(*relative.parts)
                target.parent.mkdir(parents=True, exist_ok=True)
                target.write_bytes(archive.read(f"evidence/{relative.as_posix()}"))

        # Snapshot the current database before removing WAL sidecars.
        if DB_PATH.exists():
            current = sqlite3.connect(DB_PATH, timeout=20)
            snapshot = sqlite3.connect(old_db)
            try:
                current.backup(snapshot)
                current.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            finally:
                snapshot.close()
                current.close()

        for sidecar in (Path(str(DB_PATH) + "-wal"), Path(str(DB_PATH) + "-shm")):
            try:
                sidecar.unlink(missing_ok=True)
            except OSError:
                pass

        if EVIDENCE_DIR.exists():
            old_evidence.parent.mkdir(parents=True, exist_ok=True)
            if old_evidence.exists():
                shutil.rmtree(old_evidence)
            os.replace(EVIDENCE_DIR, old_evidence)
            moved_old_evidence = True
        os.replace(stage_evidence, EVIDENCE_DIR)
        installed_new_evidence = True
        os.replace(stage_db, DB_PATH)
        replaced_db = True
        return {
            "manifest": manifest,
            "rollback_backup": str(rollback_path) if rollback_path.exists() else None,
            "evidence_count": int(manifest.get("evidence_count", 0)),
            "created_at": manifest.get("created_at", ""),
        }
    except Exception:
        # Best-effort rollback to the exact pre-restore SQLite file and evidence tree.
        if replaced_db:
            if old_db.exists():
                restore_copy = DB_PATH.with_name(DB_PATH.name + ".rollback")
                shutil.copy2(old_db, restore_copy)
                os.replace(restore_copy, DB_PATH)
            else:
                DB_PATH.unlink(missing_ok=True)
        if moved_old_evidence and old_evidence.exists():
            if EVIDENCE_DIR.exists():
                shutil.rmtree(EVIDENCE_DIR, ignore_errors=True)
            os.replace(old_evidence, EVIDENCE_DIR)
        elif installed_new_evidence and EVIDENCE_DIR.exists():
            shutil.rmtree(EVIDENCE_DIR, ignore_errors=True)
        raise
    finally:
        shutil.rmtree(stage_root, ignore_errors=True)
