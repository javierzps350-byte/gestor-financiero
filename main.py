import logging
import tkinter as tk
from tkinter import messagebox

from src.database.connection import initialize_database
from src.ui.main_window import run_app
from src.utils.logging_config import configure_logging


def main():
    configure_logging()
    try:
        initialize_database()
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
