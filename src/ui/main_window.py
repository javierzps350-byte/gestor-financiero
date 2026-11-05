import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
import calendar
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, ttk

from src.config import APP_NAME, BACKUP_DIR, EVIDENCE_DIR
from src.database.connection import get_connection
from src.domain.money import format_money
from src.services.finance_service import (
    client_debt_summary, client_payment_history, dashboard_visual_data,
    list_client_charges, list_clients, search_movements, set_client_active,
    void_movement,
)
from src.services.evidence_service import evidence_absolute_path
from src.services.report_service import export_report, build_movement_report, build_debt_report
from src.services.backup_service import create_portable_backup, restore_portable_backup
from src.ui.dialogs import ClientDialog, MovementDialog, RateDialog
from src.ui.theme_manager import ThemeManager, THEMES
from src.ui.premium import messagebox, palette_for, PremiumWindow
from src.ui.date_picker import DatePickerEntry
from src.ui.widgets import ElegantCombobox
from src.ui.assistant_view import AssistantView
from src.ui.charts import MonthlyLineChart, ExpenseDonutChart, TEAL, CORAL
from src.ui.window_chrome import NativeWindowChrome

BG = "#F2F6FA"
PANEL = "#FFFFFF"
PANEL_ALT = "#EEF3F7"
TEXT = "#243449"
MUTED = "#8190A2"
ACCENT = "#2BAE9B"
GREEN = "#2BAE9B"
RED = "#E9897D"
BORDER = "#E1E8EF"
SIDEBAR = "#FFFFFF"
WHITE = "#FFFFFF"


class MainWindow:
    """Main application shell with lightweight animated page navigation."""

    NAV_ITEMS = [
        ("dashboard", "Resumen"),
        ("incomes", "Ingresos"),
        ("expenses", "Gastos"),
        ("clients", "Clientes"),
        ("debts", "Mensualidades"),
        ("search", "Buscador"),
        ("assistant", "Agente"),
    ]

    def __init__(self, root: tk.Tk):
        self.root = root
        self.current_page = None
        self._transition_token = 0
        self._transition_after_id = None
        self._nav_widgets = {}
        self.theme_manager = ThemeManager()
        root.theme_manager = self.theme_manager
        root.title(APP_NAME)
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        # Use the real monitor pixel dimensions (main.py enables per-monitor
        # DPI awareness on Windows). The window grows on large screens while
        # remaining usable on compact office monitors; no 720p render target.
        window_width = min(1680, max(1040, screen_width - 48))
        window_height = min(1000, max(660, screen_height - 72))
        window_width = min(window_width, screen_width - 16)
        window_height = min(window_height, screen_height - 32)
        x = max(0, (screen_width - window_width) // 2)
        y = max(0, (screen_height - window_height) // 2)
        root.geometry(f"{window_width}x{window_height}+{x}+{y}")
        root.minsize(min(980, window_width), min(620, window_height))
        self.chrome = NativeWindowChrome(root)
        self.chrome.install()
        root.protocol("WM_DELETE_WINDOW", root.destroy)
        root.configure(bg=self.theme_manager.palette["bg"])
        self._configure_style()
        self._build_shell()
        self.apply_theme()
        root.bind("<Destroy>", self._on_root_destroy, add="+")

    def _configure_style(self):
        self.theme_manager.configure_styles(self.root)

    def _cancel_transition(self):
        job, self._transition_after_id = self._transition_after_id, None
        if job is not None:
            try:
                self.root.after_cancel(job)
            except tk.TclError:
                pass

    def _on_root_destroy(self, event):
        if event.widget is self.root:
            self._transition_token += 1
            self._cancel_transition()

    def apply_theme(self):
        charts = (self.dashboard.line_chart, self.dashboard.donut_chart) if hasattr(self, "dashboard") else ()
        self.theme_manager.apply(self.root, charts=charts)
        p = self.theme_manager.palette
        if hasattr(self, "data_button"):
            self.data_button.configure(bg=p["panel"], fg=p["text"], activebackground=p["selected"], activeforeground=p["text"])
        self._draw_theme_swatches()
        self._apply_window_chrome_theme(p)
        if hasattr(self, "dashboard"):
            self.dashboard.apply_theme(p)
            self.dashboard.recent_tree.tag_configure("income", foreground=p["success"])
            self.dashboard.recent_tree.tag_configure("expense", foreground=p["expense"])
            self.dashboard.recent_tree.tag_configure("void", foreground=p["muted"])
        for view_name in ("incomes", "expenses", "search"):
            view = getattr(self, view_name, None)
            if view is not None and hasattr(view, "tree"):
                view.tree.tag_configure("void", foreground=p["muted"])
        if hasattr(self, "debts"):
            self.debts.tree.tag_configure("paid", foreground=p["success"])
            self.debts.tree.tag_configure("late", foreground=p["danger"])
            self.debts.tree.tag_configure("partial", foreground=p["expense"])
            self.debts.apply_theme(p)
        if hasattr(self, "assistant"):
            self.assistant.set_theme(p)
        if self.current_page:
            self._set_nav_active(self.current_page)

    def change_theme(self, theme_id: str):
        if theme_id not in THEMES:
            return
        self.theme_manager.set_theme(theme_id)
        self.apply_theme()
        self.root.after_idle(self.root.focus_set)

    def _position_floating_window(self, window, anchor, width, height, side="right"):
        self.root.update_idletasks()
        anchor.update_idletasks()
        if side == "right":
            x = anchor.winfo_rootx() + anchor.winfo_width() + 12
        else:
            x = anchor.winfo_rootx() - width - 12
        y = anchor.winfo_rooty() + anchor.winfo_height() - height
        screen_w = self.root.winfo_screenwidth()
        screen_h = self.root.winfo_screenheight()
        x = max(8, min(x, screen_w - width - 8))
        y = max(8, min(y, screen_h - height - 8))
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _draw_theme_swatches(self):
        # Draw three compact icon-only theme selectors at the bottom of the sidebar.
        canvas = getattr(self, "theme_canvas", None)
        if canvas is None:
            return
        p = self.theme_manager.palette
        canvas.configure(bg=p["sidebar"])
        canvas.delete("all")
        swatches = (
            # Three small faceted marks echo the floating geometric accents in the reference.
            ("claro", 19, "#F6F8FA", "#D4E2EC", "#96B8C9"),
            ("suave", 53, "#F1F2EE", "#CCD2CC", "#9BAAA1"),
            ("oscuro", 87, "#60788B", "#344B5D", "#1E2D3A"),
        )
        for theme_id, x, top_color, left_color, right_color in swatches:
            active = theme_id == self.theme_manager.theme_id
            canvas.create_oval(
                x - 13, 3, x + 13, 31,
                fill=p["selected"] if active else p["sidebar"],
                outline=p["accent"] if active else p["border"],
                width=1.5 if active else 1,
            )
            tags = (f"theme:{theme_id}",)
            # Top and two shaded faces make each mark read as a tiny 3-D tile.
            canvas.create_polygon(
                x, 6, x + 9, 11, x, 17, x - 9, 11,
                fill=top_color, outline=p["border"], width=0.8, tags=tags,
            )
            canvas.create_polygon(
                x - 9, 11, x, 17, x, 28, x - 9, 22,
                fill=left_color, outline=p["border"], width=0.8, tags=tags,
            )
            canvas.create_polygon(
                x + 9, 11, x, 17, x, 28, x + 9, 22,
                fill=right_color, outline=p["border"], width=0.8, tags=tags,
            )
        canvas.configure(cursor="hand2")

    def _on_theme_swatches_click(self, event):
        for theme_id, x in (("claro", 19), ("suave", 53), ("oscuro", 87)):
            if abs(event.x - x) <= 13:
                self.change_theme(theme_id)
                return "break"
        return None

    def _begin_title_drag(self, _event=None):
        self.chrome.begin_drag()

    def _minimize_window(self):
        try:
            self.root.iconify()
        except tk.TclError:
            pass

    def _toggle_maximize(self, _event=None):
        try:
            self.root.state("normal" if self.root.state() == "zoomed" else "zoomed")
            self.root.after(80, self._refresh_maximize_glyph)
        except tk.TclError:
            pass
        return "break"

    def _refresh_maximize_glyph(self):
        try:
            if hasattr(self, "maximize_button") and self.maximize_button.winfo_exists():
                self.maximize_button.configure(text="▢" if self.root.state() == "zoomed" else "□")
        except tk.TclError:
            pass

    def _apply_window_chrome_theme(self, palette):
        if not hasattr(self, "window_titlebar"):
            return
        self.window_titlebar.configure(bg=palette["sidebar"])
        self.window_title.configure(bg=palette["sidebar"], fg=palette["text"])
        self.window_brand.configure(bg=palette["sidebar"], fg=palette["accent"])
        for button in (getattr(self, "minimize_button", None), getattr(self, "maximize_button", None)):
            if button is not None:
                button.configure(
                    bg=palette["sidebar"], fg=palette["text"],
                    activebackground=palette["selected"], activeforeground=palette["text"],
                )
        if hasattr(self, "close_button"):
            self.close_button.configure(
                bg=palette["sidebar"], fg=palette["muted"],
                activebackground=palette["danger"], activeforeground=palette["panel"],
            )
        if hasattr(self, "data_button"):
            self.data_button.configure(
                bg=palette["sidebar"], fg=palette["text"],
                activebackground=palette["selected"], activeforeground=palette["text"],
            )

    def open_data_actions(self):
        current = getattr(self, "_data_picker", None)
        if current is not None:
            try:
                if current.winfo_exists():
                    current.lift()
                    return
            except tk.TclError:
                self._data_picker = None
        dialog = PremiumWindow(self.root, "Datos", "356x190", modal=False)
        self._data_picker = dialog
        p = self.theme_manager.palette
        ttk.Label(dialog.body, text="Respaldo y traslado de información", style="Hint.TLabel").pack(anchor="w", pady=(0, 10))
        for label, callback in (
            ("Crear paquete para trasladar…", self.export_portable_backup),
            ("Restaurar paquete en este equipo…", self.import_portable_backup),
        ):
            button = ttk.Button(dialog.body, text=label, style="Quiet.TButton", command=lambda action=callback, popup=dialog: self._run_data_action(action, popup))
            button.pack(fill="x", pady=4)
        self._position_floating_window(dialog, self.data_button, 356, 190, side="left")

    def _run_data_action(self, callback, dialog):
        try:
            dialog.destroy()
        except tk.TclError:
            pass
        self._data_picker = None
        callback()

    def export_portable_backup(self):
        stamp = date.today().strftime("%Y%m%d")
        destination = filedialog.asksaveasfilename(
            parent=self.root, title="Crear paquete completo para trasladar",
            initialfile=f"GestorFinanciero_respaldo_{stamp}.gfbak",
            defaultextension=".gfbak",
            filetypes=[("Paquete de traslado Gestor Financiero", "*.gfbak")],
        )
        if not destination:
            return
        try:
            path = create_portable_backup(destination)
            messagebox.showinfo(
                "Paquete creado",
                "El paquete incluye la base de datos, clientes, movimientos, mensualidades y evidencias.\n\n"
                f"Archivo: {path}", parent=self.root,
            )
        except Exception as exc:
            messagebox.showerror("No se pudo crear el paquete", str(exc), parent=self.root)

    def import_portable_backup(self):
        source = filedialog.askopenfilename(
            parent=self.root, title="Seleccionar paquete de traslado",
            filetypes=[("Paquete Gestor Financiero", "*.gfbak"), ("Todos los archivos", "*.*")],
        )
        if not source:
            return
        try:
            from src.services.backup_service import inspect_portable_backup
            manifest = inspect_portable_backup(source)
            evidence_count = int(manifest.get("evidence_count", 0))
            created = manifest.get("created_at", "fecha desconocida")
            proceed = messagebox.askyesno(
                "Confirmar restauración",
                "Se reemplazarán los datos actuales por los del paquete seleccionado.\n\n"
                f"Respaldo creado: {created}\nEvidencias: {evidence_count}\n\n"
                "Antes de restaurar se guardará automáticamente una copia del estado actual.\n"
                "¿Deseas continuar?",
                parent=self.root,
            )
            if not proceed:
                return
            result = restore_portable_backup(source)
            self.refresh_all()
            messagebox.showinfo(
                "Restauración terminada",
                "Los datos y evidencias se restauraron correctamente.\n\n"
                f"Copia anterior: {result.get('rollback_backup') or 'No había una base previa'}",
                parent=self.root,
            )
        except Exception as exc:
            messagebox.showerror("No se pudo restaurar el paquete", str(exc), parent=self.root)

    def _build_shell(self):
        p = self.theme_manager.palette
        top = tk.Frame(self.root, bg=p["sidebar"], height=46, padx=17)
        top.pack(fill="x")
        top.pack_propagate(False)
        self.window_titlebar = top
        self.window_brand = tk.Label(
            top, text="●", bg=p["sidebar"], fg=p["accent"],
            font=("Segoe UI Symbol", 10), padx=2,
        )
        self.window_brand.pack(side="left", padx=(0, 8))
        self.window_title = tk.Label(
            top, text="Gestor Financiero", bg=p["sidebar"], fg=p["text"],
            font=("Segoe UI", 10, "bold"), anchor="w",
        )
        self.window_title.pack(side="left", anchor="center")

        self.close_button = tk.Button(
                top, text="×", command=self.root.destroy,
                bg=p["sidebar"], fg=p["muted"], activebackground=p["danger"],
                activeforeground=p["panel"], relief="flat", bd=0,
                highlightthickness=0, font=("Segoe UI Symbol", 13),
                width=4, cursor="hand2",
            )
        self.close_button.pack(side="right", fill="y")
        self.maximize_button = tk.Button(
                top, text="□", command=self._toggle_maximize,
                bg=p["sidebar"], fg=p["text"], activebackground=p["selected"],
                activeforeground=p["text"], relief="flat", bd=0,
                highlightthickness=0, font=("Segoe UI Symbol", 10),
                width=4, cursor="hand2",
            )
        self.maximize_button.pack(side="right", fill="y")
        self.minimize_button = tk.Button(
                top, text="—", command=self._minimize_window,
                bg=p["sidebar"], fg=p["text"], activebackground=p["selected"],
                activeforeground=p["text"], relief="flat", bd=0,
                highlightthickness=0, font=("Segoe UI", 12),
                width=4, cursor="hand2",
            )
        self.minimize_button.pack(side="right", fill="y")
        for button in (self.minimize_button, self.maximize_button):
            button.bind("<Enter>", lambda _event, target=button: target.configure(bg=self.theme_manager.palette["selected"]))
            button.bind("<Leave>", lambda _event, target=button: target.configure(bg=self.theme_manager.palette["sidebar"]))
        self.close_button.bind("<Enter>", lambda _event: self.close_button.configure(bg=self.theme_manager.palette["danger"]))
        self.close_button.bind("<Leave>", lambda _event: self.close_button.configure(bg=self.theme_manager.palette["sidebar"]))

        self.data_button = tk.Button(
            top, text="Datos", command=self.open_data_actions,
            bg=p["sidebar"], fg=p["text"], activebackground=p["selected"],
            activeforeground=p["text"], relief="flat", bd=0,
            highlightthickness=0, font=("Segoe UI", 9, "bold"),
            padx=14, cursor="hand2",
        )
        self.data_button.pack(side="right", fill="y", padx=(0, 8))
        self.data_button.bind("<Enter>", lambda _event: self.data_button.configure(bg=self.theme_manager.palette["selected"]))
        self.data_button.bind("<Leave>", lambda _event: self.data_button.configure(bg=self.theme_manager.palette["sidebar"]))

        if self.chrome.installed:
            for drag_target in (top, self.window_brand, self.window_title):
                drag_target.bind("<ButtonPress-1>", self._begin_title_drag, add="+")
                drag_target.bind("<Double-Button-1>", self._toggle_maximize, add="+")

        tk.Frame(self.root, bg=p["border"], height=1).pack(fill="x")

        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)
        self.sidebar = tk.Frame(shell, bg=SIDEBAR, width=124, padx=9, pady=18, highlightthickness=1, highlightbackground=BORDER)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        for page_id, label in self.NAV_ITEMS:
            self._make_nav_button(page_id, label)

        # Three colored marks replace the textual theme selector.
        sidebar_footer = tk.Frame(self.sidebar, bg=SIDEBAR)
        sidebar_footer.pack(side="bottom", fill="x", pady=(10, 0))
        tk.Frame(sidebar_footer, bg=SIDEBAR, height=1).pack(fill="x", pady=(0, 8))
        self.theme_canvas = tk.Canvas(
            sidebar_footer, width=106, height=34, bg=SIDEBAR,
            bd=0, highlightthickness=0, takefocus=True,
        )
        self.theme_canvas.pack(anchor="center")
        self.theme_canvas.bind("<Button-1>", self._on_theme_swatches_click)
        self._draw_theme_swatches()

        work = tk.Frame(shell, bg=BG)
        work.pack(side="left", fill="both", expand=True)
        self.page_host = tk.Frame(work, bg=BG)
        self.page_host.pack(fill="both", expand=True, padx=(17, 20), pady=14)

        self.dashboard = DashboardView(self.page_host, self.refresh_all)
        self.incomes = MovementView(self.page_host, "income", "Ingresos")
        self.expenses = MovementView(self.page_host, "expense", "Gastos")
        self.clients = ClientView(self.page_host, self.refresh_all)
        self.debts = DebtView(self.page_host)
        self.search = MovementView(self.page_host, "all", "Buscador")
        self.assistant = AssistantView(self.page_host, on_data_changed=self.refresh_all, on_navigate=self.show_page)
        self.pages = {
            "dashboard": self.dashboard,
            "incomes": self.incomes,
            "expenses": self.expenses,
            "clients": self.clients,
            "debts": self.debts,
            "search": self.search,
            "assistant": self.assistant,
        }
        self.root.bind("<Control-1>", lambda _e: self.show_page("dashboard"))
        self.root.bind("<Control-2>", lambda _e: self.show_page("incomes"))
        self.root.bind("<Control-3>", lambda _e: self.show_page("expenses"))
        self.root.bind("<Control-4>", lambda _e: self.show_page("clients"))
        self.root.bind("<Control-5>", lambda _e: self.show_page("debts"))
        self.root.bind("<Control-6>", lambda _e: self.show_page("search"))
        self.root.bind("<Control-7>", lambda _e: self.show_page("assistant"))
        self.show_page("dashboard", animate=False)
        self.refresh_all()

    def _make_nav_button(self, page_id, label):
        row = tk.Frame(self.sidebar, bg=SIDEBAR, height=46)
        row.pack(fill="x", padx=1, pady=4)
        row.pack_propagate(False)
        indicator = tk.Frame(row, bg=SIDEBAR, width=3)
        indicator.pack(side="left", fill="y")
        button = tk.Button(
            row, text=label, anchor="center",
            bg=SIDEBAR, fg="#748398", activebackground="#EAF5F3",
            activeforeground=TEXT, relief="flat", bd=0,
            highlightthickness=0, font=("Segoe UI", 9),
            padx=4, pady=7, cursor="hand2",
            command=lambda key=page_id: self.show_page(key),
        )
        button.pack(side="left", fill="both", expand=True)
        button.bind("<Enter>", lambda _e, key=page_id: self._nav_hover(key, True))
        button.bind("<Leave>", lambda _e, key=page_id: self._nav_hover(key, False))
        self._nav_widgets[page_id] = (row, indicator, button)

    def _nav_hover(self, page_id, hovered):
        if page_id == self.current_page:
            return
        p = self.theme_manager.palette
        row, _indicator, button = self._nav_widgets[page_id]
        color = p["selected"] if hovered else p["sidebar"]
        row.configure(bg=color)
        button.configure(bg=color)

    def _set_nav_active(self, page_id):
        p = self.theme_manager.palette
        for key, (row, indicator, button) in self._nav_widgets.items():
            active = key == page_id
            bg = p["selected"] if active else p["sidebar"]
            row.configure(bg=bg)
            indicator.configure(bg=p["accent"] if active else p["sidebar"])
            button.configure(
                bg=bg,
                fg=p["success"] if active else p["muted"],
                font=("Segoe UI", 10, "bold" if active else "normal"),
            )

    def show_page(self, page_id, animate=True):
        if page_id not in self.pages:
            return
        if page_id == self.current_page:
            return
        self._cancel_transition()
        self._transition_token += 1
        token = self._transition_token
        old_page = self.pages.get(self.current_page) if self.current_page else None
        new_page = self.pages[page_id]
        self.current_page = page_id
        self._set_nav_active(page_id)
        if old_page is not None:
            old_page.place_forget()
        if not animate:
            new_page.place(x=0, y=0, relwidth=1, relheight=1)
            return

        # Subtle horizontal entrance; no image filters, GPU, or external animation library.
        start_x = 24
        new_page.place(x=start_x, y=0, relwidth=1, relheight=1)
        frames = 8
        duration_ms = 18

        def animate_step(step=0):
            if token != self._transition_token or not new_page.winfo_exists():
                return
            progress = min(1.0, (step + 1) / frames)
            eased = 1 - (1 - progress) ** 3
            offset = int(start_x * (1 - eased))
            new_page.place_configure(x=offset)
            if step + 1 < frames:
                self._transition_after_id = self.root.after(
                    duration_ms, lambda: animate_step(step + 1)
                )
            else:
                self._transition_after_id = None
                new_page.place_configure(x=0)

        animate_step()

    def refresh_all(self):
        self.dashboard.refresh()
        self.incomes.refresh_filter_options()
        self.expenses.refresh_filter_options()
        self.search.refresh_filter_options()
        self.incomes.refresh()
        self.expenses.refresh()
        self.clients.refresh()
        self.debts.refresh_clients()
        self.search.refresh()


class DashboardView(ttk.Frame):
    """Dashboard inspired by a clean finance workspace, with interactive charts."""

    def __init__(self, parent, refresh_callback):
        super().__init__(parent, padding=4)
        self.refresh_callback = refresh_callback
        self.chart_month = date.today().strftime("%Y-%m")
        self.table_month = None
        self.selected_category = None
        self._shown_values = {"balance": 0, "income": 0, "expenses": 0}
        self._target_values = {"balance": 0, "income": 0, "expenses": 0}
        self._animation_ids = {}
        self._build()

    def destroy(self):
        """Cancel value animations before Tk removes their callback commands."""
        for job in tuple(self._animation_ids.values()):
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        self._animation_ids.clear()
        super().destroy()

    def _panel(self, parent, **kwargs):
        return tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER, **kwargs)

    def apply_theme(self, palette):
        targets = {
            "balance": palette["text"] if self._target_values["balance"] >= 0 else palette["danger"],
            "income": palette["accent"],
            "expenses": palette["expense"],
        }
        for key, target in self._target_values.items():
            self._animate_value(key, target, targets[key])

    def _build(self):
        heading = tk.Frame(self, bg=BG)
        heading.pack(fill="x", pady=(0, 9))
        weekday_names = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
        month_names = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
        today = date.today()
        date_label = f"{weekday_names[today.weekday()].capitalize()}, {today.day} de {month_names[today.month - 1]} de {today.year}"
        tk.Label(heading, text=date_label, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="right", anchor="e", pady=(4, 0))

        cards = tk.Frame(self, bg=BG)
        cards.pack(fill="x", pady=(0, 9))
        cards.grid_columnconfigure((0, 1, 2), weight=1, uniform="top_cards")
        self.card_values = {}
        card_specs = [
            ("balance", "Saldo actual", "Balance de movimientos registrados", "#4E98BA"),
            ("income", "Ingresos del mes", "Total recibido este mes", TEAL),
            ("expenses", "Egresos del mes", "Total pagado este mes", CORAL),
        ]
        for column, (key, label, subtitle, color) in enumerate(card_specs):
            card = self._panel(cards, padx=14, pady=10)
            card.grid(row=0, column=column, sticky="nsew", padx=(0 if column == 0 else 7, 0 if column == 2 else 7))
            accent = tk.Frame(card, bg=color, width=4)
            accent.pack(side="left", fill="y", padx=(0, 13))
            body = tk.Frame(card, bg=PANEL)
            body.pack(side="left", fill="both", expand=True)
            tk.Label(body, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w")
            value = tk.Label(body, text="$0,00", bg=PANEL, fg=TEXT, font=("Segoe UI", 19, "bold"))
            value.pack(anchor="w", pady=(6, 2))
            tk.Label(body, text=subtitle, bg=PANEL, fg="#99A5B3", font=("Segoe UI", 8)).pack(anchor="w")
            self.card_values[key] = value

        charts = tk.Frame(self, bg=BG)
        charts.pack(fill="x", pady=(0, 8))
        charts.grid_columnconfigure(0, weight=6, uniform="charts")
        charts.grid_columnconfigure(1, weight=5, uniform="charts")
        charts.grid_rowconfigure(0, weight=1)

        line_card = self._panel(charts, padx=13, pady=9)
        line_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        line_heading = tk.Frame(line_card, bg=PANEL)
        line_heading.pack(fill="x")
        tk.Label(line_heading, text="Evolución del balance mensual", bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        tk.Label(line_heading, text="Ingresos y gastos · últimos 12 meses", bg=PANEL, fg=MUTED, font=("Segoe UI", 8)).pack(anchor="w", pady=(2, 0))
        self.line_chart = MonthlyLineChart(line_card, self._select_month, height=150)
        self.line_chart.pack(fill="both", expand=True, pady=(3, 0))

        donut_card = self._panel(charts, padx=13, pady=9)
        donut_card.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        donut_heading = tk.Frame(donut_card, bg=PANEL)
        donut_heading.pack(fill="x")
        tk.Label(donut_heading, text="Distribución de gastos por categoría", bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(anchor="w")
        self.category_period_label = tk.Label(donut_heading, text="Este mes", bg=PANEL, fg=MUTED, font=("Segoe UI", 8))
        self.category_period_label.pack(anchor="w", pady=(2, 0))
        self.donut_chart = ExpenseDonutChart(donut_card, self._select_category, height=150)
        self.donut_chart.pack(fill="both", expand=True, pady=(3, 0))

        actions = tk.Frame(self, bg=BG)
        actions.pack(fill="x", pady=(0, 8))
        self._action_button(actions, "Registrar pago recibido", self._new_income, TEAL).pack(side="left", fill="x", expand=True, padx=(0, 6))
        self._action_button(actions, "Registrar pago realizado", self._new_expense, CORAL).pack(side="left", fill="x", expand=True, padx=(6, 0))

        recent = self._panel(self, padx=12, pady=7)
        recent.pack(fill="both", expand=True)
        recent_header = tk.Frame(recent, bg=PANEL)
        recent_header.pack(fill="x", pady=(0, 8))
        tk.Label(recent_header, text="Últimos movimientos", bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left")
        self.filter_label = tk.Label(recent_header, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 8))
        self.filter_label.pack(side="left", padx=(10, 0))
        tk.Button(recent_header, text="Limpiar filtros", command=self.clear_filters, bg=PANEL, fg=ACCENT, activebackground=PANEL, activeforeground=ACCENT, relief="flat", bd=0, font=("Segoe UI", 8, "bold"), cursor="hand2").pack(side="right")

        table_wrap = tk.Frame(recent, bg=PANEL)
        table_wrap.pack(fill="both", expand=True)
        columns = ("date", "description", "category", "type", "amount")
        self.recent_tree = ttk.Treeview(table_wrap, columns=columns, show="headings", height=2, selectmode="browse")
        for key, label, width, anchor in [
            ("date", "Fecha", 105, "center"),
            ("description", "Descripción", 260, "w"),
            ("category", "Categoría", 145, "w"),
            ("type", "Tipo", 105, "center"),
            ("amount", "Monto", 120, "e"),
        ]:
            self.recent_tree.heading(key, text=label)
            self.recent_tree.column(key, width=width, minwidth=65, anchor=anchor, stretch=key == "description")
        scrollbar = ttk.Scrollbar(table_wrap, orient="vertical", command=self.recent_tree.yview)
        self.recent_tree.configure(yscrollcommand=scrollbar.set)
        self.recent_tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.recent_tree.tag_configure("income", foreground=palette_for(self)["success"])
        self.recent_tree.tag_configure("expense", foreground=palette_for(self)["expense"])
        self.recent_tree.tag_configure("void", foreground=palette_for(self)["muted"])


    @staticmethod
    def _action_button(parent, text, command, color):
        role = "accent" if color == TEAL else "expense"
        palette = palette_for(parent)
        base = palette[role]
        hover = palette["accent_hover"] if role == "accent" else palette["expense_hover"]
        button = tk.Button(
            parent, text=text, command=command, anchor="center",
            bg=base, fg=palette["panel"], activebackground=hover, activeforeground=palette["panel"],
            relief="flat", bd=0, highlightthickness=0,
            padx=17, pady=10, font=("Segoe UI", 9, "bold"), cursor="hand2",
        )
        button.bind("<Enter>", lambda _event: button.configure(bg=(palette_for(parent)["accent_hover"] if role == "accent" else palette_for(parent)["expense_hover"])))
        button.bind("<Leave>", lambda _event: button.configure(bg=palette_for(parent)[role]))
        return button

    def _new_income(self):
        MovementDialog(self, "income", self.refresh_callback)

    def _new_expense(self):
        MovementDialog(self, "expense", self.refresh_callback)

    def _select_month(self, month: str):
        self.chart_month = month
        self.table_month = month
        self.selected_category = None
        self.refresh()

    def _select_category(self, category: str):
        if self.selected_category == category:
            self.selected_category = None
        else:
            self.selected_category = category
        self.table_month = self.chart_month
        self.refresh()

    def clear_filters(self):
        self.chart_month = date.today().strftime("%Y-%m")
        self.table_month = None
        self.selected_category = None
        self.refresh()

    def _animate_value(self, key, amount, color):
        old_after = self._animation_ids.pop(key, None)
        if old_after is not None:
            try:
                self.after_cancel(old_after)
            except tk.TclError:
                pass
        start = int(self._shown_values.get(key, 0))
        target = int(amount)
        self._target_values[key] = target
        steps = 10
        def tick(step=1):
            value = int(start + (target - start) * step / steps)
            self.card_values[key].configure(text=format_money(value), fg=color)
            self._shown_values[key] = value
            if step < steps:
                self._animation_ids[key] = self.after(17, lambda: tick(step + 1))
            else:
                self._animation_ids.pop(key, None)
                self._shown_values[key] = target
        tick()

    def refresh(self):
        try:
            data = dashboard_visual_data(
                chart_month=self.chart_month,
                table_month=self.table_month,
                category=self.selected_category,
            )
            palette = palette_for(self)
            targets = {
                "balance": (data["balance_cents"], palette["text"] if data["balance_cents"] >= 0 else palette["danger"]),
                "income": (data["income_month_cents"], palette["accent"]),
                "expenses": (data["expenses_month_cents"], palette["expense"]),
            }
            for key, (amount, color) in targets.items():
                self._animate_value(key, amount, color)
            self.line_chart.set_data(data["series"], self.chart_month)
            self.donut_chart.set_data(data["categories"], self.selected_category)
            self.category_period_label.configure(text=self._month_label(self.chart_month))
            self.recent_tree.delete(*self.recent_tree.get_children())
            for row in data["recent"]:
                is_income = row["direction"] == "income"
                amount = int(row["amount_cents"])
                amount_text = format_money(amount) if is_income else f"-{format_money(amount)}"
                description = row["reason"] or row["counterparty"]
                self.recent_tree.insert(
                    "", "end", iid=str(row["id"]),
                    values=(
                        row["payment_date"], description, row.get("category") or ("Ingresos" if is_income else "Otros"),
                        row["payment_method"], amount_text,
                    ),
                    tags=("income" if is_income else "expense",),
                )
            label_parts = []
            if self.table_month:
                label_parts.append(self._month_label(self.table_month))
            if self.selected_category:
                label_parts.append(self.selected_category)
            self.filter_label.configure(text=" · ".join(label_parts))
        except Exception as exc:
            messagebox.showerror("No se pudo cargar el resumen", str(exc), parent=self)

    @staticmethod
    def _month_label(month: str) -> str:
        names = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
        try:
            year, number = (int(part) for part in month.split("-"))
            return f"{names[number - 1].capitalize()} {year}"
        except (ValueError, IndexError):
            return month

    def backup(self):
        try:
            BACKUP_DIR.mkdir(parents=True, exist_ok=True)
            stamp = __import__('datetime').datetime.now().strftime('%Y%m%d_%H%M%S')
            destination = BACKUP_DIR / f"respaldo_{stamp}.zip"
            with tempfile.TemporaryDirectory() as temp_dir:
                temp_db = Path(temp_dir) / "gestor_financiero.sqlite3"
                source = connect()
                target = sqlite3.connect(temp_db)
                try:
                    source.backup(target)
                finally:
                    target.close()
                    source.close()
                with zipfile.ZipFile(destination, "w", compression=zipfile.ZIP_DEFLATED) as archive:
                    archive.write(temp_db, arcname="gestor_financiero.sqlite3")
                    if EVIDENCE_DIR.exists():
                        for file_path in EVIDENCE_DIR.rglob("*"):
                            if file_path.is_file():
                                archive.write(file_path, arcname=(Path("evidencias") / file_path.relative_to(EVIDENCE_DIR)).as_posix())
            messagebox.showinfo("Copia creada", f"La copia de seguridad incluye la base de datos y las evidencias:\n{destination}", parent=self)
        except Exception as exc:
            messagebox.showerror("Error de copia", str(exc), parent=self)


class MovementView(ttk.Frame):
    MONTHS = (
        "Enero", "Febrero", "Marzo", "Abril", "Mayo", "Junio",
        "Julio", "Agosto", "Septiembre", "Octubre", "Noviembre", "Diciembre",
    )
    CATEGORIES = (
        "Ingresos", "Hogar", "Comida", "Transporte", "Entretenimiento",
        "Salud", "Educación", "Servicios", "Compras", "Negocio", "Otros",
    )

    def __init__(self, parent, direction: str, title: str):
        super().__init__(parent, padding=18)
        self.direction = direction
        self.title = title
        self.last_rows = []
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text=title, style="Title.TLabel").pack(side="left")
        add_label = "Registrar ingreso" if direction == "income" else "Registrar gasto" if direction == "expense" else ""
        if add_label:
            ttk.Button(top, text=add_label, style="Accent.TButton", command=self.new_movement).pack(side="right")

        clients = list_clients(active_only=False)
        self.client_map = {"Todos los clientes": None}
        self.client_map.update({f'{c["id"]} — {c["name"]}': int(c["id"]) for c in clients})
        with get_connection() as connection:
            years = [str(row[0]) for row in connection.execute(
                "SELECT DISTINCT substr(payment_date,1,4) FROM movements ORDER BY 1 DESC"
            ).fetchall() if row[0]]
        year_values = sorted(set(years + [str(date.today().year)]), reverse=True)

        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=(14, 5))
        self.query_var = tk.StringVar()
        self.from_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.voucher_var = tk.StringVar()
        self.client_var = tk.StringVar(value="Todos los clientes")
        self.category_var = tk.StringVar(value="Todas las categorías")
        self.month_var = tk.StringVar(value="Todos los meses")
        self.year_var = tk.StringVar(value="Todos los años")

        row1 = ttk.Frame(filters)
        row1.pack(fill="x", pady=(0, 8))
        ttk.Label(row1, text="Buscar texto").grid(row=0, column=0, sticky="w")
        ttk.Entry(row1, textvariable=self.query_var, width=26).grid(row=1, column=0, padx=(0, 9), sticky="ew")
        ttk.Label(row1, text="Cliente").grid(row=0, column=1, sticky="w")
        self.client_box = ElegantCombobox(row1, textvariable=self.client_var, values=list(self.client_map), state="readonly", width=25)
        self.client_box.grid(row=1, column=1, padx=(0, 9), sticky="ew")
        ttk.Label(row1, text="Categoría").grid(row=0, column=2, sticky="w")
        category_values = ["Todas las categorías"] + list(self.CATEGORIES)
        self.category_box = ElegantCombobox(row1, textvariable=self.category_var, values=category_values, state="readonly", width=19)
        self.category_box.grid(row=1, column=2, padx=(0, 9), sticky="ew")
        ttk.Label(row1, text="N.º voucher").grid(row=0, column=3, sticky="w")
        ttk.Entry(row1, textvariable=self.voucher_var, width=17).grid(row=1, column=3, sticky="ew")
        row1.columnconfigure(0, weight=2)
        row1.columnconfigure(1, weight=2)
        row1.columnconfigure(2, weight=1)

        row2 = ttk.Frame(filters)
        row2.pack(fill="x")
        ttk.Label(row2, text="Desde").grid(row=0, column=0, sticky="w")
        DatePickerEntry(row2, textvariable=self.from_var, width=12).grid(row=1, column=0, padx=(0, 8), sticky="ew")
        ttk.Label(row2, text="Hasta").grid(row=0, column=1, sticky="w")
        DatePickerEntry(row2, textvariable=self.to_var, width=12).grid(row=1, column=1, padx=(0, 8), sticky="ew")
        ttk.Label(row2, text="Mes rápido").grid(row=0, column=2, sticky="w")
        month_values = ["Todos los meses"] + [f"{i:02d} - {name}" for i, name in enumerate(self.MONTHS, 1)]
        self.month_box = ElegantCombobox(row2, textvariable=self.month_var, values=month_values, state="readonly", width=17)
        self.month_box.grid(row=1, column=2, padx=(0, 8), sticky="ew")
        ttk.Label(row2, text="Año").grid(row=0, column=3, sticky="w")
        self.year_box = ElegantCombobox(row2, textvariable=self.year_var, values=["Todos los años"] + year_values, state="readonly", width=13)
        self.year_box.grid(row=1, column=3, padx=(0, 8), sticky="ew")
        ttk.Button(row2, text="Buscar", style="Accent.TButton", command=self.refresh).grid(row=1, column=4, padx=(0, 7))
        ttk.Button(row2, text="Limpiar", command=self.clear_filters).grid(row=1, column=5)

        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True, pady=(10, 0))
        columns = ("date", "registered", "type", "person", "reason", "category", "amount", "method", "voucher", "evidence", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "date": ("Fecha de pago", 100), "registered": ("Fecha de registro", 135),
            "type": ("Movimiento", 90), "person": ("Persona / empresa", 155),
            "reason": ("Motivo", 175), "category": ("Categoría", 115), "amount": ("Importe", 100),
            "method": ("Tipo de pago", 115), "voucher": ("Voucher", 115),
            "evidence": ("Evidencias", 75), "status": ("Estado", 85),
        }
        for key, (label, width) in headings.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=60, anchor="w" if key in ("person", "reason", "category") else "center")
        yscroll = ttk.Scrollbar(table_frame, orient="vertical", command=self.tree.yview)
        xscroll = ttk.Scrollbar(self, orient="horizontal", command=self.tree.xview)
        self.tree.configure(yscrollcommand=yscroll.set, xscrollcommand=xscroll.set)
        self.tree.pack(side="left", fill="both", expand=True)
        yscroll.pack(side="right", fill="y")
        xscroll.pack(fill="x")
        self.tree.tag_configure("void", foreground=palette_for(self)["muted"])
        self.tree.bind("<Double-1>", lambda _e: self.open_evidence())

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Abrir evidencia", command=self.open_evidence).pack(side="left")
        ttk.Button(actions, text="Anular movimiento…", command=self.void_selected).pack(side="left", padx=8)
        self.action_status_var = tk.StringVar(value="")
        self.action_status_label = ttk.Label(
            actions, textvariable=self.action_status_var, style="Hint.TLabel",
            anchor="w", wraplength=360,
        )
        self.action_status_label.pack(side="left", fill="x", expand=True, padx=(10, 6))
        ttk.Button(actions, text="Exportar resultados…", style="Accent.TButton", command=self.export).pack(side="right")
        ttk.Button(actions, text="Actualizar", command=self.refresh).pack(side="right", padx=8)
        self._status_clear_job = None
        self.refresh()

    def refresh_filter_options(self):
        selected = self.client_var.get()
        clients = list_clients(active_only=False)
        self.client_map = {"Todos los clientes": None}
        self.client_map.update({f'{c["id"]} — {c["name"]}': int(c["id"]) for c in clients})
        self.client_box.configure(values=list(self.client_map))
        self.client_var.set(selected if selected in self.client_map else "Todos los clientes")
        with get_connection() as connection:
            years = [str(row[0]) for row in connection.execute(
                "SELECT DISTINCT substr(payment_date,1,4) FROM movements ORDER BY 1 DESC"
            ).fetchall() if row[0]]
        years = sorted(set(years + [str(date.today().year)]), reverse=True)
        self.year_box.configure(values=["Todos los años"] + years)
        if self.year_var.get() not in ("Todos los años", *years):
            self.year_var.set("Todos los años")

    def new_movement(self):
        MovementDialog(self, self.direction, self.refresh)

    def _period_bounds(self):
        """Return a quick month/year interval, intersected with manual dates."""
        start = self.from_var.get().strip()
        end = self.to_var.get().strip()
        year_text = self.year_var.get()
        month_text = self.month_var.get()
        selected_year = int(year_text) if year_text != "Todos los años" else date.today().year
        if month_text != "Todos los meses":
            month = int(month_text.split(" - ", 1)[0])
            period_start = date(selected_year, month, 1)
            period_end = date(selected_year, month, calendar.monthrange(selected_year, month)[1])
            start = max(start, period_start.isoformat()) if start else period_start.isoformat()
            end = min(end, period_end.isoformat()) if end else period_end.isoformat()
        elif year_text != "Todos los años":
            period_start = date(selected_year, 1, 1).isoformat()
            period_end = date(selected_year, 12, 31).isoformat()
            start = max(start, period_start) if start else period_start
            end = min(end, period_end) if end else period_end
        if start and end and start > end:
            raise ValueError("El intervalo de fechas está vacío. Revisa los filtros Desde, Hasta, Mes y Año.")
        return start, end

    def _active_filters(self):
        date_from, date_to = self._period_bounds()
        selected_client = self.client_var.get()
        selected_category = self.category_var.get()
        return {
            "query": self.query_var.get().strip(),
            "direction": self.direction,
            "date_from": date_from,
            "date_to": date_to,
            "voucher": self.voucher_var.get().strip(),
            "client_id": self.client_map.get(selected_client),
            "category": "" if selected_category == "Todas las categorías" else selected_category,
            "include_void": True,
            "limit": 250000,
        }

    def _filter_description(self):
        filters = self._active_filters()
        client_label = self.client_var.get()
        category_label = self.category_var.get()
        return {
            "búsqueda": filters["query"] or "Todas",
            "tipo": self.title,
            "cliente": client_label,
            "categoría": category_label,
            "voucher": filters["voucher"] or "Todos",
            "desde": filters["date_from"] or "Sin límite",
            "hasta": filters["date_to"] or "Sin límite",
        }

    def clear_filters(self):
        self.query_var.set("")
        self.from_var.set("")
        self.to_var.set("")
        self.voucher_var.set("")
        self.client_var.set("Todos los clientes")
        self.category_var.set("Todas las categorías")
        self.month_var.set("Todos los meses")
        self.year_var.set("Todos los años")
        self.refresh()

    def refresh(self):
        try:
            filters = self._active_filters()
            rows = search_movements(**filters)
            self.last_rows = rows
            self.tree.delete(*self.tree.get_children())
            if rows:
                self.set_action_status(f"{len(rows):,} movimientos encontrados.", duration_ms=2200)
            else:
                self.set_action_status("No hay movimientos que coincidan con los filtros.", duration_ms=3600)
            for row in rows:
                state = "Anulado" if row["status"] == "void" else "Vigente"
                self.tree.insert("", "end", iid=str(row["id"]), values=(
                    row["payment_date"], row["registered_at"],
                    "Ingreso" if row["direction"] == "income" else "Gasto",
                    row["counterparty"], row["reason"], row.get("category") or "Otros",
                    format_money(row["amount_cents"]), row["payment_method"],
                    row["voucher_number"] or "—", row["evidence_count"], state,
                ), tags=("void",) if row["status"] == "void" else ())
        except Exception as exc:
            messagebox.showerror("Error de búsqueda", str(exc), parent=self)

    def set_action_status(self, text: str, duration_ms: int = 5200):
        """Show non-modal feedback so empty-result actions never block the UI."""
        self.action_status_var.set(text)
        job, self._status_clear_job = self._status_clear_job, None
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        if text:
            self._status_clear_job = self.after(duration_ms, lambda: self.action_status_var.set(""))

    def selected_id(self):
        selected = self.tree.selection()
        if not selected:
            self.set_action_status("Selecciona un movimiento de la lista para continuar.")
            return None
        return int(selected[0])

    def open_evidence(self):
        movement_id = self.selected_id()
        if movement_id is None:
            return
        with get_connection() as connection:
            rows = connection.execute("SELECT * FROM evidence_files WHERE movement_id=? ORDER BY id", (movement_id,)).fetchall()
        if not rows:
            self.set_action_status("Este movimiento no tiene evidencias adjuntas.")
            return
        if len(rows) == 1:
            self._open_path(evidence_absolute_path(rows[0]["relative_path"]))
            return
        dialog = PremiumWindow(self, "Evidencias del movimiento", "520x330")
        frame = ttk.Frame(dialog.body, padding=4)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Selecciona el archivo que deseas abrir:").pack(anchor="w", pady=(0, 10))
        p = palette_for(self)
        listing = tk.Listbox(frame, bg=p["panel"], fg=p["text"], selectbackground=p["selected"], selectforeground=p["text"], relief="flat", font=("Segoe UI", 9))
        listing.pack(fill="both", expand=True)
        for row in rows:
            listing.insert("end", row["original_name"])
        def open_selected():
            selection = listing.curselection()
            if not selection:
                return
            self._open_path(evidence_absolute_path(rows[selection[0]]["relative_path"]))
            dialog.destroy()
        ttk.Button(frame, text="Abrir archivo", style="Accent.TButton", command=open_selected).pack(anchor="e", pady=(10, 0))

    @staticmethod
    def _open_path(path: Path):
        if not path.exists():
            messagebox.showerror("Archivo no encontrado", f"No se encontró el archivo:\n{path}")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(str(path))
            elif sys.platform == "darwin":
                subprocess.Popen(["open", str(path)])
            else:
                subprocess.Popen(["xdg-open", str(path)])
        except Exception as exc:
            messagebox.showerror("No se pudo abrir", str(exc))

    def destroy(self):
        job, self._status_clear_job = getattr(self, "_status_clear_job", None), None
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        super().destroy()

    def void_selected(self):
        movement_id = self.selected_id()
        if movement_id is None:
            return
        dialog = PremiumWindow(self, "Anular movimiento", "470x240", modal=True)
        frame = ttk.Frame(dialog.body, padding=4)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Anular movimiento #{movement_id}", style="DialogTitle.TLabel").pack(anchor="w", pady=(0, 12))
        ttk.Label(frame, text="Motivo de anulación (obligatorio)").pack(anchor="w")
        reason = tk.StringVar()
        ttk.Entry(frame, textvariable=reason).pack(fill="x", pady=7)
        def confirm():
            try:
                if not messagebox.askyesno("Confirmar anulación", "El movimiento dejará de afectar los totales y las mensualidades. ¿Continuar?", parent=dialog):
                    return
                void_movement(movement_id, reason.get())
                dialog.destroy()
                self.refresh()
            except Exception as exc:
                messagebox.showerror("No se pudo anular", str(exc), parent=dialog)
        ttk.Button(frame, text="Anular movimiento", style="Accent.TButton", command=confirm).pack(anchor="e", pady=(8, 0))

    def export(self):
        # Do not open a modal confirmation or a native file dialog when there is
        # nothing to export. This is a common first-run state and must be instant.
        if not self.last_rows:
            self.set_action_status("No hay movimientos para exportar. Ajusta los filtros o registra un movimiento.")
            return
        extension_types = [
            ("PDF", "*.pdf"), ("Libro de Excel", "*.xlsx"),
            ("XML de datos", "*.xml"), ("Texto", "*.txt"),
            ("CSV compatible con Excel", "*.csv"),
        ]
        stamp = date.today().strftime("%Y%m%d")
        base_name = "ingresos" if self.direction == "income" else "gastos" if self.direction == "expense" else "movimientos"
        path = filedialog.asksaveasfilename(
            parent=self, title="Exportar resultados de la búsqueda",
            initialfile=f"{base_name}_{stamp}.pdf", defaultextension=".pdf",
            filetypes=extension_types,
        )
        if not path:
            return
        try:
            report = build_movement_report(self.last_rows, self._filter_description(), self.title)
            count = export_report(path, report)
            messagebox.showinfo("Exportación terminada", f"Se exportaron {count} movimientos.\n\nArchivo: {path}", parent=self)
        except Exception as exc:
            messagebox.showerror("Error al exportar", str(exc), parent=self)


class ClientView(ttk.Frame):
    def __init__(self, parent, refresh_callback):
        super().__init__(parent, padding=18)
        self.refresh_callback = refresh_callback
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Clientes", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="Nuevo cliente", style="Accent.TButton", command=self.new_client).pack(side="right")
        ttk.Button(top, text="Cambiar tarifa", command=self.change_rate).pack(side="right", padx=8)
        ttk.Label(self, text="Configura la mensualidad, consulta el estado del cliente y conserva el historial de tarifas.", style="SubTitle.TLabel").pack(anchor="w", pady=(4, 15))
        columns = ("name", "identification", "phone", "monthly", "first", "status")
        self.tree = ttk.Treeview(self, columns=columns, show="headings", selectmode="browse")
        for key, label, width in [
            ("name", "Cliente", 240), ("identification", "Identificación", 140),
            ("phone", "Teléfono", 140), ("monthly", "Tarifa actual", 120),
            ("first", "Primer cobro", 120), ("status", "Estado", 90),
        ]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="w" if key == "name" else "center")
        self.tree.pack(fill="both", expand=True)
        self.tree.bind("<Double-1>", lambda _e: self.change_rate())
        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Activar / desactivar cliente", command=self.toggle_active).pack(side="left")
        ttk.Button(actions, text="Actualizar", command=self.refresh).pack(side="right")
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        for client in list_clients():
            self.tree.insert("", "end", iid=str(client["id"]), values=(
                client["name"], client["identification"] or "—", client["phone"] or "—",
                format_money(client["current_rate_cents"]), client["first_billing_date"],
                "Activo" if client["is_active"] else "Inactivo",
            ))

    def selected_client(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Selecciona un cliente", "Selecciona un cliente de la lista.", parent=self)
            return None
        return int(selected[0])

    def new_client(self):
        ClientDialog(self, self.refresh_callback)

    def change_rate(self):
        if not self.tree.selection():
            messagebox.showwarning("Selecciona un cliente", "Selecciona un cliente antes de cambiar la tarifa.", parent=self)
            return
        selected_id = int(self.tree.selection()[0])
        RateDialog(self, self.refresh_callback, initial_client_id=selected_id)

    def toggle_active(self):
        client_id = self.selected_client()
        if client_id is None:
            return
        row = self.tree.item(str(client_id), "values")
        currently_active = row[-1] == "Activo"
        action = "desactivar" if currently_active else "activar"
        if messagebox.askyesno("Confirmar", f"¿Deseas {action} este cliente?", parent=self):
            set_client_active(client_id, not currently_active)
            self.refresh_callback()


class DebtView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=18)
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text="Mensualidades y deudas", style="Title.TLabel").pack(side="left")
        ttk.Button(top, text="Exportar todos", command=self.export_all).pack(side="right")
        ttk.Button(top, text="Exportar cliente", style="Accent.TButton", command=self.export_client).pack(side="right", padx=8)
        ttk.Button(top, text="Historial de pagos", command=self.open_payment_history).pack(side="right", padx=(0, 8))
        selectors = ttk.Frame(self)
        selectors.pack(fill="x", pady=(14, 12))
        ttk.Label(selectors, text="Cliente").pack(side="left")
        self.client_var = tk.StringVar()
        self.client_box = ElegantCombobox(selectors, textvariable=self.client_var, state="readonly", width=34)
        self.client_box.pack(side="left", padx=9)
        self.client_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Label(selectors, text="Fecha de corte").pack(side="left", padx=(10, 4))
        self.as_of_var = tk.StringVar(value=date.today().isoformat())
        DatePickerEntry(selectors, textvariable=self.as_of_var, width=12).pack(side="left")
        ttk.Button(selectors, text="Actualizar cuotas", command=self.refresh).pack(side="left", padx=9)
        self.client_map = {}
        self.summary_frame = ttk.Frame(self)
        self.summary_frame.pack(fill="x", pady=(0, 12))
        self.summary_labels = {}
        self._last_summary = None
        for key, label in [("received", "TOTAL RECIBIDO"), ("paid", "MESES CUBIERTOS"), ("overdue", "DEUDA VENCIDA"), ("pending", "PENDIENTE TOTAL"), ("advance", "ABONOS EN FUTUROS MESES")]:
            card = tk.Frame(self.summary_frame, bg=PANEL, padx=12, pady=12)
            card.pack(side="left", fill="both", expand=True, padx=(0, 7))
            tk.Label(card, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 7, "bold")).pack(anchor="w")
            value = tk.Label(card, text="—", bg=PANEL, fg=TEXT, font=("Segoe UI", 14, "bold"))
            value.pack(anchor="w", pady=(8, 0))
            self.summary_labels[key] = value
        columns = ("period", "due", "amount", "applied", "pending", "status")
        self.tree = ttk.Treeview(self, columns=columns, show="headings")
        for key, label, width in [
            ("period", "Período", 210), ("due", "Vencimiento", 130),
            ("amount", "Mensualidad", 130), ("applied", "Abonado", 130),
            ("pending", "Pendiente", 130), ("status", "Estado", 120),
        ]:
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, anchor="center")
        self.tree.pack(fill="both", expand=True)
        p = palette_for(self)
        self.tree.tag_configure("paid", foreground=p["success"])
        self.tree.tag_configure("late", foreground=p["danger"])
        self.tree.tag_configure("partial", foreground=p["expense"])
        self.refresh_clients()

    def apply_theme(self, palette):
        if self._last_summary is not None:
            overdue = int(self._last_summary.get("overdue_cents", 0))
            self.summary_labels["overdue"].configure(fg=palette["danger"] if overdue else palette["text"])

    def refresh_clients(self):
        clients = list_clients(active_only=True)
        old = self.client_var.get()
        self.client_map = {f'{c["id"]} — {c["name"]}': c for c in clients}
        self.client_box.configure(values=list(self.client_map))
        if old in self.client_map:
            self.client_var.set(old)
        elif self.client_map:
            self.client_var.set(next(iter(self.client_map)))
        else:
            self.client_var.set("")
        self.refresh()

    def refresh(self):
        self.tree.delete(*self.tree.get_children())
        key = self.client_var.get()
        client = self.client_map.get(key)
        if not client:
            for label in self.summary_labels.values():
                label.configure(text="—")
            return
        client_id = int(client["id"])
        try:
            as_of = self.as_of_var.get().strip() or date.today().isoformat()
            summary = client_debt_summary(client_id, as_of)
            self._last_summary = summary
            self.summary_labels["received"].configure(text=format_money(summary["total_received_cents"]))
            self.summary_labels["paid"].configure(text=str(summary["fully_paid_months"]))
            palette = palette_for(self)
            self.summary_labels["overdue"].configure(text=format_money(summary["overdue_cents"]), fg=palette["danger"] if summary["overdue_cents"] else palette["text"])
            self.summary_labels["pending"].configure(text=format_money(summary["pending_cents"]))
            self.summary_labels["advance"].configure(text=format_money(summary["future_applied_cents"]))
            charges = list_client_charges(client_id, as_of)
            for item in charges:
                due = int(item["amount_due_cents"])
                applied = int(item["applied_cents"])
                remaining = int(item["remaining_cents"])
                if remaining == 0:
                    status, tag = "Cubierto", "paid"
                elif applied > 0:
                    status, tag = "Abonado", "partial"
                elif item["due_date"] < as_of:
                    status, tag = "Vencido", "late"
                else:
                    status, tag = "Pendiente", ""
                self.tree.insert("", "end", values=(
                    f"{item['period_start']} a {item['period_end']}", item["due_date"],
                    format_money(due), format_money(applied), format_money(remaining), status,
                ), tags=(tag,) if tag else ())
        except Exception as exc:
            messagebox.showerror("Error al consultar mensualidades", str(exc), parent=self)

    def open_payment_history(self):
        key = self.client_var.get()
        client = self.client_map.get(key)
        if not client:
            messagebox.showwarning("Selecciona un cliente", "Selecciona un cliente para consultar su historial de pagos.", parent=self)
            return

        client_id = int(client["id"])
        as_of = self.as_of_var.get().strip() or date.today().isoformat()
        rows = client_payment_history(client_id, as_of)
        dialog = PremiumWindow(self, f"Historial de pagos · {client['name']}", "1120x520")
        frame = ttk.Frame(dialog.body, padding=4)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text=f"Historial de pagos · {client['name']}", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(frame, text=f"Fecha de corte: {as_of}. El importe recibido se muestra por separado del valor aplicado a mensualidades.", style="Hint.TLabel").pack(anchor="w", pady=(4, 12))
        columns = ("date", "registered", "amount", "applied", "unapplied", "method", "voucher", "evidence", "status", "reason")
        tree = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        definitions = [
            ("date", "Fecha pago", 95), ("registered", "Registrado", 135),
            ("amount", "Recibido", 100), ("applied", "Aplicado a cuotas", 120),
            ("unapplied", "No aplicado", 105), ("method", "Método", 105),
            ("voucher", "Voucher", 105), ("evidence", "Archivos", 65),
            ("status", "Estado", 80), ("reason", "Motivo", 190),
        ]
        for key_name, label, width in definitions:
            tree.heading(key_name, text=label)
            tree.column(key_name, width=width, minwidth=65, anchor="w" if key_name == "reason" else "center")
        tree.pack(fill="both", expand=True)
        tree.tag_configure("void", foreground=palette_for(dialog)["muted"])
        total_received = 0
        total_applied = 0
        for row in rows:
            is_void = row["status"] == "void"
            received = int(row["amount_cents"])
            applied = int(row["allocated_cents"]) if not is_void else 0
            total_received += received if not is_void else 0
            total_applied += applied
            tree.insert("", "end", iid=str(row["id"]), values=(
                row["payment_date"], row["registered_at"], format_money(received),
                format_money(applied), format_money(max(0, received - applied)),
                row["payment_method"], row["voucher_number"] or "—",
                row["evidence_count"], "Anulado" if is_void else "Vigente", row["reason"],
            ), tags=("void",) if is_void else ())
        footer = ttk.Frame(frame)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Label(footer, text=f"Total recibido vigente: {format_money(total_received)}    ·    Aplicado a mensualidades: {format_money(total_applied)}", style="SubTitle.TLabel").pack(side="left")
        ttk.Button(footer, text="Cerrar", command=dialog.destroy).pack(side="right")

    def _export_report(self, report, default_name):
        filetypes = [
            ("PDF", "*.pdf"), ("Libro de Excel", "*.xlsx"),
            ("XML de datos", "*.xml"), ("Texto", "*.txt"),
            ("CSV compatible con Excel", "*.csv"),
        ]
        path = filedialog.asksaveasfilename(
            parent=self, title="Exportar estado de cuenta", initialfile=default_name,
            defaultextension=".pdf", filetypes=filetypes,
        )
        if not path:
            return
        try:
            export_report(path, report)
            count = len(report.get("records", []))
            messagebox.showinfo("Exportación terminada", f"Se exportó el estado de cuenta.\nDetalle de períodos: {count}.\n\n{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("Error al exportar", str(exc), parent=self)

    def export_client(self):
        key = self.client_var.get()
        client = self.client_map.get(key)
        if not client:
            messagebox.showwarning("Selecciona un cliente", "Selecciona el cliente cuyo estado deseas exportar.", parent=self)
            return
        as_of = self.as_of_var.get().strip() or date.today().isoformat()
        report = build_debt_report(as_of, int(client["id"]))
        self._export_report(report, f"estado_cuenta_{client['id']}_{as_of}.pdf")

    def export_all(self):
        as_of = self.as_of_var.get().strip() or date.today().isoformat()
        report = build_debt_report(as_of)
        self._export_report(report, f"estados_de_cuenta_{as_of}.pdf")


def run_app():
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()
