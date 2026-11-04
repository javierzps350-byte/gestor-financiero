import queue
import threading
import tkinter as tk
from tkinter import ttk
from src.ui.premium import messagebox, palette_for

from src.agent.controller import FinancialAgent
from src.voice.speech import is_voice_engine_available, listen_once

BG = "#F2F6FA"
PANEL = "#FFFFFF"
TEXT = "#243449"
MUTED = "#8190A2"
ACCENT = "#2BAE9B"


class AssistantView(ttk.Frame):
    """Conversational UI for the built-in financial agent."""

    def __init__(self, parent, on_data_changed=None, on_navigate=None):
        super().__init__(parent, padding=20)
        self.agent = FinancialAgent()
        self.on_data_changed = on_data_changed or (lambda: None)
        self.on_navigate = on_navigate or (lambda _page: None)
        self._voice_queue = queue.Queue()
        self._voice_poll_job = None
        self._build()

    def _build(self):
        ttk.Label(self, text="Agente", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="Consulta y administra tus registros con instrucciones en lenguaje natural.",
            style="SubTitle.TLabel",
        ).pack(anchor="w", pady=(4, 14))

        self.chat = tk.Text(
            self, wrap="word", bg=PANEL, fg=TEXT, insertbackground=TEXT,
            relief="flat", padx=18, pady=16, font=("Segoe UI", 10),
            state="disabled", spacing1=3, spacing3=9, highlightthickness=1, highlightbackground="#E1E8EF",
        )
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.chat.yview)
        self.chat.configure(yscrollcommand=scrollbar.set)
        self.chat.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y", padx=(5, 0))
        self.chat.tag_configure("user", foreground=ACCENT, font=("Segoe UI", 9, "bold"), spacing1=9)
        self.chat.tag_configure("agent", foreground="#238F80", font=("Segoe UI", 9, "bold"), spacing1=9)
        self.chat.tag_configure("body", foreground=TEXT)
        self.chat.tag_configure("muted", foreground=MUTED, font=("Segoe UI", 9))

        self._append(
            "Agente",
            "Estoy listo. Puedo consultar tus cuentas, registrar ingresos y gastos, crear clientes y adjuntar comprobantes.\n\n"
            "Prueba: «Carlos me pagó 25 dólares por mensualidad mediante transferencia, voucher 2581».\n"
            "También puedes escribir «ayuda» para ver más ejemplos.",
        )

        input_area = ttk.Frame(self)
        input_area.pack(fill="x", side="bottom", pady=(14, 0))
        self.command_var = tk.StringVar()
        self.entry = ttk.Entry(input_area, textvariable=self.command_var)
        self.entry.pack(side="left", fill="x", expand=True, ipady=8)
        self.entry.bind("<Return>", lambda _event: self.execute())
        self.send_button = self._plain_button(input_area, "Enviar", self.execute, primary=True)
        self.send_button.pack(side="left", padx=(8, 0))
        self.voice_button = self._plain_button(input_area, "Hablar", self.listen)
        self.voice_button.pack(side="left", padx=(8, 0))

        self.pending_bar = tk.Frame(self, bg=BG)
        self.confirm_button = self._plain_button(
            self.pending_bar, "Confirmar operación", self.confirm, primary=True
        )
        self.cancel_button = self._plain_button(self.pending_bar, "Cancelar", self.cancel)
        if not is_voice_engine_available():
            self.voice_button.configure(state="disabled")
            self._append("Sistema", "El reconocimiento de voz no está configurado en este equipo. Puedes usar el asistente por texto.", "muted")

    def set_theme(self, palette):
        """Update the chat surface and message accents when the app theme changes."""
        self.chat.configure(
            bg=palette["panel"], fg=palette["text"],
            insertbackground=palette["text"],
            highlightbackground=palette["border"],
        )
        self.chat.tag_configure("user", foreground=palette["accent"])
        self.chat.tag_configure("agent", foreground=palette["success"])
        self.chat.tag_configure("body", foreground=palette["text"])
        self.chat.tag_configure("muted", foreground=palette["muted"])
        self.pending_bar.configure(bg=palette["bg"])
        for button, primary in ((self.confirm_button, True), (self.cancel_button, False), (self.send_button, True), (self.voice_button, False)):
            base = palette["accent"] if primary else palette["panel_alt"]
            foreground = palette["panel"] if primary else palette["text"]
            hover = palette["accent_hover"] if primary else palette["selected"]
            button.configure(bg=base, fg=foreground, activebackground=hover, activeforeground=foreground)

    @staticmethod
    def _plain_button(parent, text, command, primary=False):
        return tk.Button(
            parent, text=text, command=command,
            bg=ACCENT if primary else "#EAF0F5",
            fg="#FFFFFF" if primary else TEXT,
            activebackground="#239987" if primary else "#E0EAF1",
            activeforeground="#FFFFFF" if primary else TEXT,
            disabledforeground="#718096", font=("Segoe UI", 9, "bold" if primary else "normal"),
            relief="flat", bd=0, highlightthickness=0,
            padx=15, pady=9, cursor="hand2", takefocus=True,
        )

    def _append(self, speaker, message, tag="body"):
        self.chat.configure(state="normal")
        self.chat.insert("end", f"{speaker}\n", "user" if speaker == "Tú" else "agent" if speaker == "Agente" else "muted")
        self.chat.insert("end", message + "\n\n", tag)
        self.chat.configure(state="disabled")
        self.chat.see("end")

    def _refresh_pending_controls(self):
        has_pending = self.agent.pending is not None
        has_choice = self.agent.awaiting_choice is not None
        self.pending_bar.pack_forget()
        if has_pending and not has_choice:
            self.pending_bar.pack(fill="x", side="bottom", pady=(10, 0))
            self.cancel_button.pack(side="right")
            self.confirm_button.pack(side="right", padx=(0, 8))
            if self.agent.pending.get("awaiting"):
                self.confirm_button.configure(state="disabled")
            else:
                self.confirm_button.configure(state="normal")
        elif has_pending or has_choice:
            self.pending_bar.pack(fill="x", side="bottom", pady=(10, 0))
            self.cancel_button.pack(side="right")
            self.confirm_button.pack_forget()
        else:
            self.confirm_button.pack_forget()
            self.cancel_button.pack_forget()

    def execute(self):
        command = self.command_var.get().strip()
        if not command:
            return
        self.command_var.set("")
        self._append("Tú", command)
        try:
            response = self.agent.handle(command)
            self._append("Agente", response)
            self._refresh_pending_controls()
            if response.startswith(("Operación guardada", "Cliente creado", "Tarifa actualizada", "Comprobante adjuntado")):
                self._notify_data_changed()
            if self.agent.navigation_target:
                destination = self.agent.navigation_target
                self.agent.navigation_target = None
                self.on_navigate(destination)
        except Exception as exc:
            self._append("Agente", f"No pude procesar la instrucción: {exc}")
            messagebox.showerror("Error del asistente", str(exc), parent=self)

    def confirm(self):
        response = self.agent.confirm()
        self._append("Agente", response)
        self._refresh_pending_controls()
        if response.startswith(("Operación guardada", "Cliente creado", "Tarifa actualizada", "Comprobante adjuntado")):
            self._notify_data_changed()

    def _notify_data_changed(self):
        try:
            self.on_data_changed()
        except Exception as exc:
            self._append("Sistema", f"El registro se guardó, pero no se pudo actualizar la vista: {exc}", "muted")

    def cancel(self):
        self._append("Agente", self.agent.cancel())
        self._refresh_pending_controls()

    def listen(self):
        if not is_voice_engine_available():
            messagebox.showinfo("Voz no configurada", "Instala los componentes opcionales de voz y coloca el modelo español indicado en la documentación.", parent=self)
            return
        self.voice_button.configure(state="disabled", text="Escuchando…")
        self._append("Sistema", "Escuchando. Habla ahora…", "muted")
        threading.Thread(target=self._listen_worker, daemon=True).start()
        self._voice_poll_job = self.after(150, self._poll_voice_result)

    def _listen_worker(self):
        try:
            self._voice_queue.put((True, listen_once()))
        except Exception as exc:
            self._voice_queue.put((False, str(exc)))

    def _poll_voice_result(self):
        self._voice_poll_job = None
        try:
            ok, result = self._voice_queue.get_nowait()
        except queue.Empty:
            self._voice_poll_job = self.after(150, self._poll_voice_result)
            return
        self.voice_button.configure(state="normal", text="Hablar")
        if not ok:
            self._append("Agente", f"No se pudo reconocer la voz: {result}")
            return
        self.command_var.set(result.strip())
        if result.strip():
            self.execute()
        else:
            self._append("Agente", "No se detectó una frase. Inténtalo nuevamente.")

    def destroy(self):
        job, self._voice_poll_job = self._voice_poll_job, None
        if job is not None:
            try:
                self.after_cancel(job)
            except tk.TclError:
                pass
        super().destroy()
