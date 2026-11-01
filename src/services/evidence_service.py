import hashlib
import mimetypes
import re
import shutil
import uuid
from pathlib import Path

from src.config import EVIDENCE_DIR
from src.database.connection import get_connection


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as file:
        for chunk in iter(lambda: file.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def attach_evidence(movement_id: int, source_path: str) -> int:
    source = Path(source_path).expanduser().resolve()
    if not source.is_file():
        raise FileNotFoundError(f"No existe el archivo: {source}")
    digest = _sha256(source)
    mime_type = mimetypes.guess_type(source.name)[0] or "application/octet-stream"
    safe_name = re.sub(r"[^A-Za-z0-9._-]+", "_", source.name).strip("._") or "evidencia"
    folder = EVIDENCE_DIR / str(movement_id)
    folder.mkdir(parents=True, exist_ok=True)
    stored_name = f"{uuid.uuid4().hex[:10]}_{safe_name}"
    destination = folder / stored_name
    shutil.copy2(source, destination)
    relative_path = destination.relative_to(EVIDENCE_DIR.parent).as_posix()
    try:
        with get_connection() as connection:
            existing = connection.execute(
                "SELECT id FROM evidence_files WHERE movement_id=? AND sha256=?",
                (movement_id, digest),
            ).fetchone()
            if existing:
                destination.unlink(missing_ok=True)
                return int(existing["id"])
            cursor = connection.execute(
                """INSERT INTO evidence_files
                   (movement_id, original_name, stored_name, relative_path, mime_type, file_size_bytes, sha256)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (movement_id, source.name, stored_name, relative_path, mime_type, source.stat().st_size, digest),
            )
            return int(cursor.lastrowid)
    except Exception:
        destination.unlink(missing_ok=True)
        raise


def evidence_absolute_path(relative_path: str) -> Path:
    return (EVIDENCE_DIR.parent / relative_path).resolve()


def find_recent_downloads(max_days: int = 7, limit: int = 100) -> list[dict]:
    """Devuelve archivos recientes de la carpeta Descargas, más nuevos primero."""
    from datetime import datetime, timedelta

    downloads = Path.home() / "Downloads"
    if not downloads.is_dir():
        return []
    cutoff = datetime.now().timestamp() - max(1, max_days) * 86400
    ignored_suffixes = (".crdownload", ".part", ".tmp", ".download")
    results = []
    try:
        for path in downloads.iterdir():
            try:
                if not path.is_file() or path.name.lower().endswith(ignored_suffixes):
                    continue
                stat = path.stat()
                if stat.st_mtime < cutoff:
                    continue
                results.append({
                    "name": path.name,
                    "path": str(path.resolve()),
                    "modified": datetime.fromtimestamp(stat.st_mtime).strftime("%Y-%m-%d %H:%M"),
                    "modified_ts": stat.st_mtime,
                    "size": stat.st_size,
                })
            except OSError:
                continue
    except OSError:
        return []
    results.sort(key=lambda item: item["modified_ts"], reverse=True)
    return results[:max(1, min(limit, 500))]


def attach_evidence_from_download(movement_id: int, source_path: str) -> int:
    """Adjunta un archivo solo si se encuentra dentro de Descargas del usuario."""
    source = Path(source_path).expanduser().resolve()
    downloads = (Path.home() / "Downloads").resolve()
    try:
        source.relative_to(downloads)
    except ValueError as exc:
        raise ValueError("El archivo seleccionado no pertenece a la carpeta Descargas.") from exc
    return attach_evidence(movement_id, str(source))
