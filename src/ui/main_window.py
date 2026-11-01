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

from src.config import APP_NAME, APP_VERSION, BACKUP_DIR, DB_PATH, EVIDENCE_DIR
from src.database.connection import connect
from src.domain.money import format_money
from src.services.finance_service import (
    client_debt_summary, client_payment_history, dashboard_summary,
    list_client_charges, list_clients, search_movements, set_client_active,
    void_movement,
)
from src.services.evidence_service import evidence_absolute_path
from src.services.report_service import export_debts_csv, export_movements_csv
from src.ui.dialogs import ClientDialog, MovementDialog, RateDialog
from src.ui.assistant_view import AssistantView

BG = "#0D1523"
PANEL = "#172235"
PANEL_ALT = "#1C2A40"
TEXT = "#E8EEF7"
MUTED = "#9AAAC0"
ACCENT = "#35A7E8"
GREEN = "#43C59E"
RED = "#F07178"


class MainWindow:
    """Main application shell with lightweight animated page navigation."""

    NAV_ITEMS = [
        ("dashboard", "⌂", "Inicio"),
        ("incomes", "↗", "Ingresos"),
        ("expenses", "↙", "Gastos"),
        ("clients", "♙", "Clientes"),
        ("debts", "◷", "Mensualidades"),
        ("search", "⌕", "Buscador"),
        ("assistant", "✦", "Asistente"),
    ]

    PAGE_META = {
        "dashboard": ("Resumen general", "Tu actividad financiera en un solo lugar."),
        "incomes": ("Ingresos", "Pagos recibidos, comprobantes y movimientos."),
        "expenses": ("Gastos", "Pagos realizados y control de salidas."),
        "clients": ("Clientes", "Tarifas, datos y seguimiento de cada cliente."),
        "debts": ("Mensualidades", "Cuotas, abonos y saldos pendientes."),
        "search": ("Buscador", "Encuentra movimientos por persona, fecha o voucher."),
        "assistant": ("Asistente", "Consultas rápidas mediante texto o voz opcional."),
    }

    def __init__(self, root: tk.Tk):
        self.root = root
        self.current_page = None
        self._transition_token = 0
        self._nav_widgets = {}
        root.title(f"{APP_NAME} · {APP_VERSION}")
        screen_width = root.winfo_screenwidth()
        screen_height = root.winfo_screenheight()
        window_width = min(1280, max(980, screen_width - 60))
        window_height = min(820, max(660, screen_height - 80))
        root.geometry(f"{window_width}x{window_height}+30+25")
        root.minsize(min(980, window_width), min(660, window_height))
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
        style.configure("SubTitle.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 10))
        style.configure("TButton", font=("Segoe UI", 9), padding=(12, 7), background=PANEL_ALT, foreground=TEXT, borderwidth=0)
        style.map("TButton", background=[("active", "#2A3D59"), ("disabled", "#202A38")], foreground=[("disabled", "#65758A")])
        style.configure("Accent.TButton", background=ACCENT, foreground="#071522", font=("Segoe UI", 9, "bold"))
        style.map("Accent.TButton", background=[("active", "#67C3F2")])
        style.configure("TEntry", fieldbackground=PANEL, foreground=TEXT, insertcolor=TEXT, bordercolor="#2B3C55", padding=8)
        style.configure("TCombobox", fieldbackground=PANEL, background=PANEL, foreground=TEXT, arrowcolor=TEXT, padding=7)
        style.map("TCombobox", fieldbackground=[("readonly", PANEL)], foreground=[("readonly", TEXT)])
        style.configure("TCheckbutton", background=BG, foreground=TEXT)
        style.configure("Treeview", background=PANEL, fieldbackground=PANEL, foreground=TEXT, rowheight=34, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background=PANEL_ALT, foreground=TEXT, relief="flat", font=("Segoe UI", 9, "bold"), padding=10)
        style.map("Treeview", background=[("selected", "#244B70")], foreground=[("selected", "#FFFFFF")])
        style.configure("TScrollbar", background=PANEL, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED)

    def _build_shell(self):
        # Compact application header.
        top = tk.Frame(self.root, bg="#101B2C", height=76, padx=24)
        top.pack(fill="x")
        top.pack_propagate(False)

        mark = tk.Frame(top, bg=ACCENT, width=42, height=42)
        mark.pack(side="left", pady=16)
        mark.pack_propagate(False)
        tk.Label(mark, text="GF", bg=ACCENT, fg="#071522", font=("Segoe UI", 14, "bold")).pack(expand=True)

        brand = tk.Frame(top, bg="#101B2C")
        brand.pack(side="left", padx=(12, 0), pady=14)
        tk.Label(brand, text="GESTOR FINANCIERO", bg="#101B2C", fg=TEXT, font=("Segoe UI", 13, "bold")).pack(anchor="w")
        tk.Label(brand, text="CONTROL LOCAL · INGRESOS · GASTOS · MENSUALIDADES", bg="#101B2C", fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(2, 0))

        right = tk.Frame(top, bg="#101B2C")
        right.pack(side="right", pady=19)
        local_pill = tk.Frame(right, bg="#18372F", padx=10, pady=6)
        local_pill.pack(side="left", padx=(0, 12))
        tk.Label(local_pill, text="●  LOCAL Y PRIVADO", bg="#18372F", fg="#72D9B3", font=("Segoe UI", 8, "bold")).pack()
        tk.Label(right, text=f"v{APP_VERSION}", bg="#101B2C", fg=MUTED, font=("Segoe UI", 9)).pack(side="left")

        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)

        # Left navigation rail.
        self.sidebar = tk.Frame(shell, bg="#111D2E", width=218, padx=10, pady=18)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)
        tk.Label(self.sidebar, text="ESPACIO DE TRABAJO", bg="#111D2E", fg="#71849F", font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=13, pady=(5, 12))

        for page_id, symbol, label in self.NAV_ITEMS:
            self._make_nav_button(page_id, symbol, label)

        spacer = tk.Frame(self.sidebar, bg="#111D2E")
        spacer.pack(fill="both", expand=True)
        divider = tk.Frame(self.sidebar, bg="#26364D", height=1)
        divider.pack(fill="x", padx=10, pady=(8, 12))
        tk.Label(self.sidebar, text="●  DATOS EN ESTE EQUIPO", bg="#111D2E", fg="#70C9A8", font=("Segoe UI", 8, "bold")).pack(anchor="w", padx=13)
        tk.Label(self.sidebar, text="No requiere conexión\na Internet para operar.", bg="#111D2E", fg=MUTED, font=("Segoe UI", 8), justify="left").pack(anchor="w", padx=13, pady=(6, 4))

        # Main work area and slim page toolbar.
        work = tk.Frame(shell, bg=BG)
        work.pack(side="left", fill="both", expand=True)
        self.page_toolbar = tk.Frame(work, bg=BG, padx=24, pady=13, height=48)
        self.page_toolbar.pack(fill="x")
        self.page_toolbar.pack_propagate(False)
        self.breadcrumb = tk.Label(self.page_toolbar, text="INICIO  /  RESUMEN", bg=BG, fg="#8293AA", font=("Segoe UI", 8, "bold"))
        self.breadcrumb.pack(side="left", anchor="center")
        self.page_hint = tk.Label(self.page_toolbar, text="", bg=BG, fg=MUTED, font=("Segoe UI", 8))
        self.page_hint.pack(side="right", anchor="center")

        self.page_host = tk.Frame(work, bg=BG)
        self.page_host.pack(fill="both", expand=True, padx=(8, 18), pady=(0, 14))

        self.dashboard = DashboardView(self.page_host, self.refresh_all)
        self.incomes = MovementView(self.page_host, "income", "Ingresos")
        self.expenses = MovementView(self.page_host, "expense", "Gastos")
        self.clients = ClientView(self.page_host, self.refresh_all)
        self.debts = DebtView(self.page_host)
        self.search = MovementView(self.page_host, "all", "Buscador")
        self.assistant = AssistantView(self.page_host)
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

    def _make_nav_button(self, page_id, symbol, label):
        row = tk.Frame(self.sidebar, bg="#111D2E", height=44)
        row.pack(fill="x", padx=3, pady=3)
        row.pack_propagate(False)
        indicator = tk.Frame(row, bg="#111D2E", width=3)
        indicator.pack(side="left", fill="y")
        button = tk.Button(
            row, text=f"{symbol}    {label}", anchor="w",
            bg="#111D2E", fg="#A8B6C9", activebackground="#203550",
            activeforeground=TEXT, relief="flat", bd=0,
            highlightthickness=0, font=("Segoe UI", 10),
            padx=13, pady=9, cursor="hand2",
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
        color = "#192A40" if hovered else "#111D2E"
        row.configure(bg=color)
        button.configure(bg=color)

    def _set_nav_active(self, page_id):
        for key, (row, indicator, button) in self._nav_widgets.items():
            active = key == page_id
            bg = "#203550" if active else "#111D2E"
            row.configure(bg=bg)
            indicator.configure(bg=ACCENT if active else "#111D2E")
            button.configure(
                bg=bg,
                fg="#FFFFFF" if active else "#A8B6C9",
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
        title, hint = self.PAGE_META[page_id]
        self.breadcrumb.configure(text=f"GESTOR FINANCIERO  /  {title.upper()}")
        self.page_hint.configure(text=hint)

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
    def __init__(self, parent, refresh_callback):
        super().__init__(parent, padding=20)
        self.refresh_callback = refresh_callback
        self._shown_values = {key: 0 for key in ("income", "expenses", "net", "overdue")}
        self._animation_ids = {}

        heading = tk.Frame(self, bg=BG)
        heading.pack(fill="x", pady=(0, 18))
        title_box = tk.Frame(heading, bg=BG)
        title_box.pack(side="left")
        tk.Label(title_box, text="Resumen general", bg=BG, fg=TEXT, font=("Segoe UI", 22, "bold")).pack(anchor="w")
        tk.Label(title_box, text="Una vista clara de tus ingresos, gastos y cuentas pendientes.", bg=BG, fg=MUTED, font=("Segoe UI", 9)).pack(anchor="w", pady=(4, 0))
        live = tk.Frame(heading, bg="#18372F", padx=11, pady=7)
        live.pack(side="right", anchor="center", pady=(4, 0))
        tk.Label(live, text="●  RESUMEN ACTUALIZADO", bg="#18372F", fg="#72D9B3", font=("Segoe UI", 8, "bold")).pack()

        self.cards = tk.Frame(self, bg=BG)
        self.cards.pack(fill="x")
        self.card_values = {}
        card_specs = [
            ("income", "INGRESOS DEL MES", "↗", GREEN, "Dinero recibido"),
            ("expenses", "GASTOS DEL MES", "↙", RED, "Dinero pagado"),
            ("net", "BALANCE DEL MES", "＝", ACCENT, "Ingresos menos gastos"),
            ("overdue", "DEUDA VENCIDA", "◷", "#E8B86D", "Cuotas fuera de fecha"),
        ]
        for index, (key, label, symbol, color, caption) in enumerate(card_specs):
            card = tk.Frame(self.cards, bg=PANEL, padx=16, pady=14, highlightthickness=1, highlightbackground="#293A52")
            card.grid(row=0, column=index, sticky="nsew", padx=(0 if index == 0 else 7, 0 if index == 3 else 7))
            self.cards.grid_columnconfigure(index, weight=1, uniform="summary")
            tk.Frame(card, bg=color, height=3).pack(fill="x", side="top", pady=(0, 12))
            top = tk.Frame(card, bg=PANEL)
            top.pack(fill="x")
            tk.Label(top, text=label, bg=PANEL, fg=MUTED, font=("Segoe UI", 7, "bold")).pack(side="left", anchor="w")
            icon = tk.Label(top, text=symbol, bg="#22334A", fg=color, font=("Segoe UI Symbol", 12, "bold"), width=2, pady=2)
            icon.pack(side="right")
            value = tk.Label(card, text="$0,00", bg=PANEL, fg=TEXT, font=("Segoe UI", 18, "bold"))
            value.pack(anchor="w", pady=(11, 3))
            tk.Label(card, text=caption, bg=PANEL, fg="#7F91A9", font=("Segoe UI", 8)).pack(anchor="w")
            self.card_values[key] = value

        lower = tk.Frame(self, bg=BG)
        lower.pack(fill="both", expand=True, pady=(18, 0))
        activity = tk.Frame(lower, bg=PANEL, padx=19, pady=18, highlightthickness=1, highlightbackground="#293A52")
        activity.pack(side="left", fill="both", expand=True)
        activity_top = tk.Frame(activity, bg=PANEL)
        activity_top.pack(fill="x")
        tk.Label(activity_top, text="ACTIVIDAD FINANCIERA", bg=PANEL, fg=TEXT, font=("Segoe UI", 10, "bold")).pack(side="left")
        tk.Label(activity_top, text="VISTA GENERAL", bg="#22334A", fg="#9CB2CC", font=("Segoe UI", 7, "bold"), padx=8, pady=4).pack(side="right")
        self.activity_label = tk.Label(activity, text="", bg=PANEL, fg=MUTED, font=("Segoe UI", 10), justify="left", anchor="nw", wraplength=610)
        self.activity_label.pack(fill="both", expand=True, anchor="nw", pady=(17, 10))

        actions = tk.Frame(lower, bg=BG, width=218, padx=15)
        actions.pack(side="right", fill="y")
        actions.pack_propagate(False)
        tk.Label(actions, text="ACCIONES RÁPIDAS", bg=BG, fg=MUTED, font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(4, 11))
        self._action_button(actions, "＋  Registrar ingreso", lambda: self._new("income"), primary=True).pack(fill="x", pady=4)
        self._action_button(actions, "＋  Registrar gasto", lambda: self._new("expense")).pack(fill="x", pady=4)
        self._action_button(actions, "＋  Nuevo cliente", self._new_client).pack(fill="x", pady=4)
        tk.Frame(actions, bg="#26364D", height=1).pack(fill="x", pady=13)
        self._action_button(actions, "▣  Copia de seguridad", self.backup).pack(fill="x", pady=4)
        self._action_button(actions, "⟳  Actualizar resumen", self.refresh).pack(fill="x", pady=4)

        footer = tk.Frame(self, bg=BG)
        footer.pack(fill="x", pady=(12, 0))
        tk.Label(footer, text="Los importes se guardan en centavos enteros para mantener la precisión.", bg=BG, fg="#71849C", font=("Segoe UI", 8)).pack(side="left")
        tk.Label(footer, text="ALMACENAMIENTO LOCAL", bg=BG, fg="#71849C", font=("Segoe UI", 8, "bold")).pack(side="right")

    @staticmethod
    def _action_button(parent, text, command, primary=False):
        bg = ACCENT if primary else PANEL_ALT
        fg = "#071522" if primary else TEXT
        hover = "#67C3F2" if primary else "#2A3F5B"
        button = tk.Button(
            parent, text=text, command=command, anchor="w",
            bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
            relief="flat", bd=0, highlightthickness=0,
            padx=12, pady=11, font=("Segoe UI", 9, "bold" if primary else "normal"),
            cursor="hand2",
        )
        button.bind("<Enter>", lambda _e: button.configure(bg=hover))
        button.bind("<Leave>", lambda _e: button.configure(bg=bg))
        return button

    def _new(self, direction):
        MovementDialog(self, direction, self.refresh_callback)

    def _new_client(self):
        ClientDialog(self, self.refresh_callback)

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

    def _animate_card(self, key, target_cents, color):
        previous_after = self._animation_ids.pop(key, None)
        if previous_after is not None:
            try:
                self.after_cancel(previous_after)
            except tk.TclError:
                pass
        start = self._shown_values.get(key, 0)
        steps = 12

        def tick(step=1):
            value = int(start + (target_cents - start) * step / steps)
            self.card_values[key].configure(text=format_money(value), fg=color)
            self._shown_values[key] = value
            if step < steps:
                self._animation_ids[key] = self.after(16, lambda: tick(step + 1))
            else:
                self._animation_ids.pop(key, None)
                self._shown_values[key] = target_cents

        tick()

    def refresh(self):
        try:
            summary = dashboard_summary()
            targets = {
                "income": (summary["income_month_cents"], GREEN),
                "expenses": (summary["expenses_month_cents"], RED),
                "net": (summary["net_month_cents"], TEXT),
                "overdue": (summary["overdue_total_cents"], "#E8B86D" if summary["overdue_total_cents"] else TEXT),
            }
            for key, (amount, color) in targets.items():
                self._animate_card(key, int(amount), color)
            self.activity_label.configure(text=(
                f"Clientes activos:  {summary['active_clients']}\n\n"
                f"Clientes con mensualidades generadas vencidas:  {summary['clients_with_due_charges']}\n\n"
                f"Ingresos del mes:  {format_money(summary['income_month_cents'])}\n"
                f"Gastos del mes:  {format_money(summary['expenses_month_cents'])}\n"
                f"Diferencia:  {format_money(summary['net_month_cents'])}\n\n"
                "CONSEJO\n"
                "Al registrar un ingreso de mensualidad, vincúlalo al cliente y activa "
                "'Aplicar este ingreso a las mensualidades' para distribuirlo automáticamente."
            ))
        except Exception as exc:
            self.activity_label.configure(text=f"No se pudo cargar el resumen: {exc}")


class MovementView(ttk.Frame):
    def __init__(self, parent, direction: str, title: str):
        super().__init__(parent, padding=18)
        self.direction = direction
        self.title = title
        top = ttk.Frame(self)
        top.pack(fill="x")
        ttk.Label(top, text=title, style="Title.TLabel").pack(side="left")
        add_label = "＋ Registrar ingreso" if direction == "income" else "＋ Registrar gasto" if direction == "expense" else ""
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
        columns = ("date", "registered", "type", "person", "reason", "amount", "method", "voucher", "evidence", "status")
        self.tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        headings = {
            "date": ("Fecha de pago", 100), "registered": ("Fecha de registro", 135),
            "type": ("Movimiento", 90), "person": ("Persona / empresa", 155),
            "reason": ("Motivo", 195), "amount": ("Importe", 100),
            "method": ("Tipo de pago", 115), "voucher": ("Voucher", 115),
            "evidence": ("Evidencias", 75), "status": ("Estado", 85),
        }
        for key, (label, width) in headings.items():
            self.tree.heading(key, text=label)
            self.tree.column(key, width=width, minwidth=60, anchor="w" if key in ("person", "reason") else "center")
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
                    row["counterparty"], row["reason"], format_money(row["amount_cents"]), row["payment_method"],
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
        listing = tk.Listbox(frame, bg=PANEL, fg=TEXT, selectbackground="#244B70", relief="flat", font=("Segoe UI", 9))
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
        ttk.Button(top, text="＋ Nuevo cliente", style="Accent.TButton", command=self.new_client).pack(side="right")
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
