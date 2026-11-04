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

    def test_sidebar_theme_picker_changes_theme_without_text_combobox(self):
        if os.environ.get("GF_RUN_UI_TESTS") != "1":
            self.skipTest("Activa GF_RUN_UI_TESTS=1 para ejecutar pruebas visuales Tkinter")
        import tkinter as tk
        from src.database.connection import initialize_database
        from src.ui.main_window import MainWindow
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No hay entorno gráfico: {exc}")
        try:
            initialize_database()
            root.geometry("1280x820+10+10")
            app = MainWindow(root)
            root.update()
            self.assertTrue(hasattr(app, "theme_button"))
            self.assertFalse(hasattr(app, "theme_box"))
            self.assertIsInstance(app.data_button, tk.Button)
            app.open_theme_picker()
            root.update()
            self.assertTrue(app.theme_panel.winfo_manager())
            app._select_theme("oscuro")
            root.update()
            self.assertEqual(app.theme_manager.theme_id, "oscuro")
            self.assertIn("Oscuro elegante", app.theme_button.cget("text"))
            self.assertTrue(app.theme_panel.winfo_manager())
            app.change_theme("claro")
            root.update()
            app.open_data_actions()
            root.update()
            self.assertTrue(app._data_picker.winfo_exists())
            app._data_picker.destroy()
            app._data_picker = None
            root.update()
        finally:
            root.destroy()


if __name__ == "__main__":
    unittest.main()
