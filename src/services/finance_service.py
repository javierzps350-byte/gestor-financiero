from __future__ import annotations

from datetime import date
from typing import Any

from src.database.connection import get_connection
from src.domain.monthly_calculator import cycle_end, next_cycle, parse_iso_date


def _rate_for_cycle(connection, client_id: int, cycle_start: date):
    return connection.execute(
        """SELECT id, monthly_amount_cents FROM client_rates
           WHERE client_id = ? AND effective_from <= ?
           ORDER BY effective_from DESC, id DESC LIMIT 1""",
        (client_id, cycle_start.isoformat()),
    ).fetchone()


def create_client(
    name: str,
    monthly_amount_cents: int,
    first_billing_date: str,
    phone: str = "",
    email: str = "",
    identification: str = "",
    notes: str = "",
) -> int:
    name = name.strip()
    if not name:
        raise ValueError("El nombre del cliente es obligatorio.")
    if monthly_amount_cents <= 0:
        raise ValueError("La mensualidad debe ser mayor que cero.")
    start = parse_iso_date(first_billing_date)
    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO clients
               (name, identification, phone, email, notes, billing_day, first_billing_date)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (name, identification.strip(), phone.strip(), email.strip(), notes.strip(), start.day, start.isoformat()),
        )
        client_id = int(cursor.lastrowid)
        connection.execute(
            "INSERT INTO client_rates (client_id, monthly_amount_cents, effective_from) VALUES (?, ?, ?)",
            (client_id, monthly_amount_cents, start.isoformat()),
        )
        connection.execute(
            "INSERT INTO audit_log(entity_type, entity_id, action, details) VALUES ('client', ?, 'created', ?)",
            (client_id, f"Cliente creado: {name}"),
        )
        return client_id


def list_clients(active_only: bool = False) -> list[dict[str, Any]]:
    sql = """SELECT c.*,
        (SELECT r.monthly_amount_cents FROM client_rates r
         WHERE r.client_id=c.id ORDER BY r.effective_from DESC, r.id DESC LIMIT 1) AS current_rate_cents
        FROM clients c"""
    if active_only:
        sql += " WHERE c.is_active = 1"
    sql += " ORDER BY c.name COLLATE NOCASE"
    with get_connection() as connection:
        return [dict(row) for row in connection.execute(sql).fetchall()]


def set_client_active(client_id: int, active: bool) -> None:
    with get_connection() as connection:
        connection.execute("UPDATE clients SET is_active=? WHERE id=?", (1 if active else 0, client_id))
        connection.execute(
            "INSERT INTO audit_log(entity_type, entity_id, action, details) VALUES ('client', ?, 'status_changed', ?)",
            (client_id, "Activo" if active else "Inactivo"),
        )


def set_client_rate(client_id: int, monthly_amount_cents: int, effective_from: str) -> int:
    if monthly_amount_cents <= 0:
        raise ValueError("La tarifa debe ser mayor que cero.")
    effective_date = parse_iso_date(effective_from)
    with get_connection() as connection:
        client = connection.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
        if not client:
            raise ValueError("No se encontró el cliente.")
        existing = connection.execute(
            "SELECT id FROM client_rates WHERE client_id=? AND effective_from=?",
            (client_id, effective_date.isoformat()),
        ).fetchone()
        if existing:
            raise ValueError("Ya existe una tarifa con esa fecha de vigencia.")
        cursor = connection.execute(
            "INSERT INTO client_rates(client_id, monthly_amount_cents, effective_from) VALUES (?, ?, ?)",
            (client_id, monthly_amount_cents, effective_date.isoformat()),
        )
        rate_id = int(cursor.lastrowid)
        # Solo se actualizan cuotas futuras que todavía no tienen ningún abono.
        future_charges = connection.execute(
            """SELECT id, period_start FROM monthly_charges
               WHERE client_id=? AND period_start>=?
               AND id NOT IN (SELECT charge_id FROM payment_allocations)""",
            (client_id, effective_date.isoformat()),
        ).fetchall()
        for charge in future_charges:
            applicable_rate = _rate_for_cycle(
                connection, client_id, parse_iso_date(charge["period_start"])
            )
            if applicable_rate:
                connection.execute(
                    "UPDATE monthly_charges SET rate_id=?, amount_due_cents=? WHERE id=?",
                    (int(applicable_rate["id"]), int(applicable_rate["monthly_amount_cents"]), int(charge["id"])),
                )
        connection.execute(
            "INSERT INTO audit_log(entity_type, entity_id, action, details) VALUES ('client', ?, 'rate_changed', ?)",
            (client_id, f"Nueva tarifa desde {effective_date.isoformat()}: {monthly_amount_cents} centavos"),
        )
        return rate_id


def _insert_charge(connection, client_id: int, cycle_start: date, billing_day: int) -> int:
    rate = _rate_for_cycle(connection, client_id, cycle_start)
    if not rate:
        raise ValueError(
            f"No hay una tarifa configurada para el ciclo {cycle_start.isoformat()}."
        )
    end = cycle_end(cycle_start, billing_day)
    connection.execute(
        """INSERT OR IGNORE INTO monthly_charges
           (client_id, rate_id, period_start, period_end, due_date, amount_due_cents)
           VALUES (?, ?, ?, ?, ?, ?)""",
        (
            client_id,
            int(rate["id"]),
            cycle_start.isoformat(),
            end.isoformat(),
            cycle_start.isoformat(),
            int(rate["monthly_amount_cents"]),
        ),
    )
    # INSERT OR IGNORE puede conservar el lastrowid de otra inserción anterior.
    # Siempre consultamos por la clave natural para recuperar el ID correcto.
    row = connection.execute(
        "SELECT id FROM monthly_charges WHERE client_id=? AND period_start=?",
        (client_id, cycle_start.isoformat()),
    ).fetchone()
    if not row:
        raise RuntimeError("No se pudo crear ni recuperar la mensualidad.")
    return int(row["id"])


def _ensure_charges_until(connection, client_id: int, until: date) -> None:
    client = connection.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
    if not client:
        raise ValueError("No se encontró el cliente.")
    billing_day = int(client["billing_day"])
    first = parse_iso_date(client["first_billing_date"])
    latest = connection.execute(
        "SELECT period_start FROM monthly_charges WHERE client_id=? ORDER BY period_start DESC LIMIT 1",
        (client_id,),
    ).fetchone()
    current = next_cycle(parse_iso_date(latest["period_start"]), billing_day) if latest else first
    loops = 0
    while current <= until:
        _insert_charge(connection, client_id, current, billing_day)
        current = next_cycle(current, billing_day)
        loops += 1
        if loops > 1200:
            raise RuntimeError("Se alcanzó el límite de generación de mensualidades.")


def generate_charges(client_id: int, through_date: str | None = None) -> int:
    target = parse_iso_date(through_date) if through_date else date.today()
    with get_connection() as connection:
        before = connection.execute(
            "SELECT COUNT(*) AS n FROM monthly_charges WHERE client_id=?", (client_id,)
        ).fetchone()["n"]
        _ensure_charges_until(connection, client_id, target)
        after = connection.execute(
            "SELECT COUNT(*) AS n FROM monthly_charges WHERE client_id=?", (client_id,)
        ).fetchone()["n"]
        return int(after - before)


def _allocate_payment(connection, movement_id: int, client_id: int, amount_cents: int, payment_date: str) -> int:
    pay_date = parse_iso_date(payment_date)
    _ensure_charges_until(connection, client_id, pay_date)
    remaining = amount_cents
    allocated_total = 0
    iterations = 0
    while remaining > 0:
        charges = connection.execute(
            """SELECT ch.id, ch.amount_due_cents,
                      COALESCE((SELECT SUM(pa.amount_allocated_cents)
                                FROM payment_allocations pa
                                JOIN movements m ON m.id=pa.movement_id
                                WHERE pa.charge_id=ch.id AND m.status='active'), 0) AS applied
               FROM monthly_charges ch
               WHERE ch.client_id=?
               ORDER BY ch.period_start ASC""",
            (client_id,),
        ).fetchall()
        open_charge = next((row for row in charges if int(row["amount_due_cents"]) - int(row["applied"]) > 0), None)
        if open_charge is None:
            client = connection.execute("SELECT * FROM clients WHERE id=?", (client_id,)).fetchone()
            latest = connection.execute(
                "SELECT period_start FROM monthly_charges WHERE client_id=? ORDER BY period_start DESC LIMIT 1",
                (client_id,),
            ).fetchone()
            if latest:
                next_start = next_cycle(parse_iso_date(latest["period_start"]), int(client["billing_day"]))
            else:
                next_start = parse_iso_date(client["first_billing_date"])
            charge_id = _insert_charge(connection, client_id, next_start, int(client["billing_day"]))
            open_charge = connection.execute(
                "SELECT id, amount_due_cents, 0 AS applied FROM monthly_charges WHERE id=?", (charge_id,)
            ).fetchone()
        balance = int(open_charge["amount_due_cents"]) - int(open_charge["applied"])
        allocation = min(balance, remaining)
        connection.execute(
            """INSERT INTO payment_allocations(movement_id, charge_id, amount_allocated_cents)
               VALUES (?, ?, ?)""",
            (movement_id, int(open_charge["id"]), allocation),
        )
        remaining -= allocation
        allocated_total += allocation
        iterations += 1
        if iterations > 1200:
            raise RuntimeError("No fue posible distribuir el pago: demasiados períodos.")
    return allocated_total


def _rebuild_client_allocations(connection, client_id: int) -> None:
    """Rebuild monthly allocations in payment-date order.

    This keeps the oldest outstanding monthly charges covered first even when
    a payment is entered late or an older payment is voided afterwards.
    """
    connection.execute(
        """DELETE FROM payment_allocations
           WHERE movement_id IN (
               SELECT id FROM movements
               WHERE client_id=? AND direction='income' AND apply_to_monthly=1
           )""",
        (client_id,),
    )
    payments = connection.execute(
        """SELECT id, amount_cents, payment_date
           FROM movements
           WHERE client_id=? AND direction='income'
             AND apply_to_monthly=1 AND status='active'
           ORDER BY payment_date ASC, registered_at ASC, id ASC""",
        (client_id,),
    ).fetchall()
    for payment in payments:
        _allocate_payment(
            connection,
            int(payment["id"]),
            client_id,
            int(payment["amount_cents"]),
            payment["payment_date"],
        )


def create_movement(
    direction: str,
    counterparty: str,
    reason: str,
    amount_cents: int,
    payment_date: str,
    payment_method: str,
    client_id: int | None = None,
    voucher_number: str = "",
    notes: str = "",
    apply_to_monthly: bool = False,
    category: str = "Otros",
) -> int:
    if direction not in ("income", "expense"):
        raise ValueError("Tipo de movimiento no válido.")
    if not counterparty.strip():
        raise ValueError("Indica quién realiza o recibe el pago.")
    if not reason.strip():
        raise ValueError("El motivo del movimiento es obligatorio.")
    if amount_cents <= 0:
        raise ValueError("El importe debe ser mayor que cero.")
    parse_iso_date(payment_date)
    if not payment_method.strip():
        raise ValueError("Selecciona el tipo de pago.")
    if apply_to_monthly and (direction != "income" or client_id is None):
        raise ValueError("Para aplicar mensualidades debes seleccionar un cliente en un ingreso.")

    with get_connection() as connection:
        cursor = connection.execute(
            """INSERT INTO movements
               (direction, client_id, counterparty, reason, amount_cents, payment_date,
                payment_method, voucher_number, notes, category, apply_to_monthly)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                direction, client_id, counterparty.strip(), reason.strip(), amount_cents,
                payment_date, payment_method.strip(), voucher_number.strip(), notes.strip(),
                (category or ("Ingresos" if direction == "income" else "Otros")).strip(),
                1 if apply_to_monthly else 0,
            ),
        )
        movement_id = int(cursor.lastrowid)
        if apply_to_monthly:
            _rebuild_client_allocations(connection, int(client_id))
        connection.execute(
            "INSERT INTO audit_log(entity_type, entity_id, action, details) VALUES ('movement', ?, 'created', ?)",
            (movement_id, f"{direction}: {amount_cents} centavos; {reason.strip()}"),
        )
        return movement_id


def void_movement(movement_id: int, reason: str) -> None:
    if not reason.strip():
        raise ValueError("Debes indicar por qué se anula el movimiento.")
    with get_connection() as connection:
        movement = connection.execute(
            "SELECT status, client_id, direction, apply_to_monthly FROM movements WHERE id=?",
            (movement_id,),
        ).fetchone()
        if not movement:
            raise ValueError("No se encontró el movimiento.")
        if movement["status"] == "void":
            raise ValueError("Este movimiento ya está anulado.")
        connection.execute(
            "UPDATE movements SET status='void', void_reason=?, voided_at=datetime('now','localtime') WHERE id=?",
            (reason.strip(), movement_id),
        )
        if (
            movement["direction"] == "income"
            and movement["client_id"] is not None
            and int(movement["apply_to_monthly"] or 0) == 1
        ):
            _rebuild_client_allocations(connection, int(movement["client_id"]))
        connection.execute(
            "INSERT INTO audit_log(entity_type, entity_id, action, details) VALUES ('movement', ?, 'voided', ?)",
            (movement_id, reason.strip()),
        )


def _movement_select() -> str:
    return """SELECT m.*, c.name AS client_name,
        (SELECT COUNT(*) FROM evidence_files e WHERE e.movement_id=m.id) AS evidence_count
        FROM movements m LEFT JOIN clients c ON c.id=m.client_id"""


def search_movements(
    query: str = "",
    direction: str = "all",
    date_from: str = "",
    date_to: str = "",
    voucher: str = "",
    client_id: int | None = None,
    category: str = "",
    include_void: bool = False,
    limit: int = 100000,
) -> list[dict[str, Any]]:
    clauses = []
    params: list[Any] = []
    if not include_void:
        clauses.append("m.status='active'")
    if direction in ("income", "expense"):
        clauses.append("m.direction=?")
        params.append(direction)
    if query.strip():
        needle = f"%{query.strip()}%"
        clauses.append("(m.counterparty LIKE ? OR m.reason LIKE ? OR m.notes LIKE ? OR c.name LIKE ? OR m.voucher_number LIKE ? OR m.category LIKE ?)")
        params.extend([needle] * 6)
    if voucher.strip():
        clauses.append("m.voucher_number LIKE ?")
        params.append(f"%{voucher.strip()}%")
    if client_id is not None:
        clauses.append("m.client_id=?")
        params.append(int(client_id))
    if category.strip():
        clauses.append("m.category=?")
        params.append(category.strip())
    if date_from.strip():
        parse_iso_date(date_from)
        clauses.append("m.payment_date>=?")
        params.append(date_from)
    if date_to.strip():
        parse_iso_date(date_to)
        clauses.append("m.payment_date<=?")
        params.append(date_to)
    sql = _movement_select()
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY m.payment_date DESC, m.id DESC LIMIT ?"
    params.append(max(1, min(int(limit), 250000)))
    with get_connection() as connection:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]


def list_evidence(movement_id: int) -> list[dict[str, Any]]:
    with get_connection() as connection:
        return [dict(row) for row in connection.execute(
            "SELECT * FROM evidence_files WHERE movement_id=? ORDER BY id", (movement_id,)
        ).fetchall()]


def list_client_charges(client_id: int, through_date: str | None = None) -> list[dict[str, Any]]:
    """Return charges and the balance as it stood on the requested date.

    Future periods are shown only when a payment made on/before the reference
    date has already created or funded them. Payments dated after the reference
    date never reduce a historical balance.
    """
    target = parse_iso_date(through_date) if through_date else date.today()
    target_text = target.isoformat()
    with get_connection() as connection:
        _ensure_charges_until(connection, client_id, target)
        rows = connection.execute(
            """SELECT ch.*,
               COALESCE((SELECT SUM(pa.amount_allocated_cents)
                         FROM payment_allocations pa
                         JOIN movements m ON m.id=pa.movement_id
                         WHERE pa.charge_id=ch.id
                           AND m.status='active'
                           AND m.payment_date<=?),0) AS applied_cents
               FROM monthly_charges ch
               WHERE ch.client_id=?
                 AND (
                     ch.period_start<=?
                     OR EXISTS (
                         SELECT 1
                         FROM payment_allocations pa2
                         JOIN movements m2 ON m2.id=pa2.movement_id
                         WHERE pa2.charge_id=ch.id
                           AND m2.status='active'
                           AND m2.payment_date<=?
                     )
                 )
               ORDER BY ch.period_start""",
            (target_text, client_id, target_text, target_text),
        ).fetchall()
        result = []
        for row in rows:
            item = dict(row)
            item["remaining_cents"] = max(0, int(item["amount_due_cents"]) - int(item["applied_cents"]))
            result.append(item)
        return result


def client_payment_history(client_id: int, as_of: str | None = None) -> list[dict[str, Any]]:
    """List client income movements with original and monthly-applied amounts."""
    params: list[Any] = [client_id]
    date_clause = ""
    if as_of:
        reference = parse_iso_date(as_of).isoformat()
        date_clause = " AND m.payment_date<=?"
        params.append(reference)
    with get_connection() as connection:
        rows = connection.execute(
            """SELECT m.*,
               COALESCE((SELECT SUM(pa.amount_allocated_cents)
                         FROM payment_allocations pa
                         WHERE pa.movement_id=m.id),0) AS allocated_cents,
               (SELECT COUNT(*) FROM evidence_files e WHERE e.movement_id=m.id) AS evidence_count
               FROM movements m
               WHERE m.client_id=? AND m.direction='income'""" + date_clause +
            " ORDER BY m.payment_date DESC, m.id DESC",
            params,
        ).fetchall()
        return [dict(row) for row in rows]


def find_voucher_matches(voucher_number: str, exclude_movement_id: int | None = None) -> list[dict[str, Any]]:
    """Find existing movements with the same voucher, case-insensitively."""
    voucher = voucher_number.strip()
    if not voucher:
        return []
    sql = _movement_select() + " WHERE lower(trim(m.voucher_number))=lower(trim(?))"
    params: list[Any] = [voucher]
    if exclude_movement_id is not None:
        sql += " AND m.id<>?"
        params.append(exclude_movement_id)
    sql += " ORDER BY m.payment_date DESC, m.id DESC LIMIT 20"
    with get_connection() as connection:
        return [dict(row) for row in connection.execute(sql, params).fetchall()]


def client_debt_summary(client_id: int, as_of: str | None = None) -> dict[str, int]:
    reference = parse_iso_date(as_of) if as_of else date.today()
    charges = list_client_charges(client_id, reference.isoformat())
    total_billed = sum(int(c["amount_due_cents"]) for c in charges)
    total_applied = sum(int(c["applied_cents"]) for c in charges)
    overdue = sum(
        int(c["remaining_cents"]) for c in charges
        if c["due_date"] <= reference.isoformat()
    )
    pending_total = sum(int(c["remaining_cents"]) for c in charges)
    fully_paid = sum(1 for c in charges if int(c["remaining_cents"]) == 0)
    partial = sum(1 for c in charges if 0 < int(c["applied_cents"]) < int(c["amount_due_cents"]))
    future_applied = sum(
        int(c["applied_cents"]) for c in charges
        if c["due_date"] > reference.isoformat()
    )
    with get_connection() as connection:
        received = int(connection.execute(
            """SELECT COALESCE(SUM(amount_cents),0)
               FROM movements
               WHERE client_id=? AND direction='income'
                 AND status='active' AND payment_date<=?""",
            (client_id, reference.isoformat()),
        ).fetchone()[0])
    return {
        "total_billed_cents": total_billed,
        "total_applied_cents": total_applied,
        "total_received_cents": received,
        "overdue_cents": overdue,
        "pending_cents": pending_total,
        "fully_paid_months": fully_paid,
        "partial_months": partial,
        "future_applied_cents": future_applied,
    }


def dashboard_summary() -> dict[str, int]:
    today = date.today()
    month_start = today.replace(day=1).isoformat()
    with get_connection() as connection:
        income = int(connection.execute(
            "SELECT COALESCE(SUM(amount_cents),0) FROM movements WHERE direction='income' AND status='active' AND payment_date>=? AND payment_date<=?",
            (month_start, today.isoformat()),
        ).fetchone()[0])
        expenses = int(connection.execute(
            "SELECT COALESCE(SUM(amount_cents),0) FROM movements WHERE direction='expense' AND status='active' AND payment_date>=? AND payment_date<=?",
            (month_start, today.isoformat()),
        ).fetchone()[0])
        clients = int(connection.execute("SELECT COUNT(*) FROM clients WHERE is_active=1").fetchone()[0])
    # Genera las cuotas del período actual antes de calcular las cuentas vencidas.
    overdue_total = 0
    due_clients_set = set()
    for client in list_clients(active_only=True):
        summary = client_debt_summary(int(client["id"]), today.isoformat())
        overdue_total += summary["overdue_cents"]
        if summary["overdue_cents"] > 0:
            due_clients_set.add(int(client["id"]))
    due_clients = len(due_clients_set)
    return {
        "income_month_cents": income,
        "expenses_month_cents": expenses,
        "net_month_cents": income - expenses,
        "active_clients": clients,
        "clients_with_due_charges": due_clients,
        "overdue_total_cents": overdue_total,
    }


def dashboard_visual_data(
    chart_month: str | None = None,
    table_month: str | None = None,
    category: str | None = None,
    month_count: int = 12,
) -> dict[str, Any]:
    """Return dashboard chart and recent-activity data from real movements.

    ``chart_month`` controls the expense-category donut. ``table_month`` and
    ``category`` optionally filter the recent-movements table after a chart
    selection. Monetary values remain integer cents.
    """
    from calendar import monthrange
    from datetime import date

    today = date.today()
    current_month = today.strftime("%Y-%m")
    chart_month = chart_month or current_month
    if len(chart_month) != 7 or chart_month[4] != "-":
        raise ValueError("El mes debe tener formato AAAA-MM.")
    try:
        chart_year, chart_month_number = (int(part) for part in chart_month.split("-"))
        chart_start = date(chart_year, chart_month_number, 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("El mes seleccionado no es válido.") from exc
    chart_end = date(chart_year, chart_month_number, monthrange(chart_year, chart_month_number)[1])
    if chart_month == current_month:
        chart_end = min(chart_end, today)

    month_count = max(1, min(int(month_count), 36))
    absolute = today.year * 12 + today.month - 1
    first_absolute = absolute - month_count + 1
    first_year, first_month_index = divmod(first_absolute, 12)
    first_month = date(first_year, first_month_index + 1, 1)

    month_rows = []
    month_labels = ("Ene", "Feb", "Mar", "Abr", "May", "Jun", "Jul", "Ago", "Sep", "Oct", "Nov", "Dic")
    for offset in range(month_count):
        serial = first_absolute + offset
        year, month_index = divmod(serial, 12)
        month = month_index + 1
        month_rows.append({
            "month": f"{year:04d}-{month:02d}",
            "label": month_labels[month_index],
            "label_full": f"{month_labels[month_index]} {year}",
            "income_cents": 0,
            "expenses_cents": 0,
        })

    first_text = first_month.isoformat()
    today_text = today.isoformat()
    with get_connection() as connection:
        totals = connection.execute(
            """SELECT
                COALESCE(SUM(CASE WHEN direction='income' THEN amount_cents ELSE 0 END),0) AS income,
                COALESCE(SUM(CASE WHEN direction='expense' THEN amount_cents ELSE 0 END),0) AS expenses,
                (SELECT COUNT(*) FROM clients WHERE is_active=1) AS active_clients
               FROM movements WHERE status='active'"""
        ).fetchone()
        current = connection.execute(
            """SELECT
                COALESCE(SUM(CASE WHEN direction='income' THEN amount_cents ELSE 0 END),0) AS income,
                COALESCE(SUM(CASE WHEN direction='expense' THEN amount_cents ELSE 0 END),0) AS expenses
               FROM movements
               WHERE status='active' AND payment_date>=? AND payment_date<=?""",
            (today.replace(day=1).isoformat(), today_text),
        ).fetchone()
        series_rows = connection.execute(
            """SELECT substr(payment_date,1,7) AS month, direction,
                      SUM(amount_cents) AS amount
               FROM movements
               WHERE status='active' AND payment_date>=? AND payment_date<=?
               GROUP BY substr(payment_date,1,7), direction""",
            (first_text, today_text),
        ).fetchall()
        series_map = {row["month"]: row for row in month_rows}
        for row in series_rows:
            target = series_map.get(row["month"])
            if target is None:
                continue
            key = "income_cents" if row["direction"] == "income" else "expenses_cents"
            target[key] = int(row["amount"] or 0)

        category_rows = connection.execute(
            """SELECT COALESCE(NULLIF(trim(category),''),'Otros') AS category,
                      SUM(amount_cents) AS amount
               FROM movements
               WHERE status='active' AND direction='expense'
                 AND payment_date>=? AND payment_date<=?
               GROUP BY COALESCE(NULLIF(trim(category),''),'Otros')
               ORDER BY amount DESC, category COLLATE NOCASE""",
            (chart_start.isoformat(), chart_end.isoformat()),
        ).fetchall()

        clauses = ["status='active'"]
        params: list[Any] = []
        if table_month:
            try:
                year, month = (int(part) for part in table_month.split("-"))
                start = date(year, month, 1)
                end = date(year, month, monthrange(year, month)[1])
            except (TypeError, ValueError) as exc:
                raise ValueError("El filtro mensual no es válido.") from exc
            clauses.extend(["payment_date>=?", "payment_date<=?"])
            params.extend([start.isoformat(), end.isoformat()])
        if category:
            clauses.append("COALESCE(NULLIF(trim(category),''),'Otros')=?")
            params.append(category)
        recent_rows = connection.execute(
            """SELECT id, payment_date, counterparty, reason, category,
                      direction, amount_cents, payment_method, voucher_number
               FROM movements WHERE """ + " AND ".join(clauses) +
            " ORDER BY payment_date DESC, id DESC LIMIT 10",
            params,
        ).fetchall()

    active_clients = int(totals["active_clients"] or 0)
    return {
        "balance_cents": int(totals["income"] or 0) - int(totals["expenses"] or 0),
        "income_month_cents": int(current["income"] or 0),
        "expenses_month_cents": int(current["expenses"] or 0),
        "active_clients": active_clients,
        "series": month_rows,
        "categories": [
            {"category": str(row["category"]), "amount_cents": int(row["amount"] or 0)}
            for row in category_rows
        ],
        "recent": [dict(row) for row in recent_rows],
        "chart_month": chart_month,
        "table_month": table_month,
        "selected_category": category,
    }
