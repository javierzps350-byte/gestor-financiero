from calendar import monthrange
from datetime import date, timedelta


def add_months(anchor: date, months: int, billing_day: int | None = None) -> date:
    absolute_month = anchor.year * 12 + (anchor.month - 1) + months
    year, month_index = divmod(absolute_month, 12)
    month = month_index + 1
    day = min(billing_day or anchor.day, monthrange(year, month)[1])
    return date(year, month, day)


def next_cycle(cycle_start: date, billing_day: int) -> date:
    return add_months(cycle_start, 1, billing_day)


def cycle_end(cycle_start: date, billing_day: int) -> date:
    return next_cycle(cycle_start, billing_day) - timedelta(days=1)


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except (TypeError, ValueError) as exc:
        raise ValueError("La fecha debe tener formato AAAA-MM-DD.") from exc
