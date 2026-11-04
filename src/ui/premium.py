"""Polished, themed message and confirmation dialogs (no extra dependencies)."""
from __future__ import annotations

import tkinter as tk

from src.ui.theme_manager import THEMES, DEFAULT_THEME


def palette_for(widget):
    try:
        root = widget.winfo_toplevel()
        manager = getattr(root, "theme_manager", None)
        if manager:
            return manager.palette
    except Exception:
        pass
    return THEMES[DEFAULT_THEME]


class PremiumMessageDialog(tk.Toplevel):
    def __init__(self, parent, title, message, kind="info", confirm=False):
        super().__init__(parent)
        self.result = False
        self.confirm_mode = confirm
        self._previous_grab = None
        self._destroying = False
        self._fade_job = None
        self.palette = palette_for(parent)
        p = self.palette
        accent = p["expense"] if kind == "error" else p["accent"]
        self.overrideredirect(True)
        self.configure(bg=p["border"])
        self.transient(parent.winfo_toplevel() if parent is not None else None)
        self.resizable(False, False)

        outer = tk.Frame(self, bg=p["border"], padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        card = tk.Frame(outer, bg=p["panel"])
        card.pack(fill="both", expand=True)
        tk.Frame(card, bg=accent, height=4).pack(fill="x")

        header = tk.Frame(card, bg=p["panel"], padx=22, pady=15)
        header.pack(fill="x")
        tk.Label(header, text="GESTOR FINANCIERO", bg=p["panel"], fg=p["muted"], font=("Segoe UI", 8, "bold")).pack(side="left")
        close = tk.Button(header, text="×", command=self._close, bg=p["panel"], fg=p["muted"], activebackground=p["panel_alt"], activeforeground=p["text"], relief="flat", bd=0, font=("Segoe UI", 15), cursor="hand2", padx=5)
        close.pack(side="right")

        content = tk.Frame(card, bg=p["panel"], padx=24, pady=2)
        content.pack(fill="both", expand=True)
        tk.Label(content, text=title, bg=p["panel"], fg=p["text"], font=("Segoe UI", 16, "bold"), anchor="w", justify="left", wraplength=420).pack(fill="x", anchor="w")
        tk.Label(content, text=message, bg=p["panel"], fg=p["muted"], font=("Segoe UI", 10), anchor="w", justify="left", wraplength=420).pack(fill="x", anchor="w", pady=(9, 15))

        footer = tk.Frame(card, bg=p["panel_alt"], padx=20, pady=13)
        footer.pack(fill="x")
        if confirm:
            self._button(footer, "Cancelar", self._close, primary=False).pack(side="right", padx=(0, 8))
            self._button(footer, "Confirmar", self._confirm, primary=True).pack(side="right")
        else:
            self._button(footer, "Entendido", self._confirm, primary=True).pack(side="right")

        self.bind("<Escape>", lambda _e: self._close())
        self.bind("<Return>", lambda _e: self._confirm())
        self.protocol("WM_DELETE_WINDOW", self._close)
        self._place(parent)
        self._capture_previous_grab(parent)
        self.grab_set()
        self._activation_job = self.after_idle(self._activate_modal)
        self._fade_job = self.after(10, self._fade_in)

    def _activate_modal(self):
        self._activation_job = None
        try:
            if self.winfo_exists():
                self.deiconify()
                self.lift()
                self.focus_force()
        except tk.TclError:
            pass

    def _capture_previous_grab(self, parent):
        try:
            owner = parent.winfo_toplevel() if parent is not None else self.master
            previous = owner.grab_current() if owner is not None else None
            if previous is not None and previous is not self:
                previous.grab_release()
                self._previous_grab = previous
        except tk.TclError:
            self._previous_grab = None

    def destroy(self):
        if self._destroying:
            return
        self._destroying = True
        previous = self._previous_grab
        self._previous_grab = None
        self._cancel_fade()
        activation, self._activation_job = getattr(self, "_activation_job", None), None
        if activation is not None:
            try:
                self.after_cancel(activation)
            except tk.TclError:
                pass
        try:
            try:
                self.grab_release()
            except tk.TclError:
                pass
            super().destroy()
        finally:
            if previous is not None:
                try:
                    if previous.winfo_exists():
                        previous.grab_set()
                        previous.focus_set()
                except tk.TclError:
                    pass

    def _cancel_fade(self):
        job, self._fade_job = self._fade_job, None
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass

    def _button(self, parent, text, command, primary=False):
        p = self.palette
        bg = p["accent"] if primary else p["panel"]
        fg = p["panel"] if primary else p["text"]
        hover = p["accent_hover"] if primary else p["selected"]
        button = tk.Button(parent, text=text, command=command, bg=bg, fg=fg, activebackground=hover, activeforeground=fg, relief="flat", bd=0, highlightthickness=0, font=("Segoe UI", 9, "bold"), padx=19, pady=9, cursor="hand2")
        button.bind("<Enter>", lambda _e: button.configure(bg=hover))
        button.bind("<Leave>", lambda _e: button.configure(bg=bg))
        return button

    def _place(self, parent):
        self.update_idletasks()
        width, height = 500, 250 if self.confirm_mode else 230
        try:
            owner = parent.winfo_toplevel()
            px, py = owner.winfo_rootx(), owner.winfo_rooty()
            pw, ph = owner.winfo_width(), owner.winfo_height()
            x = px + max(0, (pw - width) // 2)
            y = py + max(0, (ph - height) // 2)
        except Exception:
            x = y = 100
        self.geometry(f"{width}x{height}+{x}+{y}")
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            pass

    def _fade_in(self, step=0):
        try:
            self.attributes("-alpha", min(1.0, (step + 1) / 8))
        except tk.TclError:
            return
        if step < 7 and self.winfo_exists():
            self._fade_job = self.after(16, lambda: self._fade_in(step + 1))
        else:
            self._fade_job = None

    def _confirm(self):
        self.result = True
        self.destroy()

    def _close(self):
        self.result = False
        self.destroy()


class PremiumWindow(tk.Toplevel):
    """Borderless, movable secondary window using the current application theme."""

    def __init__(self, parent, title, geometry="720x440", modal=False):
        super().__init__(parent)
        owner = parent.winfo_toplevel() if parent is not None else None
        self.theme_manager = getattr(owner, "theme_manager", None)
        if self.theme_manager is None:
            self.theme_manager = getattr(parent, "theme_manager", None)
        self.palette = self.theme_manager.palette if self.theme_manager else palette_for(parent)
        self.modal = modal
        self._drag_offset = (0, 0)
        self._previous_grab = None
        self._destroying = False
        self._fade_job = None
        p = self.palette

        self.overrideredirect(True)
        self.configure(bg=p["border"])
        self.resizable(False, False)
        if owner is not None:
            self.transient(owner)

        outer = tk.Frame(self, bg=p["border"], padx=1, pady=1)
        outer.pack(fill="both", expand=True)
        card = tk.Frame(outer, bg=p["panel"])
        card.pack(fill="both", expand=True)
        tk.Frame(card, bg=p["accent"], height=4).pack(fill="x")

        self.header = tk.Frame(card, bg=p["panel"], padx=18, pady=12, cursor="fleur")
        self.header.pack(fill="x")
        self.title_label = tk.Label(
            self.header, text=title, bg=p["panel"], fg=p["text"],
            font=("Segoe UI", 12, "bold"), anchor="w",
        )
        self.title_label.pack(side="left", fill="x", expand=True)
        self.close_button = tk.Button(
            self.header, text="×", command=self.destroy,
            bg=p["panel"], fg=p["muted"], activebackground=p["panel_alt"],
            activeforeground=p["text"], relief="flat", bd=0,
            font=("Segoe UI", 15), cursor="hand2", padx=7,
        )
        self.close_button.pack(side="right")
        self.close_button.bind("<Enter>", lambda _e: self.close_button.configure(bg=p["panel_alt"]))
        self.close_button.bind("<Leave>", lambda _e: self.close_button.configure(bg=p["panel"]))

        self.body = tk.Frame(card, bg=p["bg"], padx=18, pady=15)
        self.body.pack(fill="both", expand=True)
        for widget in (self.header, self.title_label):
            widget.bind("<ButtonPress-1>", self._start_drag)
            widget.bind("<B1-Motion>", self._drag)

        self.bind("<Escape>", lambda _e: self.destroy())
        self.protocol("WM_DELETE_WINDOW", self.destroy)
        self._set_geometry(parent, geometry)
        try:
            self.attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        if modal:
            self._capture_previous_grab(owner)
            self.grab_set()
        self._activation_job = self.after_idle(self._activate_window)
        self._fade_job = self.after(10, self._fade_in)

    def _activate_window(self):
        self._activation_job = None
        try:
            if self.winfo_exists():
                self.deiconify()
                self.lift()
                if self.modal:
                    self.focus_force()
        except tk.TclError:
            pass

    def _capture_previous_grab(self, owner):
        if owner is None:
            return
        try:
            previous = owner.grab_current()
            if previous is not None and previous is not self:
                previous.grab_release()
                self._previous_grab = previous
        except tk.TclError:
            self._previous_grab = None

    def destroy(self):
        if self._destroying:
            return
        self._destroying = True
        previous = self._previous_grab
        self._previous_grab = None
        self._cancel_fade()
        activation, self._activation_job = getattr(self, "_activation_job", None), None
        if activation is not None:
            try:
                self.after_cancel(activation)
            except tk.TclError:
                pass
        try:
            if self.modal:
                try:
                    self.grab_release()
                except tk.TclError:
                    pass
            super().destroy()
        finally:
            if previous is not None:
                try:
                    if previous.winfo_exists():
                        previous.grab_set()
                        previous.focus_set()
                except tk.TclError:
                    pass

    def _cancel_fade(self):
        job, self._fade_job = self._fade_job, None
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass

    def _set_geometry(self, parent, geometry):
        self.update_idletasks()
        try:
            width, height = (int(part) for part in geometry.lower().split("x", 1))
            if parent is not None:
                owner = parent.winfo_toplevel()
                x = owner.winfo_rootx() + max(0, (owner.winfo_width() - width) // 2)
                y = owner.winfo_rooty() + max(0, (owner.winfo_height() - height) // 2)
            else:
                x = max(0, (self.winfo_screenwidth() - width) // 2)
                y = max(0, (self.winfo_screenheight() - height) // 2)
            self.minsize(width, height)
            self.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            self.geometry(geometry)

    def _start_drag(self, event):
        self._drag_offset = (event.x_root - self.winfo_rootx(), event.y_root - self.winfo_rooty())

    def _drag(self, event):
        x = event.x_root - self._drag_offset[0]
        y = event.y_root - self._drag_offset[1]
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

    def _fade_in(self, step=0):
        try:
            self.attributes("-alpha", min(1.0, (step + 1) / 8))
        except tk.TclError:
            return
        if step < 7 and self.winfo_exists():
            self._fade_job = self.after(16, lambda: self._fade_in(step + 1))
        else:
            self._fade_job = None


def _show(parent, title, message, kind="info", confirm=False):
    dialog = PremiumMessageDialog(parent, title, message, kind=kind, confirm=confirm)
    if parent is not None:
        parent.wait_window(dialog)
    else:
        dialog.wait_window()
    return dialog.result


class messagebox:
    @staticmethod
    def showinfo(title, message, parent=None, **_kwargs):
        _show(parent, title, message, "info", False)
        return "ok"

    @staticmethod
    def showwarning(title, message, parent=None, **_kwargs):
        _show(parent, title, message, "warning", False)
        return "ok"

    @staticmethod
    def showerror(title, message, parent=None, **_kwargs):
        _show(parent, title, message, "error", False)
        return "ok"

    @staticmethod
    def askyesno(title, message, parent=None, **_kwargs):
        return _show(parent, title, message, "warning", True)
