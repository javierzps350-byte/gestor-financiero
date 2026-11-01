import queue
import threading
import tkinter as tk
from tkinter import messagebox, ttk

from src.voice.assistant import handle_text_command
from src.voice.speech import is_voice_engine_available, listen_once
PANEL = "#172235"
TEXT = "#E8EEF7"
MUTED = "#9AAAC0"


class AssistantView(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent, padding=20)
        ttk.Label(self, text="Asistente", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            self,
            text="Consultas rápidas por texto o voz. El micrófono solo se activa al pulsar el botón.",
            style="SubTitle.TLabel",
        ).pack(anchor="w", pady=(4, 18))
        examples = tk.Frame(self, bg=PANEL, padx=16, pady=14)
        examples.pack(fill="x", pady=(0, 16))
        tk.Label(examples, text="EJEMPLOS", bg=PANEL, fg=TEXT, font=("Segoe UI", 9, "bold")).pack(anchor="w")
        tk.Label(
            examples,
            text="• ¿Cuánto debe Carlos?\n• Ingresos del mes\n• Gastos del mes\n• Busca voucher 002581",
            bg=PANEL, fg=MUTED, justify="left", font=("Segoe UI", 10),
        ).pack(anchor="w", pady=(8, 0))
        ttk.Label(self, text="Escribe una consulta").pack(anchor="w")
        self.command_var = tk.StringVar()
        entry = ttk.Entry(self, textvariable=self.command_var)
        entry.pack(fill="x", pady=(4, 10))
        entry.bind("<Return>", lambda _e: self.execute())
        actions = ttk.Frame(self)
        actions.pack(fill="x")
        ttk.Button(actions, text="Consultar", style="Accent.TButton", command=self.execute).pack(side="left")
        self.voice_button = ttk.Button(actions, text="🎙 Escuchar una vez", command=self.listen)
        self.voice_button.pack(side="left", padx=8)
        ttk.Label(actions, text="El reconocimiento de voz es opcional y requiere instalar un modelo local.", style="Hint.TLabel").pack(side="left", padx=8)
        self.output = tk.Text(self, height=11, wrap="word", bg=PANEL, fg=TEXT, insertbackground=TEXT, relief="flat", padx=14, pady=12, font=("Segoe UI", 10), state="disabled")
        self.output.pack(fill="both", expand=True, pady=(16, 0))
        self._voice_queue = queue.Queue()
        self._write("El asistente está listo. Por ahora realiza consultas; no registra ni modifica movimientos sin una confirmación explícita.")
        if not is_voice_engine_available():
            self.voice_button.configure(text="🎙 Configurar voz…")

    def _write(self, text):
        self.output.configure(state="normal")
        self.output.delete("1.0", "end")
        self.output.insert("1.0", text)
        self.output.configure(state="disabled")

    def execute(self):
        command = self.command_var.get()
        try:
            self._write(handle_text_command(command))
        except Exception as exc:
            messagebox.showerror("Error del asistente", str(exc), parent=self)

    def listen(self):
        if not is_voice_engine_available():
            messagebox.showinfo(
                "Voz opcional",
                "Para habilitar voz local instala las dependencias de installer/requirements_voice.txt "
                "y coloca un modelo español compatible en models/vosk-es.\n\n"
                "La aplicación seguirá funcionando sin este componente.",
                parent=self,
            )
            return
        self.voice_button.configure(state="disabled", text="Escuchando…")
        self._write("Escuchando una intervención. Habla cerca del micrófono…")
        worker = threading.Thread(target=self._listen_worker, daemon=True)
        worker.start()
        self.after(150, self._poll_voice_result)

    def _listen_worker(self):
        try:
            self._voice_queue.put((True, listen_once()))
        except Exception as exc:
            self._voice_queue.put((False, str(exc)))

    def _poll_voice_result(self):
        try:
            ok, result = self._voice_queue.get_nowait()
        except queue.Empty:
            self.after(150, self._poll_voice_result)
            return
        self.voice_button.configure(state="normal", text="🎙 Escuchar una vez")
        if not ok:
            messagebox.showerror("No se pudo reconocer la voz", result, parent=self)
            return
        transcript = result.strip()
        self.command_var.set(transcript)
        self._write(handle_text_command(transcript) if transcript else "No se detectó una frase. Inténtalo nuevamente.")
