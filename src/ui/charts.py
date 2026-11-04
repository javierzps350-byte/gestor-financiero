from __future__ import annotations

import math
import tkinter as tk
from typing import Callable

from src.domain.money import format_money

TEAL = "#2BAE9B"
CORAL = "#E9897D"
BLUE = "#77A9D9"
PURPLE = "#A995D5"
AMBER = "#E8B765"
GREEN = "#64B99C"
PALETTE = [TEAL, CORAL, BLUE, PURPLE, AMBER, GREEN, "#D68CA8", "#83B7C8"]
TEXT = "#243449"
MUTED = "#8290A1"
GRID = "#E9EEF4"
WHITE = "#FFFFFF"


def _short_money(cents: int) -> str:
    value = abs(int(cents)) / 100
    if value >= 1_000_000:
        return f"${value / 1_000_000:.1f} M"
    if value >= 100_000:
        return f"${value / 1_000:.0f} k"
    if value >= 10_000:
        return f"${value / 1_000:.1f} k"
    return f"${value:,.0f}".replace(",", ".")


class MonthlyLineChart(tk.Canvas):
    """Lightweight interactive line chart rendered with Tk Canvas only."""

    def __init__(self, master, on_month_selected: Callable[[str], None], **kwargs):
        super().__init__(
            master, background=WHITE, highlightthickness=0, bd=0,
            **kwargs,
        )
        self.on_month_selected = on_month_selected
        self.theme = {"panel": WHITE, "text": TEXT, "muted": MUTED, "grid": GRID, "border": "#DAE3EC", "shadow": "#D8E1EA", "accent": TEAL, "expense": CORAL, "selected": "#D9F0EC"}
        self.series: list[dict] = []
        self.selected_month: str | None = None
        self.visible = {"income": True, "expenses": True}
        self._points: dict[str, list[tuple[float, float, str, int]]] = {}
        self._legend_hits: list[tuple[tuple[float, float, float, float], str]] = []
        self._hover: tuple[str, str, int, float, float] | None = None
        self.bind("<Configure>", lambda _event: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def set_theme(self, palette: dict):
        self.theme = {"panel": palette["panel"], "text": palette["text"], "muted": palette["muted"], "grid": palette["grid"], "border": palette["border"], "shadow": palette["shadow"], "accent": palette["accent"], "expense": palette["expense"], "selected": palette["selected"]}
        self.configure(background=palette["panel"])
        self.redraw()

    def set_data(self, series: list[dict], selected_month: str | None = None):
        self.series = list(series)
        self.selected_month = selected_month
        self.redraw()

    def redraw(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        p = self.theme
        width = max(self.winfo_width(), 360)
        height = max(self.winfo_height(), 140)
        left, right, top, bottom = 52, width - 20, 34, height - 32
        self._points = {"income": [], "expenses": []}
        self._legend_hits = []

        legend_y = 14
        legend_specs = [
            ("income", "Ingresos", p["accent"]),
            ("expenses", "Gastos", p["expense"]),
        ]
        lx = max(left, width - 240)
        for key, label, color in legend_specs:
            dot_color = color if self.visible[key] else p["border"]
            self.create_oval(lx, legend_y - 4, lx + 8, legend_y + 4, fill=dot_color, outline="")
            text_color = p["text"] if self.visible[key] else p["muted"]
            item = self.create_text(lx + 14, legend_y, text=label, anchor="w", fill=text_color, font=("Segoe UI", 8))
            bbox = self.bbox(item) or (lx, legend_y - 8, lx + 68, legend_y + 8)
            self._legend_hits.append(((lx - 3, legend_y - 10, bbox[2] + 4, legend_y + 10), key))
            lx = bbox[2] + 24

        if not self.series:
            self.create_text(width / 2, height / 2, text="Todavía no hay movimientos para graficar", fill=p["muted"], font=("Segoe UI", 10))
            return

        raw_values = (
            [int(item.get("income_cents", 0)) for item in self.series]
            + [int(item.get("expenses_cents", 0)) for item in self.series]
        )
        has_data = any(value > 0 for value in raw_values)
        max_value = max(raw_values + [100])
        max_value = max(100, int(math.ceil(max_value / 1000.0) * 1000))
        graph_h = bottom - top
        graph_w = max(1, right - left)

        for tick in range(5):
            fraction = tick / 4
            y = bottom - graph_h * fraction
            value = int(max_value * fraction)
            self.create_line(left, y, right, y, fill=p["grid"], width=1)
            self.create_text(left - 9, y, text=_short_money(value), anchor="e", fill=p["muted"], font=("Segoe UI", 7))

        count = len(self.series)
        if not has_data:
            for index, item in enumerate(self.series):
                if count <= 7 or index % 2 == 0 or index == count - 1:
                    x = left + (graph_w * index / max(1, count - 1))
                    self.create_text(x, bottom + 17, text=item.get("label", ""), fill=p["muted"], font=("Segoe UI", 7))
            self.create_text(
                (left + right) / 2, (top + bottom) / 2,
                text="Registra movimientos para ver la evolución",
                fill=p["muted"], font=("Segoe UI", 9),
            )
            return
        x_positions = [left + (graph_w * i / max(1, count - 1)) for i in range(count)]
        for key, color, field in (("income", p["accent"], "income_cents"), ("expenses", p["expense"], "expenses_cents")):
            if not self.visible[key]:
                continue
            coords = []
            for index, (item, x) in enumerate(zip(self.series, x_positions)):
                amount = int(item.get(field, 0))
                y = bottom - (amount / max_value) * graph_h
                coords.extend((x, y))
                self._points[key].append((x, y, str(item["month"]), amount))
            if len(coords) >= 4:
                self.create_line(*coords, fill=color, width=2.6, smooth=True, splinesteps=20, capstyle=tk.ROUND, joinstyle=tk.ROUND)
            for x, y, month, amount in self._points[key]:
                radius = 3.5
                if month == self.selected_month:
                    self.create_oval(x - 8, y - 8, x + 8, y + 8, fill=p["panel"], outline=color, width=2)
                self.create_oval(x - radius, y - radius, x + radius, y + radius, fill=color, outline=p["panel"], width=1)

        for index, (item, x) in enumerate(zip(self.series, x_positions)):
            label = item.get("label", "")
            if count <= 7 or index % 2 == 0 or index == count - 1:
                self.create_text(x, bottom + 17, text=label, fill=p["muted"], font=("Segoe UI", 7))

        if self._hover:
            self._draw_tooltip(*self._hover)

    def _nearest_point(self, x: float, y: float):
        nearest = None
        distance = 1e9
        for key, points in self._points.items():
            if not self.visible[key]:
                continue
            for px, py, month, amount in points:
                current = math.hypot(px - x, py - y)
                if current < distance:
                    distance = current
                    nearest = (key, month, amount, px, py)
        return nearest if distance <= 18 else None

    def _draw_tooltip(self, key, month, amount, x, y):
        p = self.theme
        month_data = next((item for item in self.series if item["month"] == month), {})
        title = month_data.get("label_full", month)
        income = int(month_data.get("income_cents", 0))
        expenses = int(month_data.get("expenses_cents", 0))
        lines = [title, f"Ingresos: {format_money(income)}", f"Gastos: {format_money(expenses)}"]
        box_w, box_h = 166, 58
        x0 = min(max(8, x + 12), max(8, self.winfo_width() - box_w - 8))
        y0 = max(7, y - box_h - 8)
        self.create_rectangle(x0 + 1, y0 + 2, x0 + box_w + 1, y0 + box_h + 2, fill=p["shadow"], outline="")
        self.create_rectangle(x0, y0, x0 + box_w, y0 + box_h, fill=p["panel"], outline=p["border"])
        self.create_text(x0 + 9, y0 + 10, text=lines[0], anchor="w", fill=p["text"], font=("Segoe UI", 8, "bold"))
        self.create_text(x0 + 9, y0 + 28, text=lines[1], anchor="w", fill=p["accent"], font=("Segoe UI", 8))
        self.create_text(x0 + 9, y0 + 44, text=lines[2], anchor="w", fill=p["expense"], font=("Segoe UI", 8))

    def _on_motion(self, event):
        for (x1, y1, x2, y2), _key in self._legend_hits:
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.configure(cursor="hand2")
                if self._hover is not None:
                    self._hover = None
                    self.redraw()
                return
        point = self._nearest_point(event.x, event.y)
        self.configure(cursor="hand2" if point else "")
        if point != self._hover:
            self._hover = point
            self.redraw()

    def _on_leave(self, _event):
        if self._hover is not None:
            self._hover = None
            self.redraw()
        self.configure(cursor="")

    def _on_click(self, event):
        for (x1, y1, x2, y2), key in self._legend_hits:
            if x1 <= event.x <= x2 and y1 <= event.y <= y2:
                self.visible[key] = not self.visible[key]
                self._hover = None
                self.redraw()
                return
        point = self._nearest_point(event.x, event.y)
        if point:
            _key, month, _amount, _x, _y = point
            self.selected_month = month
            self.redraw()
            self.on_month_selected(month)


class ExpenseDonutChart(tk.Canvas):
    """Interactive expense distribution chart with clickable slices and legend."""

    def __init__(self, master, on_category_selected: Callable[[str], None], **kwargs):
        super().__init__(master, background=WHITE, highlightthickness=0, bd=0, **kwargs)
        self.on_category_selected = on_category_selected
        self.theme = {"panel": WHITE, "text": TEXT, "muted": MUTED, "border": "#DAE3EC", "accent": TEAL, "expense": CORAL, "selected": "#D9F0EC"}
        self.data: list[dict] = []
        self.selected: str | None = None
        self._segments: list[tuple[float, float, str, int, str]] = []
        self._legend_hits: list[tuple[tuple[float, float, float, float], str]] = []
        self._hover: str | None = None
        self.bind("<Configure>", lambda _event: self.redraw())
        self.bind("<Motion>", self._on_motion)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_click)

    def set_theme(self, palette: dict):
        self.theme = {"panel": palette["panel"], "text": palette["text"], "muted": palette["muted"], "border": palette["border"], "accent": palette["accent"], "expense": palette["expense"], "selected": palette["selected"]}
        self.configure(background=palette["panel"])
        self.redraw()

    def set_data(self, data: list[dict], selected: str | None = None):
        self.data = list(data)
        self.selected = selected
        self.redraw()

    def redraw(self):
        if not self.winfo_exists():
            return
        self.delete("all")
        p = self.theme
        self._segments = []
        self._legend_hits = []
        width = max(self.winfo_width(), 340)
        height = max(self.winfo_height(), 140)
        cx, cy = min(108, width * 0.29), height * 0.49
        radius, inner = min(65, height * 0.34), min(41, height * 0.215)
        total = sum(max(0, int(item.get("amount_cents", 0))) for item in self.data)

        if total <= 0:
            self.create_oval(cx - radius, cy - radius, cx + radius, cy + radius, fill=p["selected"], outline="")
            self.create_oval(cx - inner, cy - inner, cx + inner, cy + inner, fill=p["panel"], outline="")
            self.create_text(cx, cy - 5, text="Sin gastos", fill=p["text"], font=("Segoe UI", 9, "bold"))
            self.create_text(cx, cy + 12, text="en este período", fill=p["muted"], font=("Segoe UI", 7))
            self.create_text(width * 0.70, height / 2, text="No hay gastos categorizados", fill=p["muted"], font=("Segoe UI", 9))
            return

        start = 90.0
        for index, item in enumerate(self.data):
            amount = max(0, int(item.get("amount_cents", 0)))
            if amount <= 0:
                continue
            extent = amount / total * 360.0
            category = str(item.get("category") or "Otros")
            color = PALETTE[index % len(PALETTE)]
            if extent >= 359.99:
                self.create_oval(
                    cx - radius, cy - radius, cx + radius, cy + radius,
                    fill=color, outline=p["panel"], width=2,
                )
            else:
                self.create_arc(
                    cx - radius, cy - radius, cx + radius, cy + radius,
                    start=start, extent=extent, style=tk.PIESLICE,
                    fill=color, outline=p["panel"], width=2,
                )
            self._segments.append((start, extent, category, amount, color))
            start += extent

        self.create_oval(cx - inner, cy - inner, cx + inner, cy + inner, fill=p["panel"], outline="")
        self.create_text(cx, cy - 9, text="TOTAL", fill=p["muted"], font=("Segoe UI", 7, "bold"))
        self.create_text(cx, cy + 10, text=_short_money(total), fill=p["text"], font=("Segoe UI", 12, "bold"))

        legend_x = min(width - 155, max(205, cx + radius + 24))
        legend_count = min(len(self.data), 8)
        row_gap = 16 if height < 175 else 20
        legend_y = max(19, cy - (legend_count - 1) * row_gap / 2)
        for index, item in enumerate(self.data[:8]):
            category = str(item.get("category") or "Otros")
            amount = int(item.get("amount_cents", 0))
            color = PALETTE[index % len(PALETTE)]
            y = legend_y + index * row_gap
            selected = self.selected == category
            self.create_oval(legend_x, y - 4, legend_x + 8, y + 4, fill=color, outline="")
            name_color = p["text"] if not selected else p["accent"]
            name = category if len(category) <= 17 else category[:16] + "…"
            self.create_text(legend_x + 15, y, text=name, anchor="w", fill=name_color, font=("Segoe UI", 8, "bold" if selected else "normal"))
            amount_text = _short_money(amount)
            self.create_text(width - 8, y, text=amount_text, anchor="e", fill=p["muted"], font=("Segoe UI", 8))
            self._legend_hits.append(((legend_x - 4, y - 11, width - 4, y + 11), category))

        if self._hover:
            segment = next((s for s in self._segments if s[2] == self._hover), None)
            if segment:
                category, amount = segment[2], segment[3]
                pct = amount / total * 100
                tooltip_y = cy + radius + 5
                if tooltip_y + 34 > height - 2:
                    tooltip_y = max(2, cy - radius - 38)
                self.create_rectangle(cx - 64, tooltip_y, cx + 64, tooltip_y + 34, fill=p["panel"], outline=p["border"])
                self.create_text(cx, tooltip_y + 17, text=f"{category}: {pct:.1f}%", fill=p["text"], font=("Segoe UI", 8, "bold"))

    def _category_at(self, x: float, y: float):
        width = max(self.winfo_width(), 340)
        height = max(self.winfo_height(), 140)
        cx, cy = min(108, width * 0.29), height * 0.49
        radius, inner = min(65, height * 0.34), min(41, height * 0.215)
        dx, dy = x - cx, cy - y
        distance = math.hypot(dx, dy)
        if inner <= distance <= radius:
            angle = math.degrees(math.atan2(dy, dx)) % 360
            relative = (angle - 90) % 360
            for start, extent, category, _amount, _color in self._segments:
                offset = (relative - (start - 90)) % 360
                if offset <= extent:
                    return category
        for (x1, y1, x2, y2), category in self._legend_hits:
            if x1 <= x <= x2 and y1 <= y <= y2:
                return category
        return None

    def _on_motion(self, event):
        category = self._category_at(event.x, event.y)
        self.configure(cursor="hand2" if category else "")
        if category != self._hover:
            self._hover = category
            self.redraw()

    def _on_leave(self, _event):
        if self._hover is not None:
            self._hover = None
            self.redraw()
        self.configure(cursor="")

    def _on_click(self, event):
        category = self._category_at(event.x, event.y)
        if category:
            self.selected = category
            self.redraw()
            self.on_category_selected(category)
