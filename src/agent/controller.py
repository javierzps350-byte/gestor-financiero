"""Agente local para consultar y operar el Gestor Financiero.

La interpretación inicial es determinista y ligera: no carga modelos de IA ni
necesita GPU o conexión a Internet. Todas las operaciones que modifican datos
se preparan como borrador y requieren confirmación explícita en la interfaz.
"""
from __future__ import annotations

import calendar
import re
import unicodedata
from datetime import date, timedelta
from typing import Any

from src.domain.money import format_money, to_cents
from src.domain.monthly_calculator import add_months
from src.services.evidence_service import attach_evidence_from_download, find_recent_downloads
from src.services.finance_service import (
    client_debt_summary,
    create_client,
    create_movement,
    dashboard_summary,
    find_voucher_matches,
    list_clients,
    search_movements,
    set_client_rate,
)


METHODS = {
    "transferencia": "Transferencia",
    "transfer": "Transferencia",
    "deposito": "Depósito",
    "deposit": "Depósito",
    "efectivo": "Efectivo",
    "cash": "Efectivo",
    "cheque": "Cheque",
    "debito": "Tarjeta de débito",
    "credito": "Tarjeta de crédito",
    "tarjeta": "Tarjeta",
    "zelle": "Zelle",
    "paypal": "PayPal",
    "otro": "Otro",
}


def _plain(value: str) -> str:
    value = unicodedata.normalize("NFD", value.casefold())
    return "".join(char for char in value if unicodedata.category(char) != "Mn")


def _clean(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" \t\r\n,.;:-")


MONTH_NUMBERS = {
    "enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5,
    "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9,
    "setiembre": 9, "octubre": 10, "noviembre": 11, "diciembre": 12,
}
CATEGORY_ALIASES = {
    "Hogar": ("hogar", "casa", "vivienda", "arriendo"),
    "Comida": ("comida", "comidas", "alimentacion", "alimentos", "supermercado", "mercado"),
    "Transporte": ("transporte", "gasolina", "combustible", "taxi", "bus", "pasaje"),
    "Entretenimiento": ("entretenimiento", "ocio", "cine"),
    "Salud": ("salud", "medicina", "medicinas", "farmacia", "medico", "doctor"),
    "Educación": ("educacion", "colegio", "universidad", "estudios", "curso"),
    "Servicios": ("servicios", "agua", "luz", "electricidad", "internet", "telefono"),
    "Compras": ("compras", "ropa", "articulos"),
    "Negocio": ("negocio", "empresa", "proveedor", "insumos", "materiales"),
    "Otros": ("otros", "varios", "miscelaneos"),
}


def _parse_user_date(value: str) -> date | None:
    value = value.strip()
    try:
        return date.fromisoformat(value)
    except ValueError:
        pass
    from datetime import datetime
    for pattern in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y"):
        try:
            return datetime.strptime(value, pattern).date()
        except ValueError:
            continue
    return None


def _extract_date(text: str) -> str | None:
    # Resolve ISO, DD/MM/YYYY and common relative/named dates.
    iso = re.search(r"\b(\d{4}-\d{2}-\d{2})\b", text)
    if iso:
        return date.fromisoformat(iso.group(1)).isoformat()
    numeric = re.search(r"\b(\d{1,2}[/-]\d{1,2}[/-]\d{4})\b", text)
    if numeric:
        parsed = _parse_user_date(numeric.group(1))
        if parsed:
            return parsed.isoformat()

    normalized = _plain(text)
    today = date.today()
    if re.search(r"\b(anteayer|antes de ayer)\b", normalized):
        return (today - timedelta(days=2)).isoformat()
    if re.search(r"\b(ayer|el dia de ayer)\b", normalized):
        return (today - timedelta(days=1)).isoformat()
    if re.search(r"\b(manana)\b", normalized):
        return (today + timedelta(days=1)).isoformat()
    if re.search(r"\b(hoy|ahora|acabo de|hace un momento)\b", normalized):
        return today.isoformat()
    month_pattern = "|".join(sorted(MONTH_NUMBERS, key=len, reverse=True))
    named = re.search(
        rf"\b(\d{1,2})\s+de\s+({month_pattern})(?:\s+(?:de|del)\s+(\d{4}))?\b",
        normalized,
    )
    if named:
        day = int(named.group(1))
        month = MONTH_NUMBERS[named.group(2)]
        year = int(named.group(3)) if named.group(3) else today.year
        try:
            return date(year, month, day).isoformat()
        except ValueError:
            return None
    return None


def _extract_period_range(text: str) -> tuple[str, str] | None:
    # Resolve common period expressions into inclusive ISO date boundaries.
    normalized = _plain(text)
    today = date.today()

    explicit: list[date] = []
    for match in re.finditer(r"\b\d{4}-\d{2}-\d{2}\b", text):
        parsed = _parse_user_date(match.group(0))
        if parsed:
            explicit.append(parsed)
    for match in re.finditer(r"\b\d{1,2}[/-]\d{1,2}[/-]\d{4}\b", text):
        parsed = _parse_user_date(match.group(0))
        if parsed:
            explicit.append(parsed)
    if len(explicit) >= 2:
        first, last = min(explicit), max(explicit)
        return first.isoformat(), last.isoformat()
    if len(explicit) == 1 and any(word in normalized for word in ("fecha", "dia", "del", "el")):
        value = explicit[0].isoformat()
        return value, value

    recent = re.search(r"\b(ultimos?|ultimas?)\s+(\d{1,3})\s+(dias?|semanas?)\b", normalized)
    if recent:
        count = max(1, min(int(recent.group(2)), 3650))
        days = count * 7 if "semana" in recent.group(3) else count
        return (today - timedelta(days=days - 1)).isoformat(), today.isoformat()

    if any(term in normalized for term in ("mes pasado", "mes anterior", "el mes anterior")):
        year = today.year if today.month > 1 else today.year - 1
        month = today.month - 1 if today.month > 1 else 12
        last_day = calendar.monthrange(year, month)[1]
        return date(year, month, 1).isoformat(), date(year, month, last_day).isoformat()
    if any(term in normalized for term in ("este mes", "mes actual", "durante el mes", "del mes")):
        return today.replace(day=1).isoformat(), today.isoformat()
    if any(term in normalized for term in ("ano pasado", "año pasado", "ano anterior", "año anterior")):
        year = today.year - 1
        return date(year, 1, 1).isoformat(), date(year, 12, 31).isoformat()
    if any(term in normalized for term in ("este ano", "este año", "ano actual", "año actual")):
        return date(today.year, 1, 1).isoformat(), today.isoformat()

    month_pattern = "|".join(sorted(MONTH_NUMBERS, key=len, reverse=True))
    month_match = re.search(rf"\b({month_pattern})\b", normalized)
    if month_match:
        month = MONTH_NUMBERS[month_match.group(1)]
        year_match = re.search(r"\b(20\d{2})\b", normalized)
        if year_match:
            year = int(year_match.group(1))
        else:
            year = today.year
            if month >= today.month and any(word in normalized for word in ("pasado", "anterior")):
                year -= 1
        last_day = calendar.monthrange(year, month)[1]
        if year == today.year and month == today.month:
            last_day = today.day
        return date(year, month, 1).isoformat(), date(year, month, last_day).isoformat()

    year_match = re.search(r"\b(20\d{2})\b", normalized)
    if year_match and any(word in normalized for word in ("ano", "año", "durante", "en", "del", "de")):
        year = int(year_match.group(1))
        return date(year, 1, 1).isoformat(), date(year, 12, 31).isoformat()
    return None


def _extract_category(text: str) -> str:
    normalized = _plain(text)
    matches = []
    for category, aliases in CATEGORY_ALIASES.items():
        hits = [
            len(_plain(alias)) for alias in aliases
            if re.search(rf"(?<!\w){re.escape(_plain(alias))}(?!\w)", normalized)
        ]
        if hits:
            matches.append((category, max(hits)))
    return max(matches, key=lambda item: item[1])[0] if matches else ""


def _extract_amount(text: str) -> int | None:
    """Read the first plausible amount, preferring explicit currency markers."""
    scrubbed = re.sub(r"\b\d{4}-\d{2}-\d{2}\b", " ", text)
    scrubbed = re.sub(
        r"\b(?:voucher|comprobante|referencia|ref)\s*(?:(?:es\s+)?(?:el\s+)?(?:numero\s+|n(?:ro)?\.?\s*|#\s*)?)?[A-Za-z0-9-]+",
        " ", scrubbed, flags=re.IGNORECASE,
    )
    patterns = (
        r"(?:\$\s*|\bUSD\s*)(\d{1,9}(?:[.,]\d{1,2})?)",
        r"\b(\d{1,9}(?:[.,]\d{1,2})?)\s*(?:dolares?|usd)\b",
    )
    for pattern in patterns:
        match = re.search(pattern, scrubbed, flags=re.IGNORECASE)
        if match:
            return to_cents(match.group(1))
    # Natural spoken/text form without a currency word: "Carlos me pagó 25".
    match = re.search(r"(?<!\w)(\d{1,9}(?:[.,]\d{1,2})?)(?!\w)", scrubbed)
    if match:
        return to_cents(match.group(1))
    return None


def _extract_method(text: str) -> str | None:
    normalized = _plain(text)
    for key, label in METHODS.items():
        if re.search(rf"\b{re.escape(key)}\b", normalized):
            return label
    return None


def _extract_voucher(text: str) -> str:
    normalized = _plain(text)
    match = re.search(
        r"\b(?:voucher|comprobante|referencia|ref)\s*(?:(?:es\s+)?(?:el\s+)?(?:numero\s+|n(?:ro)?\.?\s*|#\s*)?)?([a-z0-9][a-z0-9-]*)",
        normalized,
    )
    return match.group(1).strip() if match else ""


def _extract_reason(text: str) -> str:
    # El motivo se toma de expresiones explícitas para evitar inventarlo.
    match = re.search(r"\b(?:por concepto de|concepto de|por|para)\s+(.+)$", text, flags=re.IGNORECASE)
    if not match:
        normalized = _plain(text)
        common_reasons = (
            "mensualidad", "cuota", "electricidad", "luz", "agua", "internet",
            "alquiler", "renta", "servicio", "transporte", "alimentacion",
        )
        for candidate in common_reasons:
            if re.search(rf"\b{re.escape(candidate)}\b", normalized):
                return candidate.title()
        return ""
    reason = match.group(1)
    cut_patterns = (
        r"\b(?:mediante|con voucher|voucher|comprobante|referencia|ref)\b.*$",
        r"\b(?:por transferencia|por deposito|por efectivo|en efectivo|transferencia|deposito|cheque|tarjeta|zelle|paypal)\b.*$",
        r"\b(?:hoy|ayer|el dia|fecha)\b.*$",
        r"\b(?:\$\s*|USD\s*)\d[\d.,]*.*$",
        r"\b\d[\d.,]*\s*(?:dolares?|usd)\b.*$",
    )
    for pattern in cut_patterns:
        reason = re.sub(pattern, "", reason, flags=re.IGNORECASE)
    cleaned = _clean(reason)
    if cleaned:
        return cleaned
    normalized = _plain(text)
    common_reasons = (
        "mensualidad", "cuota", "electricidad", "luz", "agua", "internet",
        "alquiler", "renta", "servicio", "transporte", "alimentacion",
    )
    for candidate in common_reasons:
        if re.search(rf"\b{re.escape(candidate)}\b", normalized):
            return candidate.title()
    return ""


def _find_client_in_text(text: str) -> tuple[dict[str, Any] | None, list[dict[str, Any]]]:
    normalized = _plain(text)
    matches = []
    for client in list_clients(active_only=True):
        name = str(client["name"])
        normalized_name = _plain(name)
        if normalized_name and re.search(rf"(?<!\w){re.escape(normalized_name)}(?!\w)", normalized):
            matches.append(client)
    if not matches:
        return None, []
    # If a full name contains a shorter registered name, prefer the longest exact phrase.
    longest = max(len(_plain(str(item["name"]))) for item in matches)
    best = [item for item in matches if len(_plain(str(item["name"]))) == longest]
    return (best[0] if len(best) == 1 else None), best


def _extract_counterparty(text: str, direction: str, client: dict[str, Any] | None) -> str:
    if client:
        return str(client["name"])
    patterns = (
        r"(.+?)\s+me\s+pag[oó]",
        r"(.+?)\s+me\s+(?:transfiri[oó]|deposit[oó]|abon[oó]|consign[oó])",
        r"(?:me\s+)?(?:transfirieron|depositaron|abonaron|consignaron)\s+(?:de\s+)?(.+?)(?:\s+por\b|\s+de\s+\$|\s+de\s+\d|$)",
        r"(?:recib[ií]|cobr[eé])\s+(?:un pago\s+)?de\s+(.+?)(?:\s+por\b|\s+de\s+\$|\s+de\s+\d|$)",
    ) if direction == "income" else (
        r"(?:pagu[eé]|transfer[ií]|deposit[eé])\s+\$?\s*\d+(?:[.,]\d+)?\s*(?:dólares?)?\s+a\s+(.+?)(?:\s+por\b|\s+mediante\b|\s+con\b|$)",
        r"(?:pagu[eé]|transfer[ií]|deposit[eé])\s+(?:dinero\s+)?a\s+(.+?)(?:\s+por\b|\s+mediante\b|\s+con\b|$)",
        r"(?:pagu[eé]|gast[eé])\s+(?:a\s+)?(.+?)\s+\$?\d",
    )
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            candidate = _clean(match.group(1))
            candidate = re.sub(r"\b(?:ayer|hoy|mensualidad|cuota)\b.*$", "", candidate, flags=re.IGNORECASE)
            if candidate and len(candidate) <= 100:
                return candidate
    return ""


def normalized_yes(text: str) -> bool:
    return _plain(text).strip(" .!¡¿?") in {"si", "sí", "confirmar", "confirmo", "adelante", "hazlo"}


def normalized_no(text: str) -> bool:
    return _plain(text).strip(" .!¡¿?") in {"no", "cancelar", "cancela", "descartar"}


class FinancialAgent:
    """Conversation controller; writes are staged and confirmed by the user."""

    def __init__(self):
        self.pending: dict[str, Any] | None = None
        self.awaiting_choice: dict[str, Any] | None = None
        self.navigation_target: str | None = None

    def handle(self, command: str) -> str:
        text = _clean(command)
        if not text:
            return "Escribe una instrucción o una consulta."

        if (self.pending or self.awaiting_choice) and normalized_no(text):
            return self.cancel()
        if self.awaiting_choice:
            return self._resolve_choice(text)
        if self.pending and self.pending.get("awaiting"):
            return self._fill_missing(text)
        if self.pending:
            if normalized_yes(text):
                return self.confirm()
            if normalized_no(text):
                return self.cancel()
            return "Hay una operación pendiente. Responde «sí» para confirmarla o «no» para cancelarla."

        normalized = _plain(text)
        if normalized in {"ayuda", "que puedes hacer", "comandos", "ayudame"} or "que puedes hacer" in normalized:
            return self.help_text()
        navigation = self._navigation_target(normalized)
        if navigation:
            self.navigation_target = navigation[0]
            return navigation[1]

        if self._is_attach_command(normalized):
            return self._prepare_attachment(text)
        if self._is_client_command(normalized):
            return self._prepare_client(text)
        if self._is_rate_command(normalized):
            return self._prepare_rate(text)
        if self._is_query_request(normalized):
            return self._answer_query(text)
        if self._is_movement_command(normalized):
            return self._prepare_movement(text)
        return self._answer_query(text)

    @staticmethod
    def help_text() -> str:
        return (
            "Puedo consultar ingresos, gastos, balances, clientes, mensualidades, deudas, "
            "categorías, movimientos y vouchers. Entiendo períodos como este mes, el mes "
            "pasado, un mes por nombre, un año o un rango de fechas. También puedo preparar "
            "registros, crear clientes, cambiar tarifas y asociar evidencias. Toda escritura "
            "se presenta para revisión y requiere confirmación."
        )

    @staticmethod
    def _navigation_target(text: str) -> tuple[str, str] | None:
        if not any(verb in text for verb in ("abre", "abrir", "ir a", "ve a", "muestrame", "llevame", "entra en", "cambia a")):
            return None
        routes = (
            (("inicio", "panel", "principal"), "dashboard", "Abriendo el inicio."),
            (("ingresos", "cobros"), "incomes", "Abriendo ingresos."),
            (("gastos", "egresos"), "expenses", "Abriendo gastos."),
            (("clientes", "cliente"), "clients", "Abriendo clientes."),
            (("deudas", "mensualidades", "cuotas"), "debts", "Abriendo mensualidades."),
            (("buscador", "busqueda"), "search", "Abriendo el buscador."),
            (("agente", "asistente"), "assistant", "Abriendo el asistente."),
        )
        for aliases, page, message in routes:
            if any(alias in text for alias in aliases):
                return page, message
        return None

    @staticmethod
    def _is_rate_command(text: str) -> bool:
        return any(word in text for word in ("cambia", "cambiar", "actualiza", "modifica", "sube", "baja")) and any(
            word in text for word in ("mensualidad", "tarifa", "cuota mensual")
        )

    def _prepare_rate(self, text: str) -> str:
        client, matches = _find_client_in_text(text)
        if len(matches) > 1:
            return "Encontré varios clientes posibles: " + ", ".join(str(row["name"]) for row in matches) + ". Especifica el nombre completo."
        effective = _extract_date(text)
        if client and not effective:
            effective = self._next_client_cycle(client)
        payload = {
            "client_id": int(client["id"]) if client else None,
            "client_name": str(client["name"]) if client else "",
            "monthly_amount_cents": _extract_amount(text),
            "effective_from": effective,
        }
        self.pending = {"kind": "rate", "payload": payload}
        return self._advance_rate_draft()

    @staticmethod
    def _next_client_cycle(client: dict[str, Any]) -> str:
        first = date.fromisoformat(str(client["first_billing_date"]))
        billing_day = int(client["billing_day"])
        cycle = first
        today = date.today()
        while cycle <= today:
            cycle = add_months(cycle, 1, billing_day)
        return cycle.isoformat()

    def _advance_rate_draft(self) -> str:
        assert self.pending and self.pending["kind"] == "rate"
        payload = self.pending["payload"]
        fields = [
            ("client_id", "¿A qué cliente debo cambiarle la tarifa? Escribe su nombre."),
            ("monthly_amount_cents", "¿Cuál será la nueva mensualidad? Escribe el importe."),
        ]
        for key, question in fields:
            if payload.get(key) in (None, ""):
                self.pending["awaiting"] = key
                return question
        self.pending.pop("awaiting", None)
        return (
            "CAMBIO DE TARIFA — revisión antes de guardar\n"
            f"Cliente: {payload['client_name']}\n"
            f"Nueva mensualidad: {format_money(payload['monthly_amount_cents'])}\n"
            f"Vigente desde: {payload['effective_from']}\n"
            "Las cuotas históricas que ya tengan abonos no se reescribirán. Confirma para aplicar el cambio."
        )

    @staticmethod
    def _is_attach_command(text: str) -> bool:
        return any(word in text for word in ("adjunta", "adjuntar", "anexa", "anexar", "vincula evidencia", "comprobante descargado"))

    @staticmethod
    def _is_client_command(text: str) -> bool:
        return ("cliente" in text and any(word in text for word in ("crea", "crear", "agrega", "agregar", "registra", "registrar", "nuevo")))

    @staticmethod
    def _is_query_request(text: str) -> bool:
        """Prevent questions about past payments from being treated as new entries."""
        return bool(re.match(
            r"^(?:cuant[oa]s?|cual(?:es)?|que|quien(?:es)?|como|cuando|donde|"
            r"muestrame|mostrar|lista|listado|busca|buscar|encuentra|"
            r"dime|consulta|consultar|quiero saber|necesito saber|"
            r"puedes decirme|me puedes decir)", text
        ))

    @staticmethod
    def _is_movement_command(text: str) -> bool:
        phrases = (
            "me pago", "me pagaron", "me deposito", "me depositaron",
            "me transfirio", "me transfirieron", "me abono", "me abonaron",
            "me consigno", "me consignaron", "recibi", "recibi un pago",
            "recibi una transferencia", "cobre", "cobro recibido",
            "registra un ingreso", "registrar ingreso", "anota un ingreso",
            "registra un cobro", "registrar un cobro", "anota un pago",
            "anota el pago", "pague a", "he pagado", "le pague",
            "pague", "gaste", "compre", "hice una transferencia",
            "realice una transferencia", "registra un gasto", "registrar gasto",
            "anota un gasto", "registra un egreso", "registrar egreso",
            "registre un gasto", "ingreso de dinero", "salida de dinero",
        )
        return any(phrase in text for phrase in phrases)

    def _prepare_movement(self, text: str) -> str:
        normalized = _plain(text)
        expense_markers = ("pague", "pague a", "le pague", "he pagado", "gaste", "compre", "registra un gasto", "registrar gasto", "anota un gasto", "hice una transferencia")
        direction = "expense" if any(marker in normalized for marker in expense_markers) else "income"
        client, matches = _find_client_in_text(text)
        if len(matches) > 1:
            names = ", ".join(str(item["name"]) for item in matches)
            return f"Encontré varios clientes posibles: {names}. Escribe nuevamente la instrucción con el nombre completo."

        payload = {
            "direction": direction,
            "counterparty": _extract_counterparty(text, direction, client),
            "reason": _extract_reason(text),
            "amount_cents": _extract_amount(text),
            "payment_date": _extract_date(text) or date.today().isoformat(),
            "payment_method": _extract_method(text),
            "voucher_number": _extract_voucher(text),
            "client_id": int(client["id"]) if client and direction == "income" else None,
            "apply_to_monthly": bool(client and direction == "income" and re.search(r"\b(mensualidad|mensual|cuota)\b", normalized)),
            "category": _extract_category(text) or ("Ingresos" if direction == "income" else "Otros"),
            "notes": "",
        }
        self.pending = {"kind": "movement", "payload": payload}
        return self._advance_movement_draft()

    def _advance_movement_draft(self) -> str:
        assert self.pending and self.pending["kind"] == "movement"
        payload = self.pending["payload"]
        fields = [
            ("amount_cents", "¿Qué importe recibiste o pagaste? Ejemplo: 25,00."),
            ("counterparty", "¿Quién realizó o recibió el pago? Escribe el nombre de la persona o proveedor."),
            ("reason", "¿Cuál es el motivo del movimiento? Este dato es obligatorio."),
            ("payment_method", "¿Qué tipo de pago fue? Por ejemplo: transferencia, depósito, efectivo o cheque."),
        ]
        for key, question in fields:
            if payload.get(key) in (None, ""):
                self.pending["awaiting"] = key
                return question
        self.pending.pop("awaiting", None)
        duplicates = find_voucher_matches(payload["voucher_number"]) if payload.get("voucher_number") else []
        self.pending["duplicate_vouchers"] = duplicates
        return self._movement_preview(payload, duplicates)

    def _movement_preview(self, payload: dict[str, Any], duplicates: list[dict[str, Any]]) -> str:
        kind = "INGRESO" if payload["direction"] == "income" else "GASTO"
        parts = [
            f"{kind} — revisión antes de guardar",
            f"Persona: {payload['counterparty']}",
            f"Motivo: {payload['reason']}",
            f"Importe: {format_money(payload['amount_cents'])}",
            f"Fecha: {payload['payment_date']}",
            f"Tipo de pago: {payload['payment_method']}",
            f"Voucher: {payload['voucher_number'] or 'No indicado'}",
        ]
        if payload.get("apply_to_monthly"):
            client = next((c for c in list_clients() if int(c["id"]) == payload["client_id"]), None)
            parts.append(f"Mensualidades: se aplicará a la cuenta de {client['name'] if client else 'cliente'}.")
        elif payload["direction"] == "income" and payload.get("client_id"):
            parts.append("Mensualidades: no se aplicará a cuotas; se registrará como ingreso independiente.")
        if duplicates:
            parts.append(f"Atención: ya existen {len(duplicates)} movimiento(s) con ese voucher. Revísalos antes de confirmar.")
        parts.append("Pulsa «Confirmar operación» para guardar o «Cancelar» para descartarla.")
        return "\n".join(parts)

    def _fill_missing(self, answer: str) -> str:
        assert self.pending is not None
        kind = self.pending["kind"]
        key = self.pending.get("awaiting")
        if kind == "movement":
            payload = self.pending["payload"]
            if key == "amount_cents":
                payload[key] = _extract_amount(answer)
                if payload[key] is None:
                    return "No pude identificar el importe. Escríbelo, por ejemplo: 25,00."
            elif key == "counterparty":
                client, _matches = _find_client_in_text(answer)
                payload[key] = str(client["name"]) if client else _clean(answer)
                if client and payload["direction"] == "income":
                    payload["client_id"] = int(client["id"])
            elif key == "reason":
                payload[key] = _clean(answer)
                if (
                    payload["direction"] == "income"
                    and payload.get("client_id")
                    and re.search(r"\b(mensualidad|mensual|cuota)\b", _plain(answer))
                ):
                    payload["apply_to_monthly"] = True
            elif key == "payment_method":
                payload[key] = _extract_method(answer) or _clean(answer).title()
            self.pending.pop("awaiting", None)
            return self._advance_movement_draft()
        if kind == "rate":
            payload = self.pending["payload"]
            if key == "client_id":
                client, matches = _find_client_in_text(answer)
                if not client:
                    if len(matches) > 1:
                        return "Hay varios clientes posibles. Escribe el nombre completo."
                    return "No encontré ese cliente. Escribe el nombre como aparece en el registro."
                payload["client_id"] = int(client["id"])
                payload["client_name"] = str(client["name"])
                if not payload.get("effective_from"):
                    payload["effective_from"] = self._next_client_cycle(client)
            elif key == "monthly_amount_cents":
                payload[key] = _extract_amount(answer)
                if payload[key] is None:
                    return "No pude identificar el importe. Escribe la nueva mensualidad."
            self.pending.pop("awaiting", None)
            return self._advance_rate_draft()
        if kind == "client":
            payload = self.pending["payload"]
            if key == "name":
                payload[key] = _clean(answer)
            elif key == "monthly_amount_cents":
                payload[key] = _extract_amount(answer)
                if payload[key] is None:
                    return "No pude identificar la mensualidad. Escribe el importe, por ejemplo: 23,00."
            elif key == "first_billing_date":
                payload[key] = _extract_date(answer)
                if payload[key] is None:
                    try:
                        payload[key] = date.fromisoformat(answer.strip()).isoformat()
                    except ValueError:
                        return "Escribe la fecha como AAAA-MM-DD, por ejemplo: 2026-01-31."
            self.pending.pop("awaiting", None)
            return self._advance_client_draft()
        if kind == "attachment":
            return self._resolve_choice(answer)
        return "No pude continuar la operación. Cancélala e inténtalo nuevamente."

    def _prepare_client(self, text: str) -> str:
        match = re.search(r"\bcliente\s+(.+?)(?=\s+(?:con|y)\s+(?:una\s+)?(?:mensualidad|cuota)|$)", text, flags=re.IGNORECASE)
        name = _clean(match.group(1)) if match else ""
        amount = _extract_amount(text)
        first_date = _extract_date(text) or date.today().isoformat()
        self.pending = {"kind": "client", "payload": {
            "name": name, "monthly_amount_cents": amount,
            "first_billing_date": first_date,
        }}
        return self._advance_client_draft()

    def _advance_client_draft(self) -> str:
        assert self.pending and self.pending["kind"] == "client"
        payload = self.pending["payload"]
        fields = [
            ("name", "¿Cuál es el nombre completo del cliente?"),
            ("monthly_amount_cents", "¿Cuánto debe pagar al mes? Escribe el importe."),
            ("first_billing_date", "¿Desde qué fecha debe comenzar a pagar? Usa AAAA-MM-DD."),
        ]
        for key, question in fields:
            if payload.get(key) in (None, ""):
                self.pending["awaiting"] = key
                return question
        duplicates = [
            item for item in list_clients()
            if _plain(str(item["name"])) == _plain(str(payload["name"]))
        ]
        if duplicates:
            self.pending["awaiting"] = "name"
            return f"Ya existe un cliente llamado {payload['name']}. Indica otro nombre o cancela la operación."
        self.pending.pop("awaiting", None)
        return (
            "CLIENTE — revisión antes de guardar\n"
            f"Nombre: {payload['name']}\n"
            f"Mensualidad: {format_money(payload['monthly_amount_cents'])}\n"
            f"Primera fecha de cobro: {payload['first_billing_date']}\n"
            "Pulsa «Confirmar operación» para crear el cliente o «Cancelar» para descartarlo."
        )

    def _prepare_attachment(self, text: str) -> str:
        voucher = _extract_voucher(text)
        client, matches = _find_client_in_text(text)
        if len(matches) > 1:
            return "Hay varios clientes con nombres similares. Especifica el nombre completo."
        normalized = _plain(text)
        expense_context = any(token in normalized for token in ("gasto", "pague", "gaste", "transferencia que hice", "que hice", "pago que hice"))
        target_direction = "expense" if expense_context else "income"
        if voucher:
            movements = find_voucher_matches(voucher)
        elif client:
            movements = search_movements(query=str(client["name"]), direction="income", limit=20)
        elif "ultimo" in normalized or "ultima" in normalized:
            movements = search_movements(direction=target_direction, limit=20)
        else:
            return "Indica el cliente o número de voucher al que debo vincular el comprobante."
        movements = [row for row in movements if row.get("status") == "active"]
        if not movements:
            return "No encontré un ingreso activo que coincida con ese cliente o voucher."
        if not voucher and len(movements) > 1:
            # If the user said latest, the newest movement is the intended target;
            # otherwise ask the user to identify it explicitly.
            if client and ("ultimo" not in normalized and "ultima" not in normalized):
                self.awaiting_choice = {"kind": "movement", "items": movements[:8]}
                return self._format_movement_choices(movements[:8])
        if len(movements) > 1 and voucher:
            self.awaiting_choice = {"kind": "movement", "items": movements[:8]}
            return self._format_movement_choices(movements[:8])
        movement = movements[0]
        files = find_recent_downloads(max_days=7, limit=100)
        if not files:
            return "No encontré archivos recientes en la carpeta Descargas."
        if len(files) > 1:
            self.pending = {"kind": "attachment", "payload": {"movement_id": int(movement["id"]), "movement": movement}}
            self.awaiting_choice = {"kind": "file", "items": files[:10]}
            return self._format_file_choices(files[:10], movement)
        self.pending = {"kind": "attachment", "payload": {
            "movement_id": int(movement["id"]), "movement": movement,
            "source_path": files[0]["path"], "file_name": files[0]["name"],
        }}
        return self._attachment_preview(self.pending["payload"])

    @staticmethod
    def _format_movement_choices(items: list[dict[str, Any]]) -> str:
        lines = ["Encontré varios movimientos. Escribe el número del que recibirá la evidencia:"]
        for index, row in enumerate(items, 1):
            lines.append(f"{index}. {row['payment_date']} · {row['counterparty']} · {format_money(row['amount_cents'])} · {row['reason']} · Voucher {row['voucher_number'] or '—'}")
        return "\n".join(lines)

    @staticmethod
    def _format_file_choices(items: list[dict[str, Any]], movement: dict[str, Any]) -> str:
        lines = [
            f"Movimiento seleccionado: #{movement['id']} · {movement['counterparty']} · {format_money(movement['amount_cents'])}.",
            "Encontré varios archivos en Descargas. Escribe el número del comprobante correcto:",
        ]
        for index, item in enumerate(items, 1):
            lines.append(f"{index}. {item['name']} · {item['modified']}")
        return "\n".join(lines)

    def _resolve_choice(self, answer: str) -> str:
        choice_state = self.awaiting_choice
        if not choice_state:
            return "No hay ninguna selección pendiente."
        match = re.search(r"\b(\d{1,2})\b", answer)
        if not match:
            return "Escribe el número de la opción que deseas seleccionar."
        index = int(match.group(1)) - 1
        items = choice_state["items"]
        if index < 0 or index >= len(items):
            return f"Selecciona un número entre 1 y {len(items)}."
        self.awaiting_choice = None
        selected = items[index]
        if choice_state["kind"] == "movement":
            files = find_recent_downloads(max_days=7, limit=100)
            if not files:
                return "No encontré archivos recientes en Descargas."
            movement = selected
            self.pending = {"kind": "attachment", "payload": {"movement_id": int(movement["id"]), "movement": movement}}
            if len(files) > 1:
                self.awaiting_choice = {"kind": "file", "items": files[:10]}
                return self._format_file_choices(files[:10], movement)
            self.pending["payload"].update(source_path=files[0]["path"], file_name=files[0]["name"])
            return self._attachment_preview(self.pending["payload"])
        if choice_state["kind"] == "file":
            assert self.pending and self.pending["kind"] == "attachment"
            self.pending["payload"].update(source_path=selected["path"], file_name=selected["name"])
            return self._attachment_preview(self.pending["payload"])
        return "La selección no es válida."

    @staticmethod
    def _attachment_preview(payload: dict[str, Any]) -> str:
        movement = payload["movement"]
        return (
            "ADJUNTAR EVIDENCIA — revisión\n"
            f"Archivo: {payload['file_name']}\n"
            f"Movimiento: #{movement['id']} · {movement['payment_date']} · {movement['counterparty']}\n"
            f"Importe: {format_money(movement['amount_cents'])}\n"
            "El archivo se copiará a la carpeta de evidencias. Pulsa «Confirmar operación» para adjuntarlo."
        )

    def confirm(self) -> str:
        if self.awaiting_choice:
            return "Primero selecciona una opción de la lista."
        if not self.pending:
            return "No hay ninguna operación pendiente."
        if self.pending.get("awaiting"):
            return "Completa primero la información que falta."
        kind = self.pending["kind"]
        payload = self.pending["payload"]
        try:
            if kind == "movement":
                movement_id = create_movement(**payload)
                result = f"Operación guardada correctamente. Número de movimiento: #{movement_id}."
            elif kind == "client":
                client_id = create_client(**payload)
                result = f"Cliente creado correctamente. Número de cliente: #{client_id}."
            elif kind == "rate":
                rate_id = set_client_rate(payload["client_id"], payload["monthly_amount_cents"], payload["effective_from"])
                result = f"Tarifa actualizada correctamente. Número de tarifa: #{rate_id}."
            elif kind == "attachment":
                evidence_id = attach_evidence_from_download(payload["movement_id"], payload["source_path"])
                result = f"Comprobante adjuntado correctamente. Número de evidencia: #{evidence_id}."
            else:
                return "No reconozco el tipo de operación pendiente."
        except Exception as exc:
            return f"No se pudo completar la operación: {exc}"
        self.pending = None
        self.awaiting_choice = None
        return result

    def cancel(self) -> str:
        if not self.pending and not self.awaiting_choice:
            return "No hay ninguna operación pendiente."
        self.pending = None
        self.awaiting_choice = None
        return "Operación cancelada. No se modificaron los registros."

    @staticmethod
    def _period_label(period: tuple[str, str] | None) -> str:
        if not period:
            return "todo el historial"
        start, end = period
        if start == end:
            return f"el {start}"
        start_date = date.fromisoformat(start)
        end_date = date.fromisoformat(end)
        names = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
        if start_date.month == end_date.month and start_date.year == end_date.year:
            return f"{names[start_date.month - 1]} de {start_date.year}"
        if start_date.year == end_date.year and start_date.month == 1 and end_date.month == 12:
            return f"el año {start_date.year}"
        return f"desde {start} hasta {end}"

    @staticmethod
    def _format_movement_rows(rows: list[dict[str, Any]], limit: int = 12) -> str:
        lines = []
        for row in rows[:limit]:
            amount = format_money(int(row["amount_cents"]))
            if row.get("direction") == "expense":
                amount = f"-{amount}"
            fields = [
                f"#{row['id']}", row["payment_date"], str(row["counterparty"]),
                str(row.get("reason") or "Sin motivo"), amount,
            ]
            if row.get("payment_method"):
                fields.append(str(row["payment_method"]))
            if row.get("voucher_number"):
                fields.append(f"Voucher {row['voucher_number']}")
            if row.get("category"):
                fields.append(str(row["category"]))
            lines.append(" · ".join(fields))
        if len(rows) > limit:
            lines.append(f"Se muestran {limit} de {len(rows)} movimientos.")
        return "\n".join(lines)

    def _answer_query(self, text: str) -> str:
        normalized = _plain(text)
        period = _extract_period_range(text)
        date_from, date_to = period if period else ("", "")
        period_label = self._period_label(period)

        if normalized in {"hola", "buenos dias", "buenas tardes", "buenas noches", "buenas"}:
            return "Hola. ¿Qué información financiera necesitas revisar?"

        client, matches = _find_client_in_text(text)
        if len(matches) > 1:
            return "Encontré varios clientes posibles: " + ", ".join(str(row["name"]) for row in matches) + ". Indica el nombre completo."

        debt_global_terms = (
            "quien me debe", "quienes me deben", "clientes morosos",
            "clientes con deuda", "quien tiene deuda", "quienes tienen deuda",
            "pagos atrasados", "mensualidades vencidas", "deudas vencidas",
        )
        debt_terms = ("deuda", "debe", "deberia", "pendiente", "estado de cuenta", "moroso", "mensualidad vencida")
        if any(term in normalized for term in debt_global_terms):
            debtors = []
            for item in list_clients(active_only=True):
                summary = client_debt_summary(int(item["id"]), date_to or None)
                if summary["pending_cents"] > 0:
                    debtors.append((item["name"], summary["overdue_cents"], summary["pending_cents"]))
            if not debtors:
                return "No hay clientes con cuotas pendientes en el período consultado."
            debtors.sort(key=lambda row: (row[1], row[2]), reverse=True)
            return "Clientes con saldos pendientes:\n" + "\n".join(
                f"{name} · Vencido {format_money(overdue)} · Pendiente total {format_money(pending)}"
                for name, overdue, pending in debtors[:50]
            )

        if any(term in normalized for term in debt_terms):
            if not client:
                return "¿De qué cliente necesitas el estado de cuenta? Escribe su nombre."
            summary = client_debt_summary(int(client["id"]), date_to or None)
            return (
                f"Estado de cuenta de {client['name']} (al {date_to or date.today().isoformat()}):\n"
                f"Total recibido: {format_money(summary['total_received_cents'])}\n"
                f"Total facturado: {format_money(summary['total_billed_cents'])}\n"
                f"Deuda vencida: {format_money(summary['overdue_cents'])}\n"
                f"Pendiente total: {format_money(summary['pending_cents'])}\n"
                f"Mensualidades cubiertas: {summary['fully_paid_months']}\n"
                f"Mensualidades con abono parcial: {summary['partial_months']}\n"
                f"Abonos a períodos futuros: {format_money(summary['future_applied_cents'])}."
            )

        if any(word in normalized for word in ("voucher", "comprobante", "referencia")):
            voucher = _extract_voucher(text)
            if not voucher:
                return "Indica el número del voucher o comprobante que debo buscar."
            rows = find_voucher_matches(voucher)
            if period:
                rows = [row for row in rows if date_from <= row["payment_date"] <= date_to]
            if not rows:
                return f"No encontré movimientos con el voucher {voucher} durante {period_label}."
            return "Coincidencias de voucher:\n" + self._format_movement_rows(rows, 12)

        if any(phrase in normalized for phrase in (
            "lista de clientes", "mostrar clientes", "clientes registrados",
            "cuantos clientes", "cuantas personas", "mis clientes",
        )):
            clients = list_clients(active_only=True)
            if not clients:
                return "Todavía no hay clientes activos registrados."
            lines = [f"{row['name']} · Mensualidad {format_money(row['current_rate_cents'])}" for row in clients[:50]]
            return f"Hay {len(clients)} clientes activos.\n" + "\n".join(lines)

        category = _extract_category(text)
        income_terms = (
            "ingreso", "ingresos", "recibi", "recibido", "recibieron", "cobro", "cobros",
            "cobre", "cobrado", "me pagaron", "me pago", "me ha pagado", "ha pagado",
            "pagos recibidos", "me depositaron", "me transfirieron", "abonaron", "entradas",
        )
        expense_terms = (
            "gasto", "gastos", "egreso", "egresos", "pague", "pague a", "le pague",
            "he pagado", "yo he pagado", "gaste", "compre", "salida", "salidas",
            "transferi", "pagos que hice",
        )
        wants_income = any(term in normalized for term in income_terms)
        wants_expense = any(term in normalized for term in expense_terms)
        if client and not wants_expense and any(term in normalized for term in ("pago", "pagos", "pagado", "ha pagado", "abono", "abonos", "historial")):
            wants_income = True
        direction = "income" if wants_income and not wants_expense else "expense" if wants_expense and not wants_income else "all"

        method = _extract_method(text)
        wants_balance = any(term in normalized for term in ("balance", "saldo general", "saldo total", "diferencia", "resumen financiero"))
        wants_listing = any(term in normalized for term in (
            "muestrame", "mostrar", "lista", "listado", "detalle", "detalles",
            "cuales", "que movimientos", "que pagos", "que ingresos", "que gastos",
            "historial", "ultimos movimientos",
        ))
        wants_count = any(term in normalized for term in ("cuantos", "cuantas", "cantidad de", "numero de movimientos"))
        wants_total = any(term in normalized for term in (
            "cuanto", "cuanta", "total", "suma", "cuanto he", "cuanto recibi",
            "cuanto gaste", "cuanto pague", "cuanto cobre",
        ))
        client_query = bool(client and any(term in normalized for term in (
            "movimiento", "movimientos", "pago", "pagos", "ingreso", "ingresos",
            "gasto", "gastos", "historial", "recibio", "pagado", "ha pagado",
            "pague", "le pague", "he pagado",
        )))

        if wants_balance or (wants_income and wants_expense):
            rows = search_movements(date_from=date_from, date_to=date_to, limit=250000)
            if client:
                rows = [row for row in rows if row.get("client_id") == int(client["id"])]
            income_total = sum(int(row["amount_cents"]) for row in rows if row["direction"] == "income")
            expense_total = sum(int(row["amount_cents"]) for row in rows if row["direction"] == "expense")
            return (
                f"Resumen financiero de {period_label}:\n"
                f"Ingresos: {format_money(income_total)}\n"
                f"Gastos: {format_money(expense_total)}\n"
                f"Balance neto: {format_money(income_total - expense_total)}\n"
                f"Movimientos: {len(rows)}."
            )

        if direction != "all" or category or client_query or period or "ultimos movimientos" in normalized:
            rows = search_movements(
                direction=direction,
                date_from=date_from,
                date_to=date_to,
                query=str(client["name"]) if client and direction == "expense" and client_query else "",
                client_id=int(client["id"]) if client and client_query and direction != "expense" else None,
                category=category,
                limit=250000 if wants_total or wants_count else 100,
            )
            if method:
                rows = [
                    row for row in rows
                    if _plain(str(row.get("payment_method") or "")) == _plain(method)
                ]
            if not rows:
                qualifier = f" para {client['name']}" if client else ""
                category_text = f" en la categoría {category}" if category else ""
                return f"No encontré movimientos{qualifier}{category_text} durante {period_label}."
            total = sum(int(row["amount_cents"]) for row in rows)
            label = "ingresos" if direction == "income" else "gastos" if direction == "expense" else "movimientos"
            if wants_count:
                return f"Encontré {len(rows)} {label} durante {period_label}, por un total de {format_money(total)}."
            if wants_listing or (client_query and not wants_total):
                name = client["name"] if client else "la búsqueda"
                return (
                    f"{len(rows)} {label} de {name} durante {period_label}. "
                    f"Total: {format_money(total)}.\n" + self._format_movement_rows(rows, 15)
                )
            suffix = f" de {client['name']}" if client else ""
            category_suffix = f" en {category}" if category else ""
            return f"Total de {label}{suffix}{category_suffix} durante {period_label}: {format_money(total)} en {len(rows)} movimiento(s)."

        if any(word in normalized for word in ("busca", "buscar", "encuentra", "localiza", "movimiento", "movimientos")):
            query = re.sub(
                r"\b(busca|buscar|encuentra|localiza|muestrame|mostrar|el|la|los|las|por favor|movimiento|movimientos)\b",
                " ", text, flags=re.IGNORECASE,
            )
            query = str(client["name"]) if client else _clean(query)
            rows = search_movements(query=query, date_from=date_from, date_to=date_to, limit=100)
            if not rows:
                return f"No encontré movimientos que coincidan con «{_clean(query)}»."
            return "Movimientos encontrados:\n" + self._format_movement_rows(rows, 15)

        if client:
            return f"Encontré al cliente {client['name']}. Puedes preguntarme por su deuda, pagos, historial o mensualidad."
        if period:
            return f"Entendí el período {period_label}. Indícame si quieres consultar ingresos, gastos, balance o movimientos."
        return (
            "No terminé de identificar qué necesitas. Puedes preguntarme por ingresos, "
            "gastos, balance, clientes, deudas, categorías, movimientos o vouchers; "
            "también puedes indicar un mes, año o rango de fechas."
        )
