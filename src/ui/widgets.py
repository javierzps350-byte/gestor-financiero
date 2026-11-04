"""Reusable, understated controls for the desktop UI."""
from __future__ import annotations

from tkinter import ttk


class ElegantCombobox(ttk.Combobox):
    """Read-only select styled as a clean field without a visible arrow.

    Tk's native combobox class bindings still open its standard popdown when
    the field is clicked, so the interaction remains familiar and accessible
    while the old arrow button is removed from the layout.
    """

    def __init__(self, master=None, **kwargs):
        kwargs.setdefault("style", "Elegant.TCombobox")
        super().__init__(master, **kwargs)
        self.bind("<FocusIn>", self._focus_in, add="+")
        self.bind("<FocusOut>", self._focus_out, add="+")

    def _focus_in(self, _event=None):
        try:
            self.state(["focus"])
        except Exception:
            pass

    def _focus_out(self, _event=None):
        try:
            self.state(["!focus"])
        except Exception:
            pass
