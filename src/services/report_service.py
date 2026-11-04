"""Filtered report exporters: PDF, XLSX, XML, TXT and CSV.

The XLSX writer uses the Open XML package format and only Python's standard
library, keeping the installed application lightweight. PDF output is a
small, paginated vector PDF writer using the built-in WinAnsi Helvetica fonts.
"""
from __future__ import annotations

import csv
import json
import math
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Any

from src.domain.money import format_money
from src.services.finance_service import search_movements, list_clients, client_debt_summary, list_client_charges


MOVEMENT_FIELDS = [
    ("id", "ID"), ("payment_date", "Fecha de pago"),
    ("registered_at", "Fecha de registro"), ("direction_label", "Tipo"),
    ("counterparty", "Persona / empresa"), ("reason", "Motivo"),
    ("client_name", "Cliente asociado"), ("category", "Categoría"),
    ("amount", "Importe"), ("payment_method", "Tipo de pago"),
    ("voucher_number", "Voucher"), ("evidence_count", "Evidencias"),
    ("status_label", "Estado"), ("notes", "Observaciones"),
]

DEBT_FIELDS = [
    ("client", "Cliente"), ("period", "Período"), ("due_date", "Vencimiento"),
    ("monthly_amount", "Mensualidad"), ("applied", "Abonado"),
    ("remaining", "Pendiente"), ("status", "Estado"),
]


def money_decimal(cents: int) -> float:
    return round(int(cents or 0) / 100, 2)


def _movement_record(row: dict[str, Any]) -> dict[str, Any]:
    income = row.get("direction") == "income"
    void = row.get("status") == "void"
    return {
        "id": int(row.get("id") or 0),
        "payment_date": str(row.get("payment_date") or ""),
        "registered_at": str(row.get("registered_at") or ""),
        "direction": str(row.get("direction") or ""),
        "direction_label": "Ingreso" if income else "Gasto",
        "counterparty": str(row.get("counterparty") or ""),
        "reason": str(row.get("reason") or ""),
        "category": str(row.get("category") or ("Ingresos" if income else "Otros")),
        "amount_cents": int(row.get("amount_cents") or 0),
        "amount": money_decimal(row.get("amount_cents") or 0),
        "payment_method": str(row.get("payment_method") or ""),
        "voucher_number": str(row.get("voucher_number") or ""),
        "status": str(row.get("status") or "active"),
        "status_label": "Anulado" if void else "Vigente",
        "notes": str(row.get("notes") or ""),
        "client_id": row.get("client_id"),
        "client_name": str(row.get("client_name") or ""),
        "evidence_count": int(row.get("evidence_count") or 0),
    }


def build_movement_report(rows: list[dict[str, Any]], filters: dict[str, Any] | None = None, title: str = "Movimientos") -> dict[str, Any]:
    records = [_movement_record(dict(row)) for row in rows]
    active = [row for row in records if row["status"] != "void"]
    income = sum(row["amount_cents"] for row in active if row["direction"] == "income")
    expenses = sum(row["amount_cents"] for row in active if row["direction"] == "expense")
    return {
        "kind": "movements",
        "title": title,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "filters": _clean_filters(filters or {}),
        "summary": {
            "records": len(records),
            "active_records": len(active),
            "void_records": len(records) - len(active),
            "income_cents": income,
            "expenses_cents": expenses,
            "net_cents": income - expenses,
        },
        "records": records,
    }


def build_debt_report(as_of: str | None = None, client_id: int | None = None) -> dict[str, Any]:
    reference = as_of or datetime.now().date().isoformat()
    clients = list_clients(active_only=False)
    if client_id is not None:
        clients = [client for client in clients if int(client["id"]) == int(client_id)]
    summaries: list[dict[str, Any]] = []
    details: list[dict[str, Any]] = []
    for client in clients:
        cid = int(client["id"])
        summary = client_debt_summary(cid, reference)
        name = str(client["name"])
        summaries.append({
            "client_id": cid,
            "client": name,
            "active": bool(client.get("is_active", 1)),
            "monthly_rate_cents": int(client.get("current_rate_cents") or 0),
            "total_received_cents": int(summary["total_received_cents"]),
            "fully_paid_months": int(summary["fully_paid_months"]),
            "partial_months": int(summary["partial_months"]),
            "future_applied_cents": int(summary["future_applied_cents"]),
            "overdue_cents": int(summary["overdue_cents"]),
            "pending_cents": int(summary["pending_cents"]),
        })
        for charge in list_client_charges(cid, reference):
            due = int(charge["amount_due_cents"])
            applied = int(charge["applied_cents"])
            remaining = int(charge["remaining_cents"])
            if remaining == 0:
                status = "Cubierto"
            elif applied > 0:
                status = "Abonado"
            elif str(charge["due_date"]) < reference:
                status = "Vencido"
            else:
                status = "Pendiente"
            details.append({
                "client_id": cid, "client": name,
                "period_start": str(charge["period_start"]),
                "period_end": str(charge["period_end"]),
                "period": f"{charge['period_start']} a {charge['period_end']}",
                "due_date": str(charge["due_date"]),
                "amount_due_cents": due, "monthly_amount": money_decimal(due),
                "applied_cents": applied, "applied": money_decimal(applied),
                "remaining_cents": remaining, "remaining": money_decimal(remaining),
                "status": status,
            })
    return {
        "kind": "debts",
        "title": "Estado de cuentas y mensualidades",
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
        "filters": {"fecha_corte": reference, "client_id": client_id or "Todos"},
        "summary": {
            "clients": len(summaries),
            "received_cents": sum(r["total_received_cents"] for r in summaries),
            "overdue_cents": sum(r["overdue_cents"] for r in summaries),
            "pending_cents": sum(r["pending_cents"] for r in summaries),
            "future_applied_cents": sum(r["future_applied_cents"] for r in summaries),
            "periods": len(details),
        },
        "clients": summaries,
        "records": details,
    }


def _clean_filters(filters: dict[str, Any]) -> dict[str, Any]:
    return {str(k): (v if isinstance(v, (str, int, float, bool)) or v is None else str(v))
            for k, v in filters.items() if v not in (None, "")}


def export_movements_csv(destination: str, **filters) -> int:
    rows = search_movements(include_void=True, **filters)
    report = build_movement_report(rows, filters, "Movimientos")
    export_report(destination, report)
    return len(rows)


def export_debts_csv(destination: str, as_of: str | None = None) -> int:
    report = build_debt_report(as_of)
    export_report(destination, report)
    return len(report["clients"])


def export_report(destination: str | Path, report: dict[str, Any]) -> int:
    """Export a filtered query using the format selected by the file extension."""
    path = Path(destination)
    path.parent.mkdir(parents=True, exist_ok=True)
    suffix = path.suffix.lower()
    if suffix == ".pdf":
        _write_pdf(path, report)
    elif suffix == ".xlsx":
        _write_xlsx(path, report)
    elif suffix == ".xml":
        _write_xml(path, report)
    elif suffix == ".txt":
        _write_txt(path, report)
    elif suffix == ".csv":
        _write_csv(path, report)
    else:
        raise ValueError("Formato no compatible. Selecciona PDF, Excel, XML, TXT o CSV.")
    return len(report.get("records", []))


def _report_headers(report):
    return MOVEMENT_FIELDS if report["kind"] == "movements" else DEBT_FIELDS


def _row_values(report, row):
    if report["kind"] == "movements":
        return [row.get(key, "") for key, _label in MOVEMENT_FIELDS]
    return [row.get(key, "") for key, _label in DEBT_FIELDS]


def _write_csv(path: Path, report: dict[str, Any]):
    headers = _report_headers(report)
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file, delimiter=";")
        writer.writerow([label for _key, label in headers])
        for row in report.get("records", []):
            values = _row_values(report, row)
            if report["kind"] == "movements":
                values[8] = format_money(row.get("amount_cents", 0))
            else:
                values[3] = format_money(row.get("amount_due_cents", 0))
                values[4] = format_money(row.get("applied_cents", 0))
                values[5] = format_money(row.get("remaining_cents", 0))
            writer.writerow(values)


def _write_xml(path: Path, report: dict[str, Any]):
    root = ET.Element("gestor_financiero_report", {
        "format_version": "1",
        "kind": report["kind"],
        "generated_at": report["generated_at"],
    })
    ET.SubElement(root, "title").text = report["title"]
    filters = ET.SubElement(root, "filters")
    for key, value in report.get("filters", {}).items():
        ET.SubElement(filters, "filter", {"name": str(key)}).text = str(value)
    summary = ET.SubElement(root, "summary")
    for key, value in report.get("summary", {}).items():
        ET.SubElement(summary, key).text = str(value)
    if report["kind"] == "debts":
        clients_node = ET.SubElement(root, "clients")
        for row in report.get("clients", []):
            node = ET.SubElement(clients_node, "client")
            for key, value in row.items():
                ET.SubElement(node, key).text = "" if value is None else str(value)
    records = ET.SubElement(root, "records")
    for row in report.get("records", []):
        node = ET.SubElement(records, "record")
        for key, value in row.items():
            ET.SubElement(node, key).text = "" if value is None else str(value)
    tree = ET.ElementTree(root)
    try:
        ET.indent(tree, space="  ")
    except AttributeError:
        pass
    tree.write(path, encoding="utf-8", xml_declaration=True)


def _write_txt(path: Path, report: dict[str, Any]):
    lines = [report["title"], "=" * max(12, len(report["title"])),
             f"Generado: {report['generated_at']}", "Filtros:"]
    for key, value in report.get("filters", {}).items():
        lines.append(f"  {key}: {value}")
    lines.append("")
    lines.append("RESUMEN")
    for key, value in report.get("summary", {}).items():
        if key.endswith("_cents"):
            label = key.removesuffix("_cents").replace("_", " ").capitalize()
            lines.append(f"  {label}: {format_money(value)}")
        else:
            lines.append(f"  {key.replace('_', ' ').capitalize()}: {value}")
    lines.extend(["", "DETALLE", "-" * 72])
    for index, row in enumerate(report.get("records", []), start=1):
        lines.append(f"Registro {index}")
        for key, value in row.items():
            if key.endswith("_cents") or key in {"amount", "monthly_amount", "applied", "remaining"}:
                continue
            lines.append(f"  {key.replace('_', ' ').capitalize()}: {value}")
        if report["kind"] == "movements":
            lines.append(f"  Importe: {format_money(row.get('amount_cents', 0))}")
        else:
            lines.append(f"  Mensualidad: {format_money(row.get('amount_due_cents', 0))}")
            lines.append(f"  Abonado: {format_money(row.get('applied_cents', 0))}")
            lines.append(f"  Pendiente: {format_money(row.get('remaining_cents', 0))}")
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


# ---------- Minimal OOXML writer (no openpyxl / runtime dependencies) ----------

_NS_MAIN = "http://schemas.openxmlformats.org/spreadsheetml/2006/main"
_NS_REL = "http://schemas.openxmlformats.org/officeDocument/2006/relationships"
_NS_PKG_REL = "http://schemas.openxmlformats.org/package/2006/relationships"
_NS_CT = "http://schemas.openxmlformats.org/package/2006/content-types"
ET.register_namespace("", _NS_MAIN)
ET.register_namespace("r", _NS_REL)


def _col_name(index: int) -> str:
    result = ""
    while index:
        index, rem = divmod(index - 1, 26)
        result = chr(65 + rem) + result
    return result


def _sheet_xml(rows, header_row: int | None, currency_columns=()):
    root = ET.Element(f"{{{_NS_MAIN}}}worksheet")
    sheet_pr = ET.SubElement(root, f"{{{_NS_MAIN}}}sheetPr")
    ET.SubElement(sheet_pr, f"{{{_NS_MAIN}}}pageSetUpPr", {"fitToPage": "1", "autoPageBreaks": "0"})
    views = ET.SubElement(root, f"{{{_NS_MAIN}}}sheetViews")
    view = ET.SubElement(views, f"{{{_NS_MAIN}}}sheetView", {"workbookViewId": "0"})
    if header_row:
        ET.SubElement(view, f"{{{_NS_MAIN}}}pane", {
            "ySplit": str(header_row), "topLeftCell": f"A{header_row + 1}",
            "activePane": "bottomLeft", "state": "frozen",
        })
    ET.SubElement(root, f"{{{_NS_MAIN}}}sheetFormatPr", {"defaultRowHeight": "19"})
    max_cols = max((len(row) for row in rows), default=1)
    cols = ET.SubElement(root, f"{{{_NS_MAIN}}}cols")
    for col in range(1, max_cols + 1):
        lengths = [len(str(row[col - 1])) for row in rows if col <= len(row) and row[col - 1] is not None]
        width = min(42, max(12, max(lengths, default=12) + 2))
        if col in currency_columns:
            width = 16
        ET.SubElement(cols, f"{{{_NS_MAIN}}}col", {"min": str(col), "max": str(col), "width": str(width), "customWidth": "1"})
    sheet_data = ET.SubElement(root, f"{{{_NS_MAIN}}}sheetData")
    for row_index, row in enumerate(rows, start=1):
        row_node = ET.SubElement(sheet_data, f"{{{_NS_MAIN}}}row", {"r": str(row_index)})
        for col_index, value in enumerate(row, start=1):
            if value is None:
                continue
            ref = f"{_col_name(col_index)}{row_index}"
            if isinstance(value, bool):
                cell = ET.SubElement(row_node, f"{{{_NS_MAIN}}}c", {"r": ref, "t": "b"})
                ET.SubElement(cell, f"{{{_NS_MAIN}}}v").text = "1" if value else "0"
            elif isinstance(value, (int, float, Decimal)):
                style = "4" if col_index in currency_columns else "0"
                cell = ET.SubElement(row_node, f"{{{_NS_MAIN}}}c", {"r": ref, "s": style})
                ET.SubElement(cell, f"{{{_NS_MAIN}}}v").text = str(value)
            else:
                style = "1" if row_index == 1 else "2" if row_index == 2 else "3" if header_row == row_index else "0"
                cell = ET.SubElement(row_node, f"{{{_NS_MAIN}}}c", {"r": ref, "t": "inlineStr", "s": str(style)})
                inline = ET.SubElement(cell, f"{{{_NS_MAIN}}}is")
                text = ET.SubElement(inline, f"{{{_NS_MAIN}}}t", {"{http://www.w3.org/XML/1998/namespace}space": "preserve"})
                text.text = str(value)
    if header_row and len(rows) > header_row:
        ET.SubElement(root, f"{{{_NS_MAIN}}}autoFilter", {
            "ref": f"A{header_row}:{_col_name(max_cols)}{len(rows)}"
        })
    if max_cols > 1 and len(rows) >= 2:
        last_col = _col_name(max_cols)
        merge_ranges = [f"A1:{last_col}1", f"A2:{last_col}2"]
        if len(rows) >= 3 and rows[2] and rows[2][0] == "Filtros":
            merge_ranges.append(f"B3:{last_col}3")
        merges = ET.SubElement(root, f"{{{_NS_MAIN}}}mergeCells", {"count": str(len(merge_ranges))})
        for merge_range in merge_ranges:
            ET.SubElement(merges, f"{{{_NS_MAIN}}}mergeCell", {"ref": merge_range})
    ET.SubElement(root, f"{{{_NS_MAIN}}}printOptions", {"horizontalCentered": "0", "verticalCentered": "0"})
    ET.SubElement(root, f"{{{_NS_MAIN}}}pageMargins", {
        "left": "0.25", "right": "0.25", "top": "0.5", "bottom": "0.5", "header": "0.2", "footer": "0.2",
    })
    ET.SubElement(root, f"{{{_NS_MAIN}}}pageSetup", {
        "paperSize": "8" if max_cols >= 13 else "9",
        "orientation": "landscape", "fitToWidth": "1", "fitToHeight": "0",
    })
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _styles_xml():
    root = ET.Element(f"{{{_NS_MAIN}}}styleSheet")
    numfmts = ET.SubElement(root, f"{{{_NS_MAIN}}}numFmts", {"count": "1"})
    ET.SubElement(numfmts, f"{{{_NS_MAIN}}}numFmt", {"numFmtId": "164", "formatCode": '"$"#,##0.00;[Red]-"$"#,##0.00'})
    fonts = ET.SubElement(root, f"{{{_NS_MAIN}}}fonts", {"count": "4"})
    for bold, color, size in [(False, "FF243449", 10), (True, "FFFFFFFF", 18), (False, "FF8190A2", 10), (True, "FFFFFFFF", 10)]:
        font = ET.SubElement(fonts, f"{{{_NS_MAIN}}}font")
        if bold: ET.SubElement(font, f"{{{_NS_MAIN}}}b")
        ET.SubElement(font, f"{{{_NS_MAIN}}}sz", {"val": str(size)})
        ET.SubElement(font, f"{{{_NS_MAIN}}}color", {"rgb": color})
        ET.SubElement(font, f"{{{_NS_MAIN}}}name", {"val": "Aptos"})
    fills = ET.SubElement(root, f"{{{_NS_MAIN}}}fills", {"count": "3"})
    ET.SubElement(fills, f"{{{_NS_MAIN}}}fill").append(ET.Element(f"{{{_NS_MAIN}}}patternFill", {"patternType": "none"}))
    ET.SubElement(fills, f"{{{_NS_MAIN}}}fill").append(ET.Element(f"{{{_NS_MAIN}}}patternFill", {"patternType": "gray125"}))
    fill = ET.SubElement(fills, f"{{{_NS_MAIN}}}fill")
    pattern = ET.SubElement(fill, f"{{{_NS_MAIN}}}patternFill", {"patternType": "solid"})
    ET.SubElement(pattern, f"{{{_NS_MAIN}}}fgColor", {"rgb": "FF2BAE9B"})
    ET.SubElement(pattern, f"{{{_NS_MAIN}}}bgColor", {"indexed": "64"})
    borders = ET.SubElement(root, f"{{{_NS_MAIN}}}borders", {"count": "1"})
    border = ET.SubElement(borders, f"{{{_NS_MAIN}}}border")
    for side in ("left", "right", "top", "bottom", "diagonal"):
        ET.SubElement(border, f"{{{_NS_MAIN}}}{side}")
    ET.SubElement(root, f"{{{_NS_MAIN}}}cellStyleXfs", {"count": "1"}).append(ET.Element(f"{{{_NS_MAIN}}}xf", {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0"}))
    xfs = ET.SubElement(root, f"{{{_NS_MAIN}}}cellXfs", {"count": "5"})
    ET.SubElement(xfs, f"{{{_NS_MAIN}}}xf", {"numFmtId": "0", "fontId": "0", "fillId": "0", "borderId": "0", "xfId": "0"})
    ET.SubElement(xfs, f"{{{_NS_MAIN}}}xf", {"numFmtId": "0", "fontId": "1", "fillId": "2", "borderId": "0", "xfId": "0", "applyAlignment": "1"}).append(ET.Element(f"{{{_NS_MAIN}}}alignment", {"vertical": "center"}))
    ET.SubElement(xfs, f"{{{_NS_MAIN}}}xf", {"numFmtId": "0", "fontId": "2", "fillId": "0", "borderId": "0", "xfId": "0"})
    ET.SubElement(xfs, f"{{{_NS_MAIN}}}xf", {"numFmtId": "0", "fontId": "3", "fillId": "2", "borderId": "0", "xfId": "0", "applyAlignment": "1"}).append(ET.Element(f"{{{_NS_MAIN}}}alignment", {"horizontal": "center", "vertical": "center", "wrapText": "1"}))
    ET.SubElement(xfs, f"{{{_NS_MAIN}}}xf", {"numFmtId": "164", "fontId": "0", "fillId": "0", "borderId": "0", "xfId": "0"})
    cell_styles = ET.SubElement(root, f"{{{_NS_MAIN}}}cellStyles", {"count": "1"})
    ET.SubElement(cell_styles, f"{{{_NS_MAIN}}}cellStyle", {"name": "Normal", "xfId": "0", "builtinId": "0"})
    return ET.tostring(root, encoding="utf-8", xml_declaration=True)


def _write_xlsx(path: Path, report: dict[str, Any]):
    if report["kind"] == "movements":
        headers = [label for _key, label in MOVEMENT_FIELDS]
        detail_rows = []
        for row in report.get("records", []):
            detail_rows.append([row.get(key, "") for key, _label in MOVEMENT_FIELDS])
        title = report["title"]
        summary_rows = [
            [title], [f"Generado: {report['generated_at']}"],
            ["Filtros", json.dumps(report.get("filters", {}), ensure_ascii=False)],
            ["Registros", report["summary"]["records"]],
            ["Ingresos", money_decimal(report["summary"]["income_cents"])],
            ["Gastos", money_decimal(report["summary"]["expenses_cents"])],
            ["Balance neto", money_decimal(report["summary"]["net_cents"])],
        ]
        detail_sheet = summary_rows + [[None] * len(headers)] + [headers] + detail_rows
        header_row = len(summary_rows) + 2
        currency_columns = {9}
        sheets = [("Resumen y movimientos", detail_sheet, header_row, currency_columns)]
    else:
        client_headers = ["ID", "Cliente", "Tarifa", "Recibido", "Meses cubiertos", "Meses parciales", "Abono futuro", "Deuda vencida", "Pendiente total", "Activo"]
        client_rows = [[
            row["client_id"], row["client"], money_decimal(row["monthly_rate_cents"]),
            money_decimal(row["total_received_cents"]), row["fully_paid_months"], row["partial_months"],
            money_decimal(row["future_applied_cents"]), money_decimal(row["overdue_cents"]),
            money_decimal(row["pending_cents"]), "Sí" if row["active"] else "No",
        ] for row in report.get("clients", [])]
        detail_headers = [label for _key, label in DEBT_FIELDS]
        detail_rows = [[row["client"], row["period"], row["due_date"], row["monthly_amount"], row["applied"], row["remaining"], row["status"]] for row in report.get("records", [])]
        summary_rows = [
            [report["title"]], [f"Fecha de corte: {report['filters'].get('fecha_corte', '')}"],
            ["Clientes", report["summary"]["clients"]],
            ["Total recibido", money_decimal(report["summary"]["received_cents"])],
            ["Deuda vencida", money_decimal(report["summary"]["overdue_cents"])],
            ["Pendiente total", money_decimal(report["summary"]["pending_cents"])],
            ["Abonos futuros", money_decimal(report["summary"]["future_applied_cents"])],
        ]
        client_sheet = summary_rows + [[None] * len(client_headers)] + [client_headers] + client_rows
        month_sheet = [["Detalle de mensualidades"], [f"Fecha de corte: {report['filters'].get('fecha_corte', '')}"], [None] * len(detail_headers), detail_headers] + detail_rows
        sheets = [
            ("Resumen clientes", client_sheet, len(summary_rows) + 2, {3, 4, 7, 8, 9}),
            ("Mensualidades", month_sheet, 4, {4, 5, 6}),
        ]

    content_types = ET.Element(f"{{{_NS_CT}}}Types")
    ET.SubElement(content_types, f"{{{_NS_CT}}}Default", {"Extension": "rels", "ContentType": "application/vnd.openxmlformats-package.relationships+xml"})
    ET.SubElement(content_types, f"{{{_NS_CT}}}Default", {"Extension": "xml", "ContentType": "application/xml"})
    ET.SubElement(content_types, f"{{{_NS_CT}}}Override", {"PartName": "/xl/workbook.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"})
    ET.SubElement(content_types, f"{{{_NS_CT}}}Override", {"PartName": "/xl/styles.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.styles+xml"})
    for i in range(len(sheets)):
        ET.SubElement(content_types, f"{{{_NS_CT}}}Override", {"PartName": f"/xl/worksheets/sheet{i+1}.xml", "ContentType": "application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"})

    package_rels = ET.Element(f"{{{_NS_PKG_REL}}}Relationships")
    ET.SubElement(package_rels, f"{{{_NS_PKG_REL}}}Relationship", {"Id": "rId1", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument", "Target": "xl/workbook.xml"})

    workbook = ET.Element(f"{{{_NS_MAIN}}}workbook")
    ET.SubElement(workbook, f"{{{_NS_MAIN}}}bookViews").append(ET.Element(f"{{{_NS_MAIN}}}workbookView", {"xWindow": "0", "yWindow": "0", "windowWidth": "18000", "windowHeight": "10000"}))
    sheet_list = ET.SubElement(workbook, f"{{{_NS_MAIN}}}sheets")
    wb_rels = ET.Element(f"{{{_NS_PKG_REL}}}Relationships")
    for i, (name, _rows, _header, _currencies) in enumerate(sheets, start=1):
        ET.SubElement(sheet_list, f"{{{_NS_MAIN}}}sheet", {"name": name, "sheetId": str(i), f"{{{_NS_REL}}}id": f"rId{i}"})
        ET.SubElement(wb_rels, f"{{{_NS_PKG_REL}}}Relationship", {"Id": f"rId{i}", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet", "Target": f"worksheets/sheet{i}.xml"})
    ET.SubElement(wb_rels, f"{{{_NS_PKG_REL}}}Relationship", {"Id": f"rId{len(sheets)+1}", "Type": "http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles", "Target": "styles.xml"})

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", ET.tostring(content_types, encoding="utf-8", xml_declaration=True))
        archive.writestr("_rels/.rels", ET.tostring(package_rels, encoding="utf-8", xml_declaration=True))
        archive.writestr("xl/workbook.xml", ET.tostring(workbook, encoding="utf-8", xml_declaration=True))
        archive.writestr("xl/_rels/workbook.xml.rels", ET.tostring(wb_rels, encoding="utf-8", xml_declaration=True))
        archive.writestr("xl/styles.xml", _styles_xml())
        for i, (_name, rows, header, currencies) in enumerate(sheets, start=1):
            archive.writestr(f"xl/worksheets/sheet{i}.xml", _sheet_xml(rows, header, currencies))


# ---------- Small vector PDF writer ----------


def _pdf_string(value: Any) -> bytes:
    raw = str(value if value is not None else "").encode("cp1252", errors="replace")
    escaped = bytearray()
    for byte in raw:
        if byte in (40, 41, 92):
            escaped.extend(b"\\" + bytes([byte]))
        elif byte < 32 or byte >= 127:
            escaped.extend(f"\\{byte:03o}".encode("ascii"))
        else:
            escaped.append(byte)
    return bytes(escaped)


def _pdf_color(hex_color: str):
    value = hex_color.lstrip("#")
    return tuple(int(value[i:i + 2], 16) / 255 for i in (0, 2, 4))


def _pdf_text(commands, x, y, text, size=8, color="#243449", bold=False):
    r, g, b = _pdf_color(color)
    font = "F2" if bold else "F1"
    commands.append(
        f"BT /{font} {size} Tf {r:.3f} {g:.3f} {b:.3f} rg 1 0 0 1 {x:.2f} {y:.2f} Tm ".encode("ascii")
        + b"(" + _pdf_string(text) + b") Tj ET"
    )


def _pdf_rect(commands, x, y, width, height, fill):
    r, g, b = _pdf_color(fill)
    commands.append(f"q {r:.3f} {g:.3f} {b:.3f} rg {x:.2f} {y:.2f} {width:.2f} {height:.2f} re f Q".encode("ascii"))


def _pdf_line(commands, x1, y1, x2, y2, color="#DDE5EC", width=0.6):
    r, g, b = _pdf_color(color)
    commands.append(f"q {r:.3f} {g:.3f} {b:.3f} RG {width:.2f} w {x1:.2f} {y1:.2f} m {x2:.2f} {y2:.2f} l S Q".encode("ascii"))


def _short(value: Any, max_chars: int) -> str:
    text = " ".join(str(value or "").split())
    if len(text) > max_chars:
        return text[:max_chars - 1].rstrip() + "…"
    return text


def _pdf_pages(report):
    page_width, page_height = 842, 595  # A4 landscape, points
    margin = 28
    pages = []
    records = report.get("records", [])
    row_height = 24
    rows_per_page = 15
    total_pages = max(1, math.ceil(len(records) / rows_per_page))
    if report["kind"] == "movements":
        # The PDF is an overview table. Long notes are shortened to keep the
        # whole record visible; XLSX/XML/TXT/CSV retain every character.
        columns = [
            ("id", "ID", 25), ("payment_date", "Fecha", 52),
            ("registered_at", "Registro", 60), ("direction_label", "Tipo", 36),
            ("counterparty", "Persona", 70), ("client_name", "Cliente", 75),
            ("reason", "Motivo", 85), ("category", "Categoría", 55),
            ("amount_cents", "Importe", 55), ("payment_method", "Método", 55),
            ("voucher_number", "Voucher", 60), ("evidence_count", "Archivos", 30),
            ("status_label", "Estado", 45), ("notes", "Notas", 50),
        ]
    else:
        columns = [
            ("client_id", "ID", 28), ("client", "Cliente", 110),
            ("period", "Período", 130), ("due_date", "Vencimiento", 72),
            ("amount_due_cents", "Mensualidad", 72),
            ("applied_cents", "Abonado", 72), ("remaining_cents", "Pendiente", 72),
            ("status", "Estado", 68),
        ]
    table_width = sum(col[2] for col in columns)
    scale = (page_width - 2 * margin) / table_width
    columns = [(key, label, width * scale) for key, label, width in columns]

    for page_index in range(total_pages):
        page_rows = records[page_index * rows_per_page:(page_index + 1) * rows_per_page]
        commands = []
        _pdf_rect(commands, 0, 0, page_width, page_height, "#FFFFFF")
        _pdf_rect(commands, 0, page_height - 9, page_width, 9, "#2BAE9B")
        _pdf_text(commands, margin, 550, report["title"], 18, "#243449", True)
        _pdf_text(commands, margin, 533, f"Generado: {report['generated_at']}  |  Página {page_index + 1} de {total_pages}", 8, "#8190A2")
        filter_text = " · ".join(f"{key}: {value}" for key, value in report.get("filters", {}).items())
        _pdf_text(commands, margin, 519, _short(filter_text, 125) or "Sin filtros adicionales", 8, "#657489")

        summary = report.get("summary", {})
        if report["kind"] == "movements":
            metrics = [
                ("REGISTROS", str(summary.get("records", 0))),
                ("INGRESOS", format_money(summary.get("income_cents", 0))),
                ("GASTOS", format_money(summary.get("expenses_cents", 0))),
                ("BALANCE", format_money(summary.get("net_cents", 0))),
            ]
        else:
            metrics = [
                ("CLIENTES", str(summary.get("clients", 0))),
                ("RECIBIDO", format_money(summary.get("received_cents", 0))),
                ("DEUDA VENCIDA", format_money(summary.get("overdue_cents", 0))),
                ("PENDIENTE", format_money(summary.get("pending_cents", 0))),
            ]
        box_gap = 8
        box_width = (page_width - 2 * margin - box_gap * 3) / 4
        for index, (label, value) in enumerate(metrics):
            x = margin + index * (box_width + box_gap)
            _pdf_rect(commands, x, 466, box_width, 40, "#F1F7F6")
            _pdf_text(commands, x + 10, 491, label, 7, "#8190A2", True)
            _pdf_text(commands, x + 10, 475, value, 11, "#243449", True)

        header_y = 439
        _pdf_rect(commands, margin, header_y - 4, page_width - 2 * margin, 22, "#243F51")
        x = margin
        header_font_size = 6.2 if report["kind"] == "movements" else 7
        for _key, label, width in columns:
            _pdf_text(commands, x + 3, header_y + 4, label, header_font_size, "#FFFFFF", True)
            x += width
        row_y = header_y - 27
        body_font_size = 5.7 if report["kind"] == "movements" else 7
        for index, row in enumerate(page_rows):
            if index % 2 == 0:
                _pdf_rect(commands, margin, row_y - 8, page_width - 2 * margin, row_height, "#F7F9FB")
            x = margin
            for key, _label, width in columns:
                value = row.get(key, "")
                if key.endswith("_cents"):
                    value = format_money(value)
                max_chars = max(4, int((width - 6) / (body_font_size * 0.53)))
                text = _short(value, max_chars)
                _pdf_text(commands, x + 3, row_y + 1, text, body_font_size, "#34465A")
                x += width
            _pdf_line(commands, margin, row_y - 8, page_width - margin, row_y - 8, "#E8EDF2", 0.35)
            row_y -= row_height
        if report["kind"] == "movements":
            note = "Nota: los campos largos pueden abreviarse en esta vista PDF; Excel, XML, TXT y CSV conservan el texto completo."
            _pdf_text(commands, margin, 39, note, 6.5, "#8190A2")
        footer_text = "Gestor Financiero · Reporte generado desde los filtros seleccionados"
        _pdf_text(commands, margin, 20, footer_text, 7, "#8190A2")
        _pdf_line(commands, margin, 33, page_width - margin, 33, "#E1E8EF", 0.5)
        stream = b"\n".join(commands) + b"\n"
        pages.append(stream)
    return pages


def _write_pdf(path: Path, report: dict[str, Any]):
    streams = _pdf_pages(report)
    objects: list[bytes | None] = [None] * (5 + len(streams) * 2)
    objects[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
    kids = " ".join(f"{6 + i * 2} 0 R" for i in range(len(streams)))
    objects[2] = f"<< /Type /Pages /Kids [{kids}] /Count {len(streams)} >>".encode("ascii")
    objects[3] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica /Encoding /WinAnsiEncoding >>"
    objects[4] = b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica-Bold /Encoding /WinAnsiEncoding >>"
    for index, stream in enumerate(streams):
        content_id = 5 + index * 2
        page_id = content_id + 1
        objects[content_id] = f"<< /Length {len(stream)} >>\nstream\n".encode("ascii") + stream + b"endstream"
        objects[page_id] = (
            b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 842 595] "
            b"/Resources << /Font << /F1 3 0 R /F2 4 0 R >> >> "
            + f"/Contents {content_id} 0 R >>".encode("ascii")
        )
    data = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
    offsets = [0]
    for index in range(1, len(objects)):
        offsets.append(len(data))
        data.extend(f"{index} 0 obj\n".encode("ascii"))
        data.extend(objects[index] or b"")
        data.extend(b"\nendobj\n")
    xref_offset = len(data)
    data.extend(f"xref\n0 {len(objects)}\n".encode("ascii"))
    data.extend(b"0000000000 65535 f \n")
    for offset in offsets[1:]:
        data.extend(f"{offset:010d} 00000 n \n".encode("ascii"))
    data.extend(
        f"trailer\n<< /Size {len(objects)} /Root 1 0 R >>\nstartxref\n{xref_offset}\n%%EOF\n".encode("ascii")
    )
    path.write_bytes(data)
