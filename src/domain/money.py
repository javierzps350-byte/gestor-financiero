from decimal import Decimal, InvalidOperation, ROUND_HALF_UP


def to_cents(value: str | int | float | Decimal) -> int:
    try:
        amount = Decimal(str(value).replace("$", "").replace(",", ".").strip())
    except (InvalidOperation, ValueError) as exc:
        raise ValueError("Escribe un importe válido.") from exc
    if not amount.is_finite() or amount <= 0:
        raise ValueError("El importe debe ser mayor que cero.")
    return int((amount * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))


def format_money(cents: int | None) -> str:
    value = (cents or 0) / 100
    return f"${value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
