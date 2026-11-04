import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from src.database import connection
from src.ui import theme_manager


class AppBootTests(unittest.TestCase):
    def test_main_window_builds_all_pages_without_gpu_or_external_packages(self):
        if os.environ.get("GF_RUN_UI_TESTS") != "1":
            self.skipTest("Activa GF_RUN_UI_TESTS=1 para ejecutar pruebas visuales Tkinter")
        import tkinter as tk
        from src.ui.main_window import MainWindow

        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No hay un entorno gráfico disponible: {exc}")

        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            with patch.object(connection, "DB_PATH", base / "data" / "test.sqlite3"), \
                 patch.object(theme_manager, "DATA_DIR", base / "data"):
                connection.initialize_database()
                try:
                    app = MainWindow(root)
                    root.update_idletasks()
                    root.update()
                    self.assertEqual(
                        set(app.pages),
                        {"dashboard", "incomes", "expenses", "clients", "debts", "search", "assistant"},
                    )
                    self.assertGreater(root.winfo_width(), 1000)
                    self.assertGreater(root.winfo_height(), 600)
                finally:
                    root.destroy()


if __name__ == "__main__":
    unittest.main()
