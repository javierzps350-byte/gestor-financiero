import os
import sqlite3
import subprocess
import sys
import tempfile
import zipfile
import tkinter as tk
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from src.config import APP_NAME, BACKUP_DIR, EVIDENCE_DIR
from src.database.connection import connect
from src.domain.money import format_money
from src.services.finance_service import (
    client_debt_summary, client_payment_history, dashboard_visual_data,
    list_client_charges, list_clients, search_movements, set_client_active,
    void_movement,
)
from src.services.evidence_service import evidence_absolute_path
from src.services.report_service import export_debts_csv, export_movements_csv
from src.ui.dialogs import ClientDialog, MovementDialog, RateDialog
from src.ui.assistant_view import AssistantView
from src.ui.charts import MonthlyLineChart, ExpenseDonutChart, TEAL, CORAL

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
        self._nav_widgets = {}
        root.title(APP_NAME)
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        window_width = min(1440, max(960, screen_width - 40))
        window_height = min(920, max(680, screen_height - 60))
        root.geometry(f"{window_width}x{window_height}+20+15")
        root.minsize(min(940, window_width), min(660, window_height))
        root.configure(bg=BG)
        self._configure_style()
        self._build_shell()

    def _configure_style(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=BG)
        style.configure("Panel.TFrame", background=PANEL)
        style.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        style.configure("DialogTitle.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 19, "bold"))
        style.configure("Hint.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 21, "bold"))
        style.configure("SubTitle.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        style.configure("TButton", font=("Segoe UI", 9), padding=(13, 8), background=PANEL_ALT, foreground=TEXT, borderwidth=0)
        style.map("TButton", background=[("active", "#E4EDF4"), ("disabled", "#F0F3F6")], foreground=[("disabled", "#AAB4BF")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#FFFFFF", font=("Segoe UI", 9, "bold"), padding=(14, 9))
        style.map("Accent.TButton", background=[("active", "#239987")])
        style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT, bordercolor=BORDER, padding=9)
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=TEXT, arrowcolor=MUTED, padding=8)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", TEXT)])
        style.configure("TCheckbutton", background=BG, foreground=TEXT, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=31, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#F3F6F9", foreground="#657489", relief="flat", font=("Segoe UI", 8, "bold"), padding=(10, 10))
        style.map("Treeview", background=[("selected", "#D9F0EC")], foreground=[("selected", TEXT)])
        style.configure("TScrollbar", background="#E7EDF3", troughcolor=BG, bordercolor=BG, arrowcolor=MUTED)

    def _build_shell(self):
        top = tk.Frame(self.root, bg=WHITE, height=66, padx=28)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(top, text="Gestor Financiero", bg=WHITE, fg=TEXT, font=("Segoe UI", 16, "bold")).pack(side="left", anchor="center")
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)
        self.sidebar = tk.Frame(shell, bg=SIDEBAR, width=112, padx=8, pady=20, highlightthickness=1, highlightbackground=BORDER)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        for page_id, label in self.NAV_ITEMS:
            self._make_nav_button(page_id, label)

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
        row = tk.Frame(self.sidebar, bg=SIDEBAR, height=49)
        row.pack(fill="x", padx=1, pady=4)
        row.pack_propagate(False)
        indicator = tk.Frame(row, bg=SIDEBAR, width=3)
        indicator.pack(side="left", fill="y")
        button = tk.Button(
            row, text=label, anchor="center",
            bg=SIDEBAR, fg="#748398", activebackground="#EAF5F3",
            activeforeground=TEXT, relief="flat", bd=0,
            highlightthickness=0, font=("Segoe UI", 9),
            padx=4, pady=8, cursor="hand2",
            command=lambda key=page_id: self.show_page(key),
        )
        button.pack(side="left", fill="both", expand=True)
        button.bind("<Enter>", lambda _e, key=page_id: self._nav_hover(key, True))
        button.bind("<Leave>", lambda _e, key=page_id: self._nav_hover(key, False))
        self._nav_widgets[page_id] = (row, indicator, button)

    def _nav_hover(self, page_id, hovered):
        if page_id == self.current_page:
            return
        row, _indicator, button = self._nav_widgets[page_id]
        color = "#F1F7F6" if hovered else SIDEBAR
        row.configure(bg=color)
        button.configure(bg=color)

    def _set_nav_active(self, page_id):
        for key, (row, indicator, button) in self._nav_widgets.items():
            active = key == page_id
            bg = "#E5F4F1" if active else SIDEBAR
            row.configure(bg=bg)
            indicator.configure(bg=ACCENT if active else SIDEBAR)
            button.configure(
                bg=bg,
                fg="#208E80" if active else "#748398",
                font=("Segoe UI", 10, "bold" if active else "normal"),
            )

    def show_page(self, page_id, animate=True):
        if page_id not in self.pages:
            return
        if page_id == self.current_page:
            return
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
                self.root.after(duration_ms, lambda: animate_step(step + 1))
            else:
                new_page.place_configure(x=0)

        animate_step()

    def refresh_all(self):
        self.dashboard.refresh()
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
        self._animation_ids = {}
        self._build()

    def _panel(self, parent, **kwargs):
        return tk.Frame(parent, bg=PANEL, highlightthickness=1, highlightbackground=BORDER, **kwargs)

    def _build(self):
        heading = tk.Frame(self, bg=BG)
        heading.pack(fill="x", pady=(0, 9))
        title_block = tk.Frame(heading, bg=BG)
        title_block.pack(side="left", fill="x", expand=True)
        tk.Label(title_block, text="Hola, bienvenido", bg=BG, fg=TEXT, font=("Segoe UI", 19, "bold")).pack(anchor="w")
        tk.Label(title_block, text="Este es el resumen de tu actividad financiera.", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(3, 0))
        weekday_names = ("lunes", "martes", "miércoles", "jueves", "viernes", "sábado", "domingo")
        month_names = ("enero", "febrero", "marzo", "abril", "mayo", "junio", "julio", "agosto", "septiembre", "octubre", "noviembre", "diciembre")
        today = date.today()
        date_label = f"{weekday_names[today.weekday()].capitalize()}, {today.day} de {month_names[today.month - 1]} de {today.year}"
        tk.Label(heading, text=date_label, bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(side="right", anchor="e", pady=(10, 0))

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
        self.recent_tree.tag_configure("income", foreground="#208F7E")
        self.recent_tree.tag_configure("expense", foreground="#D9776B")
        self.recent_tree.tag_configure("void", foreground="#A5AFBA")


    @staticmethod
    def _action_button(parent, text, command, color):
        button = tk.Button(
            parent, text=text, command=command, anchor="center",
            bg=color, fg=WHITE, activebackground=color, activeforeground=WHITE,
            relief="flat", bd=0, highlightthickness=0,
            padx=17, pady=10, font=("Segoe UI", 9, "bold"), cursor="hand2",
        )
        hover = "#238F80" if color == TEAL else "#D9786D"
        button.bind("<Enter>", lambda _event: button.configure(bg=hover))
        button.bind("<Leave>", lambda _event: button.configure(bg=color))
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
            targets = {
                "balance": (data["balance_cents"], "#314D64" if data["balance_cents"] >= 0 else RED),
                "income": (data["income_month_cents"], TEAL),
                "expenses": (data["expenses_month_cents"], CORAL),
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
    def __init__(self, parent, direction: str, title: str):
        super().__init__(parent, padding=18)
        self.direction = direction
        self.title = title
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text=title, style="Title.TLabel").pack(side="left")
        add_label = "Registrar ingreso" if direction == "income" else "Registrar gasto" if direction == "expense" else ""
        if add_label:
            ttk.Button(top, text=add_label, style="Accent.TButton", command=self.new_movement).pack(side="right")

        filters = ttk.Frame(self)
        filters.pack(fill="x", pady=(14, 12))
        self.query_var = tk.StringVar()
        self.from_var = tk.StringVar()
        self.to_var = tk.StringVar()
        self.voucher_var = tk.StringVar()
        ttk.Label(filters, text="Buscar").grid(row=0, column=0, sticky="w")
        ttk.Entry(filters, textvariable=self.query_var, width=29).grid(row=1, column=0, padx=(0, 9), sticky="ew")
        ttk.Label(filters, text="Desde (AAAA-MM-DD)").grid(row=0, column=1, sticky="w")
        ttk.Entry(filters, textvariable=self.from_var, width=17).grid(row=1, column=1, padx=(0, 9), sticky="ew")
        ttk.Label(filters, text="Hasta (AAAA-MM-DD)").grid(row=0, column=2, sticky="w")
        ttk.Entry(filters, textvariable=self.to_var, width=17).grid(row=1, column=2, padx=(0, 9), sticky="ew")
        ttk.Label(filters, text="N.º voucher").grid(row=0, column=3, sticky="w")
        ttk.Entry(filters, textvariable=self.voucher_var, width=17).grid(row=1, column=3, padx=(0, 9), sticky="ew")
        ttk.Button(filters, text="Buscar", command=self.refresh).grid(row=1, column=4, padx=(0, 7))
        ttk.Button(filters, text="Limpiar", command=self.clear_filters).grid(row=1, column=5)
        filters.columnconfigure(0, weight=1)

        table_frame = ttk.Frame(self)
        table_frame.pack(fill="both", expand=True)
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
        self.tree.tag_configure("void", foreground="#8995A7")
        self.tree.bind("<Double-1>", lambda _e: self.open_evidence())

        actions = ttk.Frame(self)
        actions.pack(fill="x", pady=(12, 0))
        ttk.Button(actions, text="Abrir evidencia", command=self.open_evidence).pack(side="left")
        ttk.Button(actions, text="Anular movimiento…", command=self.void_selected).pack(side="left", padx=8)
        ttk.Button(actions, text="Exportar CSV", command=self.export).pack(side="right")
        ttk.Button(actions, text="Actualizar", command=self.refresh).pack(side="right", padx=8)
        self.refresh()

    def new_movement(self):
        MovementDialog(self, self.direction, self.refresh)

    def clear_filters(self):
        self.query_var.set("")
        self.from_var.set("")
        self.to_var.set("")
        self.voucher_var.set("")
        self.refresh()

    def refresh(self):
        try:
            rows = search_movements(
                query=self.query_var.get(), direction=self.direction,
                date_from=self.from_var.get(), date_to=self.to_var.get(),
                voucher=self.voucher_var.get(), include_void=True,
            )
            self.tree.delete(*self.tree.get_children())
            for row in rows:
                state = "Anulado" if row["status"] == "void" else "Vigente"
                amount_prefix = "Ingreso" if row["direction"] == "income" else "Gasto"
                self.tree.insert("", "end", iid=str(row["id"]), values=(
                    row["payment_date"], row["registered_at"],
                    "Ingreso" if row["direction"] == "income" else "Gasto",
                    row["counterparty"], row["reason"], row.get("category") or "Otros",
                    format_money(row["amount_cents"]), row["payment_method"],
                    row["voucher_number"] or "—", row["evidence_count"], state,
                ), tags=("void",) if row["status"] == "void" else ())
        except Exception as exc:
            messagebox.showerror("Error de búsqueda", str(exc), parent=self)

    def selected_id(self):
        selected = self.tree.selection()
        if not selected:
            messagebox.showwarning("Selecciona un movimiento", "Primero selecciona un movimiento de la lista.", parent=self)
            return None
        return int(selected[0])

    def open_evidence(self):
        movement_id = self.selected_id()
        if movement_id is None:
            return
        with connect() as connection:
            rows = connection.execute("SELECT * FROM evidence_files WHERE movement_id=? ORDER BY id", (movement_id,)).fetchall()
        if not rows:
            messagebox.showinfo("Sin evidencias", "Este movimiento no tiene archivos adjuntos.", parent=self)
            return
        if len(rows) == 1:
            self._open_path(evidence_absolute_path(rows[0]["relative_path"]))
            return
        dialog = tk.Toplevel(self)
        dialog.title("Evidencias del movimiento")
        dialog.geometry("520x330")
        dialog.configure(bg=BG)
        dialog.transient(self)
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Selecciona el archivo que deseas abrir:").pack(anchor="w", pady=(0, 10))
        listing = tk.Listbox(frame, bg=PANEL, fg=TEXT, selectbackground="#D9F0EC", relief="flat", font=("Segoe UI", 9))
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

    def void_selected(self):
        movement_id = self.selected_id()
        if movement_id is None:
            return
        dialog = tk.Toplevel(self)
        dialog.title("Anular movimiento")
        dialog.geometry("470x220")
        dialog.configure(bg=BG)
        dialog.transient(self)
        dialog.grab_set()
        frame = ttk.Frame(dialog, padding=20)
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
        path = filedialog.asksaveasfilename(parent=self, title="Exportar movimientos", defaultextension=".csv", initialfile="movimientos.csv", filetypes=[("CSV compatible con Excel", "*.csv")])
        if not path:
            return
        try:
            count = export_movements_csv(path, query=self.query_var.get(), direction=self.direction,
                                         date_from=self.from_var.get(), date_to=self.to_var.get(),
                                         voucher=self.voucher_var.get())
            messagebox.showinfo("Exportación terminada", f"Se exportaron {count} movimientos.\n\n{path}", parent=self)
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
        ttk.Button(top, text="Exportar estado de cuentas", command=self.export).pack(side="right")
        ttk.Button(top, text="Historial de pagos", command=self.open_payment_history).pack(side="right", padx=(0, 8))
        selectors = ttk.Frame(self)
        selectors.pack(fill="x", pady=(14, 12))
        ttk.Label(selectors, text="Cliente").pack(side="left")
        self.client_var = tk.StringVar()
        self.client_box = ttk.Combobox(selectors, textvariable=self.client_var, state="readonly", width=42)
        self.client_box.pack(side="left", padx=9)
        self.client_box.bind("<<ComboboxSelected>>", lambda _e: self.refresh())
        ttk.Button(selectors, text="Actualizar cuotas", command=self.refresh).pack(side="left")
        self.client_map = {}
        self.summary_frame = ttk.Frame(self)
        self.summary_frame.pack(fill="x", pady=(0, 12))
        self.summary_labels = {}
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
        self.tree.tag_configure("paid", foreground=GREEN)
        self.tree.tag_configure("late", foreground=RED)
        self.tree.tag_configure("partial", foreground="#E8BA68")
        self.refresh_clients()

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
            summary = client_debt_summary(client_id)
            self.summary_labels["received"].configure(text=format_money(summary["total_received_cents"]))
            self.summary_labels["paid"].configure(text=str(summary["fully_paid_months"]))
            self.summary_labels["overdue"].configure(text=format_money(summary["overdue_cents"]), fg=RED if summary["overdue_cents"] else TEXT)
            self.summary_labels["pending"].configure(text=format_money(summary["pending_cents"]))
            self.summary_labels["advance"].configure(text=format_money(summary["future_applied_cents"]))
            charges = list_client_charges(client_id)
            today = date.today().isoformat()
            for item in charges:
                due = int(item["amount_due_cents"])
                applied = int(item["applied_cents"])
                remaining = int(item["remaining_cents"])
                if remaining == 0:
                    status, tag = "Cubierto", "paid"
                elif applied > 0:
                    status, tag = "Abonado", "partial"
                elif item["due_date"] < today:
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
        rows = client_payment_history(client_id)
        dialog = tk.Toplevel(self)
        dialog.title(f"Historial de pagos · {client['name']}")
        dialog.geometry("1120x520")
        dialog.minsize(900, 420)
        dialog.configure(bg=BG)
        dialog.transient(self)
        frame = ttk.Frame(dialog, padding=18)
        frame.pack(fill="both", expand=True)

        ttk.Label(frame, text=f"Historial de pagos · {client['name']}", style="DialogTitle.TLabel").pack(anchor="w")
        ttk.Label(
            frame,
            text="El importe recibido se muestra por separado del valor aplicado a mensualidades.",
            style="Hint.TLabel",
        ).pack(anchor="w", pady=(4, 12))

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
        tree.tag_configure("void", foreground="#8995A7")

        total_received = 0
        total_applied = 0
        for row in rows:
            is_void = row["status"] == "void"
            received = int(row["amount_cents"])
            applied = int(row["allocated_cents"]) if not is_void else 0
            total_received += received if not is_void else 0
            total_applied += applied
            tree.insert(
                "", "end", iid=str(row["id"]),
                values=(
                    row["payment_date"], row["registered_at"], format_money(received),
                    format_money(applied), format_money(max(0, received - applied)),
                    row["payment_method"], row["voucher_number"] or "—",
                    row["evidence_count"], "Anulado" if is_void else "Vigente", row["reason"],
                ),
                tags=("void",) if is_void else (),
            )

        footer = ttk.Frame(frame)
        footer.pack(fill="x", pady=(12, 0))
        ttk.Label(
            footer,
            text=f"Total recibido vigente: {format_money(total_received)}    ·    Aplicado a mensualidades: {format_money(total_applied)}",
            style="SubTitle.TLabel",
        ).pack(side="left")
        ttk.Button(footer, text="Cerrar", command=dialog.destroy).pack(side="right")

    def export(self):
        path = filedialog.asksaveasfilename(parent=self, title="Exportar estados de cuenta", defaultextension=".csv", initialfile="estados_de_cuenta.csv", filetypes=[("CSV compatible con Excel", "*.csv")])
        if not path:
            return
        try:
            count = export_debts_csv(path)
            messagebox.showinfo("Exportación terminada", f"Se exportaron {count} clientes.\n\n{path}", parent=self)
        except Exception as exc:
            messagebox.showerror("Error al exportar", str(exc), parent=self)


def run_app():
    root = tk.Tk()
    MainWindow(root)
    root.mainloop()
