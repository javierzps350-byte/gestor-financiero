"""Puente HTTP opcional para NEXUS.

No se inicia automáticamente. Por defecto escucha solo en 127.0.0.1 y exige
un token bearer creado al activar el puente. No importa ningún módulo de NEXUS.
"""
from __future__ import annotations

import json
import secrets
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from src.config import DATA_DIR
from src.domain.money import to_cents
from src.services.finance_service import (
    client_debt_summary, create_movement, list_clients, search_movements,
)
from src.services.evidence_service import find_recent_downloads, attach_evidence_from_download

TOKEN_PATH = DATA_DIR / "nexus_bridge.token"


def get_or_create_token() -> str:
    if TOKEN_PATH.exists():
        return TOKEN_PATH.read_text(encoding="utf-8").strip()
    token = secrets.token_urlsafe(40)
    TOKEN_PATH.write_text(token, encoding="utf-8")
    try:
        TOKEN_PATH.chmod(0o600)
    except OSError:
        pass
    return token


class NexusBridge:
    """API local de consulta y registro, desactivada hasta que se invoque start()."""

    def __init__(self, host: str = "127.0.0.1", port: int = 8765):
        if host not in ("127.0.0.1", "localhost", "::1"):
            raise ValueError("El puente solo puede enlazarse a la interfaz local en esta versión.")
        self.host = host
        self.port = port
        self.server: ThreadingHTTPServer | None = None
        self.thread: threading.Thread | None = None
        self.token = get_or_create_token()

    def start(self) -> str:
        if self.server:
            return self.token
        bridge = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, _format, *_args):
                return

            def _send(self, status: int, payload: dict[str, Any]):
                data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def _authorized(self) -> bool:
                return secrets.compare_digest(self.headers.get("Authorization", ""), f"Bearer {bridge.token}")

            def do_GET(self):
                if self.path == "/health":
                    return self._send(200, {"ok": True, "service": "gestor-financiero-bridge"})
                if not self._authorized():
                    return self._send(401, {"ok": False, "error": "unauthorized"})
                if self.path.startswith("/api/v1/search"):
                    from urllib.parse import parse_qs, urlparse
                    params = parse_qs(urlparse(self.path).query)
                    rows = search_movements(query=params.get("q", [""])[0], limit=100)
                    return self._send(200, {"ok": True, "movements": rows})
                if self.path == "/api/v1/clients":
                    clients = list_clients(active_only=True)
                    return self._send(200, {"ok": True, "clients": [
                        {"id": c["id"], "name": c["name"], "monthly_rate_cents": c["current_rate_cents"]}
                        for c in clients
                    ]})
                if self.path.startswith("/api/v1/recent-downloads"):
                    return self._send(200, {"ok": True, "files": find_recent_downloads(max_days=7, limit=100)})
                return self._send(404, {"ok": False, "error": "not_found"})

            def do_POST(self):
                if not self._authorized():
                    return self._send(401, {"ok": False, "error": "unauthorized"})
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                    if length <= 0 or length > 65536:
                        return self._send(400, {"ok": False, "error": "invalid_body_size"})
                    payload = json.loads(self.rfile.read(length).decode("utf-8"))
                    if self.path == "/api/v1/debt":
                        client_id = int(payload["client_id"])
                        summary = client_debt_summary(client_id, payload.get("as_of"))
                        return self._send(200, {"ok": True, "summary": summary})
                    if self.path == "/api/v1/evidence":
                        if not payload.get("confirm", False):
                            return self._send(409, {"ok": False, "confirmation_required": True})
                        evidence_id = attach_evidence_from_download(int(payload["movement_id"]), payload["source_path"])
                        return self._send(201, {"ok": True, "evidence_id": evidence_id})
                    if self.path == "/api/v1/movements":
                        if not payload.get("confirm", False):
                            return self._send(409, {"ok": False, "confirmation_required": True})
                        movement_id = create_movement(
                            direction=payload["direction"],
                            counterparty=payload["counterparty"],
                            reason=payload["reason"],
                            amount_cents=to_cents(payload["amount"]),
                            payment_date=payload["payment_date"],
                            payment_method=payload["payment_method"],
                            client_id=payload.get("client_id"),
                            voucher_number=payload.get("voucher_number", ""),
                            notes=payload.get("notes", ""),
                            apply_to_monthly=bool(payload.get("apply_to_monthly", False)),
                        )
                        return self._send(201, {"ok": True, "movement_id": movement_id})
                    return self._send(404, {"ok": False, "error": "not_found"})
                except (KeyError, ValueError, TypeError, json.JSONDecodeError) as exc:
                    return self._send(400, {"ok": False, "error": str(exc)})
                except Exception:
                    return self._send(500, {"ok": False, "error": "internal_error"})

        self.server = ThreadingHTTPServer((self.host, self.port), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self.token

    def stop(self) -> None:
        if self.server:
            self.server.shutdown()
            self.server.server_close()
            self.server = None
            self.thread = None
