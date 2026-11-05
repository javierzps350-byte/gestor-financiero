import os
import unittest

from src.ui.theme_manager import THEMES, ThemeManager
from src.ui.widgets import ElegantCombobox


class ElegantControlTests(unittest.TestCase):
    def test_all_themes_keep_the_expected_visual_tokens(self):
        for theme_id, palette in THEMES.items():
            with self.subTest(theme=theme_id):
                self.assertIn("input", palette)
                self.assertIn("selected", palette)
                self.assertIn("shadow", palette)
                self.assertEqual(len(palette["accent"]), 7)

    def test_combobox_layout_has_no_legacy_arrow(self):
        if os.environ.get("GF_RUN_UI_TESTS") != "1":
            self.skipTest("Activa GF_RUN_UI_TESTS=1 para ejecutar pruebas visuales Tkinter")
        import tkinter as tk
        from tkinter import ttk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No hay entorno gráfico: {exc}")
        try:
            manager = ThemeManager()
            manager.configure_styles(root)
            combo = ElegantCombobox(root, values=("Uno", "Dos", "Tres"), state="readonly")
            combo.pack(fill="x", padx=20, pady=20)
            root.update()
            layout = str(ttk.Style(root).layout("Elegant.TCombobox"))
            self.assertNotIn("Combobox.downarrow", layout)
            combo.current(0)
            self.assertEqual(combo.get(), "Uno")
            # Clicking the blank, arrowless surface must still post the native list.
            combo.event_generate("<Button-1>", x=80, y=12)
            root.update()
            popdown = str(root.tk.call("ttk::combobox::PopdownWindow", combo))
            self.assertTrue(bool(root.tk.call("winfo", "ismapped", popdown)))
            combo.event_generate("<Escape>")
            root.update()
            try:
                root.tk.call("ttk::combobox::Unpost", combo)
            except tk.TclError:
                pass
            root.update()
        finally:
            root.destroy()


    def test_dark_theme_uses_non_white_focus_and_popdown_colors(self):
        if os.environ.get("GF_RUN_UI_TESTS") != "1":
            self.skipTest("Activa GF_RUN_UI_TESTS=1 para ejecutar pruebas visuales Tkinter")
        import tkinter as tk
        from tkinter import ttk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No hay entorno gráfico: {exc}")
        try:
            manager = ThemeManager()
            manager.set_theme("oscuro")
            manager.configure_styles(root)
            style = ttk.Style(root)
            palette = manager.palette
            self.assertEqual(style.lookup("TEntry", "focuscolor"), palette["input"])
            self.assertEqual(style.lookup("Elegant.TCombobox", "focuscolor"), palette["input"])
            self.assertEqual(style.lookup("Treeview", "focuscolor"), palette["panel"])
            self.assertEqual(style.lookup("TCheckbutton", "indicatorcolor"), palette["input"])
        finally:
            root.destroy()

    def test_empty_movement_actions_return_without_modal_or_file_dialog(self):
        if os.environ.get("GF_RUN_UI_TESTS") != "1":
            self.skipTest("Activa GF_RUN_UI_TESTS=1 para ejecutar pruebas visuales Tkinter")
        import tkinter as tk
        import tempfile
        from pathlib import Path
        from unittest.mock import patch
        from src.database import connection
        from src.ui import theme_manager
        from src.ui.main_window import MovementView
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No hay entorno gráfico: {exc}")
        with tempfile.TemporaryDirectory() as temp:
            base = Path(temp)
            with patch.object(connection, "DB_PATH", base / "data" / "test.sqlite3"), \
                 patch.object(theme_manager, "DATA_DIR", base / "data"):
                connection.initialize_database()
                try:
                    view = MovementView(root, "income", "Ingresos")
                    view.pack(fill="both", expand=True)
                    root.geometry("1000x600")
                    root.update()
                    with patch("src.ui.main_window.filedialog.asksaveasfilename") as save_dialog, \
                         patch("src.ui.main_window.messagebox.askyesno") as confirm, \
                         patch("src.ui.main_window.messagebox.showwarning") as warning, \
                         patch("src.ui.main_window.messagebox.showinfo") as info:
                        view.export()
                        self.assertIn("No hay movimientos", view.action_status_var.get())
                        view.open_evidence()
                        self.assertIn("Selecciona un movimiento", view.action_status_var.get())
                        self.assertFalse(save_dialog.called)
                        self.assertFalse(confirm.called)
                        self.assertFalse(warning.called)
                        self.assertFalse(info.called)
                finally:
                    root.destroy()

    def test_sidebar_theme_palette_uses_three_icon_only_swatches(self):
        if os.environ.get("GF_RUN_UI_TESTS") != "1":
            self.skipTest("Activa GF_RUN_UI_TESTS=1 para ejecutar pruebas visuales Tkinter")
        import tkinter as tk
        from src.ui.main_window import MainWindow
        from src.database.connection import initialize_database
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No hay entorno gráfico: {exc}")
        try:
            initialize_database()
            root.geometry("1280x820+10+10")
            app = MainWindow(root)
            root.update()
            self.assertTrue(hasattr(app, "theme_canvas"))
            self.assertFalse(hasattr(app, "theme_button"))
            self.assertFalse(hasattr(app, "theme_panel"))
            self.assertEqual(int(app.theme_canvas.cget("height")), 34)
            app.theme_canvas.event_generate("<Button-1>", x=87, y=17)
            root.update()
            self.assertEqual(app.theme_manager.theme_id, "oscuro")
            self.assertEqual(app.theme_manager.palette["bg"], THEMES["oscuro"]["bg"])
            self.assertEqual(len(app.theme_canvas.find_withtag("theme:claro")), 3)
            self.assertEqual(len(app.theme_canvas.find_withtag("theme:suave")), 3)
            self.assertEqual(len(app.theme_canvas.find_withtag("theme:oscuro")), 3)



if __name__ == "__main__":
    unittest.main()
