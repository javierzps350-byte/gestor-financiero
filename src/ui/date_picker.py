"""Compact Spanish calendar picker for ISO date fields."""
from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date
from tkinter import ttk

from src.ui.premium import palette_for

MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
WEEKDAYS = ("L", "M", "X", "J", "V", "S", "D")


def month_weeks(year: int, month: int):
    """Return a Monday-first calendar matrix for the requested month."""
    if not 1 <= month <= 12:
        raise ValueError("El mes debe estar entre 1 y 12.")
    return calendar.monthcalendar(year, month)


class DatePickerEntry(ttk.Frame):
    """Entry plus a small popup calendar. The bound value remains YYYY-MM-DD."""

    def __init__(self, parent, textvariable=None, width=16, **kwargs):
        super().__init__(parent, **kwargs)
        self.variable = textvariable or tk.StringVar()
        p = palette_for(parent)
        self.entry = ttk.Entry(self, textvariable=self.variable, width=width)
        self.entry.pack(side="left", fill="x", expand=True)
        self.button = tk.Button(
            self, text="▦", command=self.open_calendar,
            font=("Segoe UI Symbol", 11), width=3, relief="flat", bd=0,
            bg=p["panel_alt"], fg=p["text"], activebackground=p["selected"], activeforeground=p["text"],
            cursor="hand2", padx=3, pady=4,
        )
        self.button.pack(side="left", padx=(5, 0))
        self.button.bind("<Enter>", self._hover)
        self.button.bind("<Leave>", self._unhover)
        self._popup = None

    def _hover(self, _event=None):
        p = palette_for(self)
        self.button.configure(bg=p["selected"], fg=p["text"])

    def _unhover(self, _event=None):
        p = palette_for(self)
        self.button.configure(bg=p["panel_alt"], fg=p["text"])

    def _current_date(self):
        try:
            return date.fromisoformat(self.variable.get().strip())
        except (ValueError, TypeError):
            return date.today()

    def open_calendar(self):
        if self._popup and self._popup.winfo_exists():
            self._popup.destroy()
            self._popup = None
            return
        p = palette_for(self)
        current = self._current_date()
        year, month = current.year, current.month
        popup = tk.Toplevel(self)
        self._popup = popup
        popup.overrideredirect(True)
        popup.configure(bg=p["border"])
        popup.transient(self.winfo_toplevel())
        outer = tk.Frame(popup, bg=p["border"], padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        card = tk.Frame(outer, bg=p["panel"], padx=13, pady=12)
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg=p["panel"])
        header.pack(fill="x", pady=(0, 10))
        grid = tk.Frame(card, bg=p["panel"])
        grid.pack(fill="both", expand=True)

        controls = tk.Frame(card, bg=p["panel"])
        controls.pack(fill="x", pady=(10, 0))

        def close():
            if popup.winfo_exists():
                popup.destroy()
            self._popup = None

        def choose(day_value):
            if day_value:
                self.variable.set(date(year_var[0], month_var[0], day_value).isoformat())
            close()

        year_var = [year]
        month_var = [month]

        def change(delta):
            month_var[0] += delta
            if month_var[0] < 1:
                month_var[0] = 12
                year_var[0] -= 1
            elif month_var[0] > 12:
                month_var[0] = 1
                year_var[0] += 1
            draw()

        def draw():
            for child in header.winfo_children():
                child.destroy()
            for child in grid.winfo_children():
                child.destroy()
            tk.Button(header, text="‹", command=lambda: change(-1), bg=p["panel_alt"], fg=p["text"], activebackground=p["selected"], activeforeground=p["text"], relief="flat", bd=0, font=("Segoe UI", 14), width=3, cursor="hand2").pack(side="left")
            tk.Label(header, text=f"{MONTHS[month_var[0]-1].capitalize()} {year_var[0]}", bg=p["panel"], fg=p["text"], font=("Segoe UI", 11, "bold")).pack(side="left", expand=True, anchor="w", padx=10)
            tk.Button(header, text="›", command=lambda: change(1), bg=p["panel_alt"], fg=p["text"], activebackground=p["selected"], activeforeground=p["text"], relief="flat", bd=0, font=("Segoe UI", 14), width=3, cursor="hand2").pack(side="right")

            for col, weekday in enumerate(WEEKDAYS):
                tk.Label(grid, text=weekday, width=4, bg=p["panel"], fg=p["muted"], font=("Segoe UI", 8, "bold")).grid(row=0, column=col, pady=(0, 5))

            weeks = month_weeks(year_var[0], month_var[0])
            for row, week in enumerate(weeks, start=1):
                for col, day_value in enumerate(week):
                    if not day_value:
                        tk.Label(grid, text="", width=4, bg=p["panel"]).grid(row=row, column=col, padx=1, pady=1)
                        continue
                    is_today = (year_var[0], month_var[0], day_value) == (date.today().year, date.today().month, date.today().day)
                    chosen = (year_var[0], month_var[0], day_value) == (current.year, current.month, current.day)
                    bg = p["accent"] if is_today else p["selected"] if chosen else p["panel"]
                    fg = p["panel"] if is_today else p["text"]
                    btn = tk.Button(grid, text=str(day_value), width=3, command=lambda value=day_value: choose(value), bg=bg, fg=fg, activebackground=p["accent_hover"], activeforeground=p["panel"], relief="flat", bd=0, font=("Segoe UI", 9, "bold" if (is_today or chosen) else "normal"), cursor="hand2")
                    btn.grid(row=row, column=col, padx=1, pady=1, ipadx=2, ipady=5)
                    btn.bind("<Enter>", lambda _e, b=btn: b.configure(bg=p["selected"], fg=p["text"]) if b.cget("bg") != p["accent"] else None)
                    btn.bind("<Leave>", lambda _e, b=btn, color=bg, text_color=fg: b.configure(bg=color, fg=text_color))

        def choose_today():
            self.variable.set(date.today().isoformat())
            close()

        tk.Button(controls, text="Hoy", command=choose_today, bg=p["panel_alt"], fg=p["text"], activebackground=p["selected"], activeforeground=p["text"], relief="flat", bd=0, font=("Segoe UI", 9, "bold"), padx=12, pady=6, cursor="hand2").pack(side="right")
        draw()
        popup.update_idletasks()
        popup_width = popup.winfo_reqwidth()
        popup_height = popup.winfo_reqheight()
        screen_width = popup.winfo_screenwidth()
        screen_height = popup.winfo_screenheight()
        x = self.button.winfo_rootx()
        below_y = self.button.winfo_rooty() + self.button.winfo_height() + 4
        y = below_y if below_y + popup_height <= screen_height else self.button.winfo_rooty() - popup_height - 4
        x = max(4, min(x, screen_width - popup_width - 4))
        y = max(4, min(y, screen_height - popup_height - 4))
        popup.geometry(f"{popup_width}x{popup_height}+{x}+{y}")
        popup.bind("<Escape>", lambda _e: close())
        popup.bind("<FocusOut>", lambda _e: self.after(120, lambda: close() if popup.winfo_exists() and not popup.focus_displayof() else None))
        popup.focus_force()
