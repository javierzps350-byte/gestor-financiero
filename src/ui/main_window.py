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
    client_debt_summary, client_payment_history, dashboard_summary,
    list_client_charges, list_clients, search_movements, set_client_active,
    void_movement,
)
from src.services.evidence_service import evidence_absolute_path
from src.services.report_service import export_debts_csv, export_movements_csv
from src.ui.dialogs import ClientDialog, MovementDialog, RateDialog
from src.ui.assistant_view import AssistantView

BG = "#0B1220"
PANEL = "#131F31"
PANEL_ALT = "#1B2A40"
TEXT = "#EDF2FA"
MUTED = "#94A3B8"
ACCENT = "#62B8E8"
GREEN = "#4CC6A2"
RED = "#EF7D83"
BORDER = "#26374E"
SIDEBAR = "#0E1929"


class MainWindow:
    """Main application shell with lightweight animated page navigation."""

    NAV_ITEMS = [
        ("dashboard", "Inicio"),
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
        style.configure("SubTitle.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))

        style.configure(
            "TButton", font=("Segoe UI", 9), padding=(13, 8),
            background=PANEL_ALT, foreground=TEXT, borderwidth=0,
        )
        style.map(
            "TButton",
            background=[("active", "#2A405C"), ("disabled", "#202A38")],
            foreground=[("disabled", "#65758A")],
        )
        style.configure(
            "Accent.TButton", background=ACCENT, foreground="#081523",
            font=("Segoe UI", 9, "bold"), padding=(14, 9),
        )
        style.map("Accent.TButton", background=[("active", "#83CFF2")])
        style.configure(
            "TEntry", fieldbackground=PANEL, foreground=TEXT,
            insertcolor=TEXT, bordercolor=BORDER, padding=9,
        )
        style.configure(
            "TCombobox", fieldbackground=PANEL, background=PANEL,
            foreground=TEXT, arrowcolor=TEXT, padding=8,
        )
        style.map(
            "TCombobox", fieldbackground=[("readonly", PANEL)],
            foreground=[("readonly", TEXT)],
        )
        style.configure("TCheckbutton", background=BG, foreground=TEXT, font=("Segoe UI", 9))
        style.map("TCheckbutton", background=[("active", BG)])
        style.configure(
            "Treeview", background=PANEL, fieldbackground=PANEL,
            foreground=TEXT, rowheight=36, borderwidth=0,
            font=("Segoe UI", 9),
        )
        style.configure(
            "Treeview.Heading", background=PANEL_ALT, foreground="#C9D5E5",
            relief="flat", font=("Segoe UI", 9, "bold"), padding=(11, 10),
        )
        style.map("Treeview", background=[("selected", "#244B70")], foreground=[("selected", "#FFFFFF")])
        style.configure("TScrollbar", background=PANEL, troughcolor=BG, bordercolor=BG, arrowcolor=MUTED)

    def _build_shell(self):
        # Minimal header: brand only, without decorative status labels.
        top = tk.Frame(self.root, bg="#101A2A", height=68, padx=25)
        top.pack(fill="x")
        top.pack_propagate(False)
        tk.Label(
            top, text="Gestor financiero", bg="#101A2A", fg=TEXT,
            font=("Segoe UI", 16, "bold"),
        ).pack(side="left", anchor="center")
        tk.Frame(self.root, bg=BORDER, height=1).pack(fill="x")

        shell = tk.Frame(self.root, bg=BG)
        shell.pack(fill="both", expand=True)

        self.sidebar = tk.Frame(shell, bg=SIDEBAR, width=205, padx=10, pady=18)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        for page_id, label in self.NAV_ITEMS:
            self._make_nav_button(page_id, label)

        work = tk.Frame(shell, bg=BG)
        work.pack(side="left", fill="both", expand=True)
        self.page_host = tk.Frame(work, bg=BG)
        self.page_host.pack(fill="both", expand=True, padx=(18, 22), pady=18)

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
        row = tk.Frame(self.sidebar, bg=SIDEBAR, height=44)
        row.pack(fill="x", padx=3, pady=3)
        row.pack_propagate(False)
        indicator = tk.Frame(row, bg=SIDEBAR, width=3)
        indicator.pack(side="left", fill="y")
        button = tk.Button(
            row, text=label, anchor="w",
            bg=SIDEBAR, fg="#AAB7C9", activebackground="#203550",
            activeforeground=TEXT, relief="flat", bd=0,
            highlightthickness=0, font=("Segoe UI", 10),
            padx=16, pady=9, cursor="hand2",
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
        color = "#17283D" if hovered else SIDEBAR
        row.configure(bg=color)
        button.configure(bg=color)

    def _set_nav_active(self, page_id):
        for key, (row, indicator, button) in self._nav_widgets.items():
            active = key == page_id
            bg = "#1B3049" if active else SIDEBAR
            row.configure(bg=bg)
            indicator.configure(bg=ACCENT if active else SIDEBAR)
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
        heading.pack(fill="x", pady=(0, 22))
        tk.Label(
            heading, text="Resumen general", bg=BG, fg=TEXT,
            font=("Segoe UI", 23, "bold"),
        ).pack(anchor="w")
        tk.Label(
            heading, text="Ingresos, gastos y cuentas pendientes.",
            bg=BG, fg=MUTED, font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(5, 0))

        self.cards = tk.Frame(self, bg=BG)
        self.cards.pack(fill="x")
        self.card_values = {}
        card_specs = [
            ("income", "Ingresos del mes", GREEN, "Dinero recibido"),
            ("expenses", "Gastos del mes", RED, "Dinero pagado"),
            ("net", "Balance del mes", ACCENT, "Ingresos menos gastos"),
            ("overdue", "Deuda vencida", "#E8B86D", "Cuotas fuera de fecha"),
        ]
        for index, (key, label, color, caption) in enumerate(card_specs):
            card = tk.Frame(
                self.cards, bg=PANEL, padx=17, pady=16,
                highlightthickness=1, highlightbackground=BORDER,
            )
            card.grid(
                row=0, column=index, sticky="nsew",
                padx=(0 if index == 0 else 7, 0 if index == 3 else 7),
            )
            self.cards.grid_columnconfigure(index, weight=1, uniform="summary")
            tk.Frame(card, bg=color, height=3).pack(fill="x", side="top", pady=(0, 15))
            tk.Label(
                card, text=label.upper(), bg=PANEL, fg=MUTED,
                font=("Segoe UI", 8, "bold"),
            ).pack(anchor="w")
            value = tk.Label(
                card, text="$0,00", bg=PANEL, fg=TEXT,
                font=("Segoe UI", 20, "bold"),
            )
            value.pack(anchor="w", pady=(10, 4))
            tk.Label(
                card, text=caption, bg=PANEL, fg="#8292A8",
                font=("Segoe UI", 8),
            ).pack(anchor="w")
            self.card_values[key] = value

        lower = tk.Frame(self, bg=BG)
        lower.pack(fill="both", expand=True, pady=(20, 0))
        activity = tk.Frame(
            lower, bg=PANEL, padx=21, pady=20,
            highlightthickness=1, highlightbackground=BORDER,
        )
        activity.pack(side="left", fill="both", expand=True)
        tk.Label(
            activity, text="Resumen de clientes", bg=PANEL,
            fg=TEXT, font=("Segoe UI", 11, "bold"),
        ).pack(anchor="w")
        tk.Frame(activity, bg=BORDER, height=1).pack(fill="x", pady=(14, 16))

        client_metrics = tk.Frame(activity, bg=PANEL)
        client_metrics.pack(fill="x", anchor="n")
        client_metrics.grid_columnconfigure(0, weight=1, uniform="client_metrics")
        client_metrics.grid_columnconfigure(1, weight=1, uniform="client_metrics")

        active_card = tk.Frame(
            client_metrics, bg="#192A40", padx=18, pady=17,
            highlightthickness=1, highlightbackground="#2A3C54",
        )
        active_card.grid(row=0, column=0, sticky="nsew", padx=(0, 7))
        tk.Label(
            active_card, text="CLIENTES ACTIVOS", bg="#192A40", fg=MUTED,
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w")
        self.active_clients_value = tk.Label(
            active_card, text="0", bg="#192A40", fg=TEXT,
            font=("Segoe UI", 25, "bold"),
        )
        self.active_clients_value.pack(anchor="w", pady=(9, 0))

        overdue_card = tk.Frame(
            client_metrics, bg="#192A40", padx=18, pady=17,
            highlightthickness=1, highlightbackground="#2A3C54",
        )
        overdue_card.grid(row=0, column=1, sticky="nsew", padx=(7, 0))
        tk.Label(
            overdue_card, text="CLIENTES CON DEUDA VENCIDA", bg="#192A40", fg=MUTED,
            font=("Segoe UI", 8, "bold"),
        ).pack(anchor="w")
        self.overdue_clients_value = tk.Label(
            overdue_card, text="0", bg="#192A40", fg="#E8B86D",
            font=("Segoe UI", 25, "bold"),
        )
        self.overdue_clients_value.pack(anchor="w", pady=(9, 0))

        actions = tk.Frame(lower, bg=BG, width=222, padx=16)
        actions.pack(side="right", fill="y")
        actions.pack_propagate(False)
        tk.Label(
            actions, text="Acciones rápidas", bg=BG, fg=MUTED,
            font=("Segoe UI", 9, "bold"),
        ).pack(anchor="w", pady=(3, 12))
        self._action_button(actions, "Registrar ingreso", lambda: self._new("income"), primary=True).pack(fill="x", pady=4)
        self._action_button(actions, "Registrar gasto", lambda: self._new("expense")).pack(fill="x", pady=4)
        self._action_button(actions, "Nuevo cliente", self._new_client).pack(fill="x", pady=4)
        tk.Frame(actions, bg=BORDER, height=1).pack(fill="x", pady=13)
        self._action_button(actions, "Crear copia de seguridad", self.backup).pack(fill="x", pady=4)
        self._action_button(actions, "Actualizar resumen", self.refresh).pack(fill="x", pady=4)

    @staticmethod
    def _action_button(parent, text, command, primary=False):
        bg = ACCENT if primary else PANEL_ALT
        fg = "#081523" if primary else TEXT
        hover = "#83CFF2" if primary else "#2A405C"
        button = tk.Button(
            parent, text=text, command=command, anchor="w",
            bg=bg, fg=fg, activebackground=hover, activeforeground=fg,
            relief="flat", bd=0, highlightthickness=0,
            padx=14, pady=12, font=("Segoe UI", 9, "bold" if primary else "normal"),
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
            self.active_clients_value.configure(text=str(summary["active_clients"]))
            self.overdue_clients_value.configure(
                text=str(summary["clients_with_due_charges"]),
                fg="#E8B86D" if summary["clients_with_due_charges"] else TEXT,
            )
        except Exception as exc:
            self.active_clients_value.configure(text="—")
            self.overdue_clients_value.configure(text="—")
            messagebox.showerror("No se pudo cargar el resumen", str(exc), parent=self)


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
