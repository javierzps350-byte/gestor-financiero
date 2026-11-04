"""Inline calendar picker for ISO date fields (YYYY-MM-DD).

The calendar is rendered as an overlay frame inside the current toplevel. It
never creates another native window and never changes Tk's grab stack. This is
intentional: date fields are used inside modal forms and nested premium dialogs
on Windows, where nested Toplevel grabs can hide the calendar or strand focus.
"""
from __future__ import annotations

import calendar
import tkinter as tk
from datetime import date
from tkinter import ttk
import weakref

from src.ui.premium import palette_for

MONTHS = (
    "enero", "febrero", "marzo", "abril", "mayo", "junio",
    "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre",
)
WEEKDAYS = ("L", "M", "X", "J", "V", "S", "D")

# One lightweight dispatcher per Tk root avoids leaving stale global bindings
# when many date fields are created and destroyed by page navigation.
_ACTIVE_PICKERS = weakref.WeakKeyDictionary()
_BOUND_ROOTS = weakref.WeakSet()


def _active_picker_set(root):
    pickers = _ACTIVE_PICKERS.get(root)
    if pickers is None:
        pickers = weakref.WeakSet()
        _ACTIVE_PICKERS[root] = pickers
    if root not in _BOUND_ROOTS:
        root.bind_all("<Button-1>", lambda event, target=root: _dispatch_global_click(target, event), add="+")
        root.bind_all("<Escape>", lambda event, target=root: _dispatch_global_escape(target, event), add="+")
        _BOUND_ROOTS.add(root)
    return pickers


def _dispatch_global_click(root, event):
    for picker in tuple(_ACTIVE_PICKERS.get(root, ())):
        picker._handle_global_click(event)
    return None


def _dispatch_global_escape(root, _event=None):
    active = tuple(_ACTIVE_PICKERS.get(root, ()))
    if not active:
        return None
    for picker in active:
        picker._close_calendar(restore_focus=True)
    return "break"


def month_weeks(year: int, month: int):
    """Return a Monday-first calendar matrix for the requested month."""
    if not 1 <= month <= 12:
        raise ValueError("El mes debe estar entre 1 y 12.")
    return calendar.monthcalendar(year, month)


class DatePickerEntry(ttk.Frame):
    """Date entry with an inline, keyboard-safe calendar overlay."""

    def __init__(self, parent, textvariable=None, width=16, **kwargs):
        super().__init__(parent, **kwargs)
        self.variable = textvariable if textvariable is not None else tk.StringVar(master=self)
        self._popup: tk.Frame | None = None
        self._day_buttons: list[tk.Button] = []
        self._focus_job = None
        self._root_widget = None
        self.entry = ttk.Entry(self, textvariable=self.variable, width=width)
        self.entry.pack(side="left", fill="x", expand=True)
        palette = palette_for(parent)
        self.button = tk.Button(
            self, text="▦", command=self.open_calendar,
            font=("Segoe UI Symbol", 11), width=3, relief="flat", bd=0,
            bg=palette["panel_alt"], fg=palette["text"],
            activebackground=palette["selected"], activeforeground=palette["text"],
            cursor="hand2", padx=3, pady=4, takefocus=True,
        )
        self.button.pack(side="left", padx=(5, 0))
        self.button.bind("<Enter>", self._hover)
        self.button.bind("<Leave>", self._unhover)
        self.button.bind("<Escape>", self._on_owner_escape, add="+")
        self.entry.bind("<Escape>", self._on_owner_escape, add="+")
        self.bind("<Destroy>", self._on_destroy, add="+")

    def _cancel_focus_job(self):
        job, self._focus_job = self._focus_job, None
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass

    def _on_destroy(self, event=None):
        if event is not None and event.widget is not self:
            return
        self._cancel_focus_job()
        self._close_calendar(restore_focus=False)

    def _hover(self, _event=None):
        palette = palette_for(self)
        self.button.configure(bg=palette["selected"], fg=palette["text"])

    def _unhover(self, _event=None):
        palette = palette_for(self)
        self.button.configure(bg=palette["panel_alt"], fg=palette["text"])

    def _current_date(self):
        try:
            return date.fromisoformat(self.variable.get().strip())
        except (ValueError, TypeError):
            return date.today()

    def open_calendar(self):
        if self._popup is not None:
            try:
                if self._popup.winfo_exists():
                    # The calendar icon acts as a toggle, not as a redundant lift.
                    self._close_calendar(restore_focus=True)
                    return
            except tk.TclError:
                self._popup = None

        owner = self.winfo_toplevel()
        if not self.winfo_exists() or not self.button.winfo_exists():
            return
        owner.update_idletasks()
        palette = palette_for(self)
        current = self._current_date()
        year = [current.year]
        month = [current.month]
        selected = [current]
        self._day_buttons = []

        # A child Frame overlay avoids creating a second Toplevel/grab. It is
        # placed above the form's normal pack/grid layout and removed cleanly.
        popup = tk.Frame(
            owner, bg=palette["border"], padx=1, pady=1,
            highlightthickness=0, takefocus=True,
        )
        self._popup = popup
        self._root_widget = self._root()
        _active_picker_set(self._root_widget).add(self)
        card = tk.Frame(popup, bg=palette["panel"], padx=13, pady=12)
        card.pack(fill="both", expand=True)

        header = tk.Frame(card, bg=palette["panel"])
        header.pack(fill="x", pady=(0, 9))
        month_label = tk.Label(
            header, bg=palette["panel"], fg=palette["text"],
            font=("Segoe UI", 11, "bold"), anchor="w",
        )
        month_label.pack(side="left", fill="x", expand=True, padx=(8, 6))

        def make_button(parent, text, command, width=3, **kwargs):
            button = tk.Button(
                parent, text=text, command=command, width=width,
                bg=palette["panel_alt"], fg=palette["text"],
                activebackground=palette["selected"], activeforeground=palette["text"],
                relief="flat", bd=0, highlightthickness=0,
                font=("Segoe UI", 9, "bold"), cursor="hand2", takefocus=True,
                padx=4, pady=4, **kwargs,
            )
            button.bind("<Escape>", lambda _event: close(), add="+")
            return button

        grid = tk.Frame(card, bg=palette["panel"])
        grid.pack(fill="both", expand=True)
        footer = tk.Frame(card, bg=palette["panel"])
        footer.pack(fill="x", pady=(9, 0))

        def close():
            self._close_calendar()

        def choose(day_value):
            if day_value:
                self.variable.set(date(year[0], month[0], day_value).isoformat())
            close()

        def change_month(delta):
            month[0] += delta
            if month[0] < 1:
                month[0] = 12
                year[0] -= 1
            elif month[0] > 12:
                month[0] = 1
                year[0] += 1
            draw()

        def draw():
            for child in grid.winfo_children():
                child.destroy()
            self._day_buttons.clear()
            month_label.configure(text=f"{MONTHS[month[0] - 1].capitalize()} {year[0]}")

            today = date.today()
            for column, weekday in enumerate(WEEKDAYS):
                tk.Label(
                    grid, text=weekday, width=4, height=1,
                    bg=palette["panel"], fg=palette["muted"],
                    font=("Segoe UI", 8, "bold"),
                ).grid(row=0, column=column, padx=1, pady=(0, 4))

            for row_index, week in enumerate(month_weeks(year[0], month[0]), start=1):
                for column, day_value in enumerate(week):
                    if not day_value:
                        tk.Label(grid, text="", width=4, height=1, bg=palette["panel"]).grid(
                            row=row_index, column=column, padx=1, pady=1,
                        )
                        continue
                    current_day = date(year[0], month[0], day_value)
                    is_today = current_day == today
                    is_selected = current_day == selected[0]
                    background = palette["accent"] if is_today else palette["selected"] if is_selected else palette["panel"]
                    foreground = palette["panel"] if is_today else palette["text"]
                    button = tk.Button(
                        grid, text=str(day_value), width=3, height=1,
                        command=lambda value=day_value: choose(value),
                        bg=background, fg=foreground,
                        activebackground=palette["accent_hover"], activeforeground=palette["panel"],
                        relief="flat", bd=0, highlightthickness=0,
                        font=("Segoe UI", 9, "bold" if (is_today or is_selected) else "normal"),
                        cursor="hand2", takefocus=True,
                    )
                    button.grid(row=row_index, column=column, padx=1, pady=1, ipadx=2, ipady=2)
                    button.bind(
                        "<Enter>",
                        lambda _event, target=button, today_flag=is_today: target.configure(
                            bg=palette["accent_hover"] if today_flag else palette["selected"],
                            fg=palette["panel"] if today_flag else palette["text"],
                        ),
                    )
                    button.bind(
                        "<Leave>",
                        lambda _event, target=button, bg=background, fg=foreground: target.configure(bg=bg, fg=fg),
                    )
                    button.bind("<Escape>", lambda _event: close(), add="+")
                    self._day_buttons.append(button)

        def choose_today():
            self.variable.set(date.today().isoformat())
            close()

        make_button(header, "‹", lambda: change_month(-1)).pack(side="left")
        make_button(header, "›", lambda: change_month(1)).pack(side="right")
        make_button(header, "×", close, width=2).pack(side="right", padx=(5, 0))
        make_button(footer, "Hoy", choose_today, width=8).pack(side="right")
        make_button(footer, "Cerrar", close, width=8).pack(side="right", padx=(0, 7))
        draw()

        # The overlay is constrained to the owning window, which keeps it in
        # front of modal forms without crossing window/grab boundaries.
        owner.update_idletasks()
        popup.update_idletasks()
        popup_width = max(306, popup.winfo_reqwidth() + 2)
        popup_height = max(302, popup.winfo_reqheight() + 2)
        owner_width = max(owner.winfo_width(), 1)
        owner_height = max(owner.winfo_height(), 1)
        anchor_x = self.button.winfo_rootx() - owner.winfo_rootx()
        anchor_y = self.button.winfo_rooty() - owner.winfo_rooty()
        below_y = anchor_y + self.button.winfo_height() + 5
        above_y = anchor_y - popup_height - 5
        if below_y + popup_height <= owner_height - 6:
            popup_y = below_y
        elif above_y >= 6:
            popup_y = above_y
        else:
            popup_y = max(6, min(below_y, owner_height - popup_height - 6))
        popup_x = max(6, min(anchor_x, owner_width - popup_width - 6))
        # A compact fallback for unusually small dialogs. Their container is
        # expanded in the date-bearing forms, but never let the overlay escape.
        popup_width = min(popup_width, max(280, owner_width - 12))
        popup_height = min(popup_height, max(280, owner_height - 12))
        popup.place(x=popup_x, y=popup_y, width=popup_width, height=popup_height)
        popup.lift()
        popup.focus_set()
        popup.bind("<Escape>", lambda _event: close())
        self._cancel_focus_job()
        self._focus_job = self.after_idle(self._focus_calendar_day)

    def _focus_calendar_day(self):
        if self._popup is None:
            return
        try:
            if self._day_buttons:
                target = next((b for b in self._day_buttons if b.cget("text") == str(self._current_date().day)), self._day_buttons[0])
                target.focus_set()
            elif self._popup.winfo_exists():
                self._popup.focus_set()
        except tk.TclError:
            pass

    @staticmethod
    def _is_descendant(widget, ancestor):
        """Return whether a Tk widget belongs to an ancestor widget subtree."""
        current = widget
        while current is not None:
            if current is ancestor:
                return True
            try:
                current = current.master
            except AttributeError:
                return False
        return False

    def _handle_global_click(self, event):
        popup = self._popup
        if popup is None:
            return
        clicked = getattr(event, "widget", None)
        # Keep the calendar open for clicks inside itself or in its own entry/button.
        # Clicking another date field closes this one before that field opens.
        if self._is_descendant(clicked, popup) or self._is_descendant(clicked, self):
            return
        self._close_calendar(restore_focus=False)

    def _on_owner_escape(self, _event=None):
        if self._popup is not None:
            self._close_calendar(restore_focus=True)
            return "break"
        return None

    def _close_calendar(self, restore_focus=True):
        self._cancel_focus_job()
        root = self._root_widget
        self._root_widget = None
        if root is not None:
            try:
                _ACTIVE_PICKERS.get(root, weakref.WeakSet()).discard(self)
            except (KeyError, TypeError):
                pass
        popup = self._popup
        self._popup = None
        self._day_buttons.clear()
        if popup is not None:
            try:
                if popup.winfo_exists():
                    popup.destroy()
            except tk.TclError:
                pass
        if restore_focus:
            try:
                if self.entry.winfo_exists():
                    self.entry.focus_set()
            except tk.TclError:
                pass
