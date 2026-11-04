import logging
import sys
import tkinter as tk
from tkinter import messagebox

from src.database.connection import initialize_database
from src.ui.main_window import run_app
from src.utils.logging_config import configure_logging


def enable_windows_dpi_awareness():
    """Let Windows render Tk at the monitor's native DPI instead of bitmap scaling."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        # PER_MONITOR_AWARE_V2 where supported; fall back for older Windows.
        try:
            ctypes.windll.user32.SetProcessDpiAwarenessContext(ctypes.c_void_p(-4))
        except Exception:
            try:
                ctypes.windll.shcore.SetProcessDpiAwareness(2)
            except Exception:
                ctypes.windll.user32.SetProcessDPIAware()
    except Exception:
        pass


def main():
    enable_windows_dpi_awareness()
    configure_logging()
    try:
        migrations = initialize_database()
        if migrations:
            logging.info("Actualización de base de datos aplicada: %s", "; ".join(migrations))
        run_app()
    except Exception as exc:
        logging.exception("Error fatal al iniciar la aplicación")
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Error al iniciar Gestor Financiero", str(exc))
            root.destroy()
        except Exception:
            raise


if __name__ == "__main__":
    main()
