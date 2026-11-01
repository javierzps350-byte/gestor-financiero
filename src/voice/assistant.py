"""Procesamiento ligero de comandos escritos; no utiliza modelos de IA."""
import re

from src.domain.money import format_money
from src.services.finance_service import client_debt_summary, list_clients, dashboard_summary, search_movements


def handle_text_command(command: str) -> str:
    text = command.strip()
    lowered = text.casefold()
    if not text:
        return "Escribe una consulta. Ejemplos: 'ingresos del mes', 'gastos del mes' o 'deuda de Carlos'."

    if "ingresos" in lowered and "mes" in lowered:
        result = dashboard_summary()
        return f"Los ingresos registrados este mes son {format_money(result['income_month_cents'])}."
    if "gastos" in lowered and "mes" in lowered:
        result = dashboard_summary()
        return f"Los gastos registrados este mes son {format_money(result['expenses_month_cents'])}."
    if "voucher" in lowered or "comprobante" in lowered:
        match = re.search(r"(?:voucher|comprobante)\s*(?:n(?:o|úm)?\.?\s*)?([a-z0-9-]+)", lowered)
        number = match.group(1) if match else lowered
        rows = search_movements(voucher=number, limit=20)
        if not rows:
            return "No encontré movimientos con ese número de voucher."
        return "Encontré: " + "; ".join(
            f"{row['payment_date']} · {row['counterparty']} · {format_money(row['amount_cents'])} · {row['reason']}"
            for row in rows[:10]
        )
    if "deuda" in lowered or "debe" in lowered:
        name = lowered.replace("cuánto", "").replace("cuanto", "").replace("deuda", "").replace("debe", "").replace("tiene", "").replace("de", "").replace("el", "").replace("la", "").replace("cliente", "").replace("?", " ").strip(" :")
        matches = [c for c in list_clients(active_only=True) if name and name in c["name"].casefold()]
        if not matches:
            return "No identifiqué al cliente. Escribe el nombre como aparece en el registro."
        if len(matches) > 1:
            return "Hay varios clientes con ese nombre: " + ", ".join(c["name"] for c in matches[:8])
        client = matches[0]
        summary = client_debt_summary(int(client["id"]))
        return (
            f"Estado de {client['name']}: deuda vencida {format_money(summary['overdue_cents'])}; "
            f"pendiente total de cuotas generadas {format_money(summary['pending_cents'])}; "
            f"meses cubiertos {summary['fully_paid_months']}; "
            f"abonos aplicados a períodos futuros {format_money(summary['future_applied_cents'])}."
        )
    return "Todavía no reconozco esa instrucción. Puedes consultar ingresos del mes, gastos del mes, una deuda o un número de voucher."
