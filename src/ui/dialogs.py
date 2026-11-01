import os
import tkinter as tk
from tkinter import filedialog, messagebox, ttk
from datetime import date

from src.domain.money import to_cents
from src.services.finance_service import create_client, create_movement, list_clients, set_client_rate
from src.services.evidence_service import attach_evidence, find_recent_downloads


def primary_button(parent, text: str, command):
    """Button with explicit Tk styling to avoid ttk theme/DPI rendering quirks."""
    return tk.Button(
        parent, text=text, command=command,
        bg="#35A7E8", fg="#071522",
        activebackground="#67C3F2", activeforeground="#071522",
        disabledforeground="#718096",
        font=("Segoe UI", 9, "bold"),
        relief="flat", bd=0, highlightthickness=0,
        padx=17, pady=8, cursor="hand2",
        takefocus=True,
    )


class BaseDialog(tk.Toplevel):
    def __init__(self, parent, title: str, size: str = "620x620"):
        super().__init__(parent)
        self.title(title)
        self.geometry(size)
        self.resizable(False, False)
        self.transient(parent)
        self.grab_set()
        self.configure(bg="#101827")
        self.protocol("WM_DELETE_WINDOW", self.destroy)


class ClientDialog(BaseDialog):
    def __init__(self, parent, on_saved):
        super().__init__(parent, "Nuevo cliente", "600x650")
        self.on_saved = on_saved
        self.vars = {
            "name": tk.StringVar(), "identification": tk.StringVar(),
            "phone": tk.StringVar(), "email": tk.StringVar(),
            "amount": tk.StringVar(), "start": tk.StringVar(value=date.today().isoformat()),
        }
        body = ttk.Frame(self, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Registrar cliente", style="DialogTitle.TLabel").pack(anchor="w", pady=(0, 16))
        self._field(body, "Nombre o razón social *", "name")
        self._field(body, "Identificación (opcional)", "identification")
        self._field(body, "Teléfono", "phone")
        self._field(body, "Correo electrónico", "email")
        self._field(body, "Mensualidad en dólares *", "amount")
        self._field(body, "Primera fecha de cobro (AAAA-MM-DD) *", "start")
        ttk.Label(body, text="El día de cobro se toma de la primera fecha. Los cambios de tarifa tendrán una fecha de vigencia.", style="Hint.TLabel", wraplength=500).pack(anchor="w", pady=(7, 16))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom")
        ttk.Button(buttons, text="Cancelar", command=self.destroy).pack(side="right", padx=(8, 0))
        primary_button(buttons, "Guardar cliente", self.save).pack(side="right", ipadx=3, ipady=1)

    def _field(self, parent, label, key):
        ttk.Label(parent, text=label).pack(anchor="w", pady=(8, 3))
        entry = ttk.Entry(parent, textvariable=self.vars[key])
        entry.pack(fill="x")
        if key == "name":
            entry.focus_set()

    def find_downloads(self):
        recent = find_recent_downloads(max_days=7, limit=150)
        if not recent:
            messagebox.showinfo("Descargas recientes", "No se encontraron archivos recientes en la carpeta Descargas.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Archivos recientes de Descargas")
        dialog.geometry("720x420")
        dialog.configure(bg="#101827")
        dialog.transient(self)
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Selecciona el comprobante correcto. Solo se mostrarán archivos de los últimos 7 días.", style="Hint.TLabel").pack(anchor="w", pady=(0, 10))
        columns = ("name", "modified", "size")
        listing = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        listing.heading("name", text="Archivo")
        listing.heading("modified", text="Modificado")
        listing.heading("size", text="Tamaño")
        listing.column("name", width=390)
        listing.column("modified", width=145, anchor="center")
        listing.column("size", width=100, anchor="e")
        listing.pack(fill="both", expand=True)
        for index, item in enumerate(recent):
            size = f"{item['size'] / 1024:.1f} KB" if item["size"] < 1024 * 1024 else f"{item['size'] / (1024 * 1024):.2f} MB"
            listing.insert("", "end", iid=str(index), values=(item["name"], item["modified"], size))
        def add_selected():
            selected = listing.selection()
            if not selected:
                messagebox.showwarning("Selecciona un archivo", "Selecciona el archivo que deseas adjuntar.", parent=dialog)
                return
            path = recent[int(selected[0])]["path"]
            if path not in self.evidence_paths:
                self.evidence_paths.append(path)
            self.files_label.configure(text="\n".join(os.path.basename(p) for p in self.evidence_paths))
            dialog.destroy()
        listing.bind("<Double-1>", lambda _e: add_selected())
        ttk.Button(frame, text="Adjuntar archivo seleccionado", style="Accent.TButton", command=add_selected).pack(anchor="e", pady=(10, 0))

    def save(self):
        try:
            amount = to_cents(self.vars["amount"].get())
            create_client(
                self.vars["name"].get(), amount, self.vars["start"].get(),
                phone=self.vars["phone"].get(), email=self.vars["email"].get(),
                identification=self.vars["identification"].get(),
            )
            self.on_saved()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self)


class RateDialog(BaseDialog):
    def __init__(self, parent, on_saved, initial_client_id=None):
        super().__init__(parent, "Cambiar tarifa", "500x360")
        self.on_saved = on_saved
        self.clients = list_clients()
        body = ttk.Frame(self, padding=24)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Nueva tarifa mensual", style="DialogTitle.TLabel").pack(anchor="w", pady=(0, 16))
        ttk.Label(body, text="Cliente").pack(anchor="w", pady=(5, 3))
        self.client_map = {f'{c["id"]} — {c["name"]}': c["id"] for c in self.clients}
        initial_key = next((key for key, value in self.client_map.items() if value == initial_client_id), None)
        self.client_var = tk.StringVar(value=initial_key or next(iter(self.client_map), ""))
        self.client_box = ttk.Combobox(body, textvariable=self.client_var, values=list(self.client_map), state="readonly")
        self.client_box.pack(fill="x")
        self.amount_var = tk.StringVar()
        self.date_var = tk.StringVar(value=date.today().isoformat())
        ttk.Label(body, text="Nueva mensualidad en dólares").pack(anchor="w", pady=(12, 3))
        ttk.Entry(body, textvariable=self.amount_var).pack(fill="x")
        ttk.Label(body, text="Fecha desde la que aplica (AAAA-MM-DD)").pack(anchor="w", pady=(12, 3))
        ttk.Entry(body, textvariable=self.date_var).pack(fill="x")
        ttk.Label(body, text="Usa como fecha de vigencia el inicio de un ciclo mensual.", style="Hint.TLabel").pack(anchor="w", pady=8)
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom", pady=(12, 0))
        ttk.Button(buttons, text="Cancelar", command=self.destroy).pack(side="right", padx=(8, 0))
        primary_button(buttons, "Guardar tarifa", self.save).pack(side="right", ipadx=3, ipady=1)

    def save(self):
        try:
            key = self.client_var.get()
            if key not in self.client_map:
                raise ValueError("Selecciona un cliente.")
            set_client_rate(self.client_map[key], to_cents(self.amount_var.get()), self.date_var.get())
            self.on_saved()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("No se pudo cambiar la tarifa", str(exc), parent=self)


class MovementDialog(BaseDialog):
    METHODS = ["Transferencia", "Depósito", "Efectivo", "Cheque", "Tarjeta", "Otro"]

    def __init__(self, parent, direction: str, on_saved):
        title = "Registrar ingreso" if direction == "income" else "Registrar gasto"
        super().__init__(parent, title, "650x790")
        self.direction = direction
        self.on_saved = on_saved
        self.evidence_paths: list[str] = []
        self.clients = list_clients(active_only=True)
        self.client_map = {f'{c["id"]} — {c["name"]}': c for c in self.clients}
        self.vars = {
            "counterparty": tk.StringVar(), "reason": tk.StringVar(),
            "amount": tk.StringVar(), "date": tk.StringVar(value=date.today().isoformat()),
            "method": tk.StringVar(value="Transferencia"), "voucher": tk.StringVar(),
            "client": tk.StringVar(), "apply": tk.BooleanVar(value=False),
        }
        body = ttk.Frame(self, padding=22)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=title, style="DialogTitle.TLabel").pack(anchor="w", pady=(0, 12))
        if direction == "income":
            ttk.Label(body, text="Cliente registrado (opcional)").pack(anchor="w", pady=(5, 3))
            self.client_box = ttk.Combobox(body, textvariable=self.vars["client"], values=list(self.client_map), state="readonly")
            self.client_box.pack(fill="x")
            self.client_box.bind("<<ComboboxSelected>>", self._client_selected)
        self._field(body, "Persona / empresa *", "counterparty")
        self._field(body, "Motivo del movimiento *", "reason")
        self._field(body, "Importe recibido o pagado *", "amount")
        self._field(body, "Fecha del pago (AAAA-MM-DD) *", "date")
        ttk.Label(body, text="Tipo de pago *").pack(anchor="w", pady=(9, 3))
        ttk.Combobox(body, textvariable=self.vars["method"], values=self.METHODS, state="readonly").pack(fill="x")
        self._field(body, "Número de voucher / comprobante (opcional)", "voucher")
        if direction == "income":
            ttk.Checkbutton(body, text="Aplicar este ingreso a las mensualidades del cliente", variable=self.vars["apply"]).pack(anchor="w", pady=(12, 4))
        ttk.Label(body, text="Observaciones (opcional)").pack(anchor="w", pady=(9, 3))
        self.notes = tk.Text(body, height=3, wrap="word", bg="#172235", fg="#EDF3FC", insertbackground="white", relief="flat", padx=9, pady=7)
        self.notes.pack(fill="x")
        evidence_frame = ttk.Frame(body)
        evidence_frame.pack(fill="x", pady=(12, 0))
        ttk.Label(evidence_frame, text="Evidencias adjuntas").pack(side="left")
        ttk.Button(evidence_frame, text="Buscar en Descargas…", command=self.find_downloads).pack(side="right", padx=(7, 0))
        ttk.Button(evidence_frame, text="Agregar archivos…", command=self.choose_files).pack(side="right")
        self.files_label = ttk.Label(body, text="No hay archivos seleccionados.", style="Hint.TLabel", wraplength=560)
        self.files_label.pack(anchor="w", pady=(5, 0))
        buttons = ttk.Frame(body)
        buttons.pack(fill="x", side="bottom", pady=(14, 0))
        ttk.Button(buttons, text="Cancelar", command=self.destroy).pack(side="right", padx=(8, 0))
        primary_button(buttons, "Guardar movimiento", self.save).pack(side="right", ipadx=3, ipady=1)

    def _field(self, parent, label, key):
        ttk.Label(parent, text=label).pack(anchor="w", pady=(9, 3))
        entry = ttk.Entry(parent, textvariable=self.vars[key])
        entry.pack(fill="x")

    def _client_selected(self, _event=None):
        selected = self.vars["client"].get()
        client = self.client_map.get(selected)
        if client:
            self.vars["counterparty"].set(client["name"])

    def choose_files(self):
        paths = filedialog.askopenfilenames(
            parent=self,
            title="Seleccionar evidencias",
            filetypes=[("Documentos e imágenes", "*.pdf *.png *.jpg *.jpeg *.webp *.doc *.docx *.xls *.xlsx *.csv *.txt"), ("Todos los archivos", "*.*")],
        )
        if paths:
            for path in paths:
                if path not in self.evidence_paths:
                    self.evidence_paths.append(path)
            self.files_label.configure(text="\n".join(os.path.basename(p) for p in self.evidence_paths))

    def find_downloads(self):
        recent = find_recent_downloads(max_days=7, limit=150)
        if not recent:
            messagebox.showinfo("Descargas recientes", "No se encontraron archivos recientes en la carpeta Descargas.", parent=self)
            return
        dialog = tk.Toplevel(self)
        dialog.title("Archivos recientes de Descargas")
        dialog.geometry("720x420")
        dialog.configure(bg="#101827")
        dialog.transient(self)
        frame = ttk.Frame(dialog, padding=16)
        frame.pack(fill="both", expand=True)
        ttk.Label(frame, text="Selecciona el comprobante correcto. Solo se mostrarán archivos de los últimos 7 días.", style="Hint.TLabel").pack(anchor="w", pady=(0, 10))
        columns = ("name", "modified", "size")
        listing = ttk.Treeview(frame, columns=columns, show="headings", selectmode="browse")
        listing.heading("name", text="Archivo")
        listing.heading("modified", text="Modificado")
        listing.heading("size", text="Tamaño")
        listing.column("name", width=390)
        listing.column("modified", width=145, anchor="center")
        listing.column("size", width=100, anchor="e")
        listing.pack(fill="both", expand=True)
        for index, item in enumerate(recent):
            size = f"{item['size'] / 1024:.1f} KB" if item["size"] < 1024 * 1024 else f"{item['size'] / (1024 * 1024):.2f} MB"
            listing.insert("", "end", iid=str(index), values=(item["name"], item["modified"], size))
        def add_selected():
            selected = listing.selection()
            if not selected:
                messagebox.showwarning("Selecciona un archivo", "Selecciona el archivo que deseas adjuntar.", parent=dialog)
                return
            path = recent[int(selected[0])]["path"]
            if path not in self.evidence_paths:
                self.evidence_paths.append(path)
            self.files_label.configure(text="\n".join(os.path.basename(p) for p in self.evidence_paths))
            dialog.destroy()
        listing.bind("<Double-1>", lambda _e: add_selected())
        ttk.Button(frame, text="Adjuntar archivo seleccionado", style="Accent.TButton", command=add_selected).pack(anchor="e", pady=(10, 0))

    def save(self):
        try:
            amount = to_cents(self.vars["amount"].get())
            client_id = None
            if self.direction == "income" and self.vars["client"].get() in self.client_map:
                client_id = int(self.client_map[self.vars["client"].get()]["id"])
            if self.vars["apply"].get() and client_id is None:
                raise ValueError("Selecciona un cliente para aplicar el ingreso a mensualidades.")
            counterparty = self.vars["counterparty"].get().strip()
            if not counterparty and client_id:
                counterparty = self.client_map[self.vars["client"].get()]["name"]
            movement_id = create_movement(
                direction=self.direction,
                counterparty=counterparty,
                reason=self.vars["reason"].get(),
                amount_cents=amount,
                payment_date=self.vars["date"].get(),
                payment_method=self.vars["method"].get(),
                client_id=client_id,
                voucher_number=self.vars["voucher"].get(),
                notes=self.notes.get("1.0", "end").strip(),
                apply_to_monthly=self.vars["apply"].get(),
            )
            attachment_errors = []
            for path in self.evidence_paths:
                try:
                    attach_evidence(movement_id, path)
                except Exception as exc:
                    attachment_errors.append(f"{os.path.basename(path)}: {exc}")
            self.on_saved()
            self.destroy()
            if attachment_errors:
                messagebox.showwarning("Movimiento guardado con advertencias", "El movimiento se guardó, pero algunos archivos no pudieron adjuntarse:\n\n" + "\n".join(attachment_errors), parent=self.master)
            else:
                messagebox.showinfo("Registro guardado", f"Movimiento #{movement_id} registrado correctamente.", parent=self.master)
        except Exception as exc:
            messagebox.showerror("No se pudo guardar", str(exc), parent=self)
