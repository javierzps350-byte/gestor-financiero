import csv
from pathlib import Path

from src.domain.money import format_money
from src.services.finance_service import search_movements, list_clients, client_debt_summary


def export_movements_csv(destination: str, **filters) -> int:
    rows = search_movements(include_void=True, **filters)
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(["ID", "Estado", "Tipo", "Fecha", "Persona", "Motivo", "Categoría", "Importe", "Método", "Voucher", "Notas"])
        for row in rows:
            writer.writerow([
                row["id"], row["status"], "Ingreso" if row["direction"] == "income" else "Gasto",
                row["payment_date"], row["counterparty"], row["reason"], row.get("category") or "Otros",
                format_money(row["amount_cents"]), row["payment_method"], row["voucher_number"] or "", row["notes"] or "",
            ])
    return len(rows)


def export_debts_csv(destination: str, as_of: str | None = None) -> int:
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow(["Cliente", "Tarifa mensual", "Total recibido", "Meses cubiertos", "Abono futuro", "Deuda vencida", "Pendiente total"])
        clients = list_clients(active_only=True)
        for client in clients:
            summary = client_debt_summary(int(client["id"]), as_of)
            writer.writerow([
                client["name"], format_money(client["current_rate_cents"]),
                format_money(summary["total_received_cents"]), summary["fully_paid_months"],
                format_money(summary["future_applied_cents"]), format_money(summary["overdue_cents"]),
                format_money(summary["pending_cents"]),
            ])
    return len(clients)
