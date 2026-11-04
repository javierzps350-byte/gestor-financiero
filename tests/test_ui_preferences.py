import json
import tempfile
import unittest
from pathlib import Path

from src.ui.date_picker import month_weeks
from src.ui.theme_manager import THEMES, ThemeManager, _role_for_color
from src.ui.date_picker import DatePickerEntry


class ThemeManagerTests(unittest.TestCase):
    def test_all_themes_have_complete_semantic_palette(self):
        required = {
            "bg", "panel", "panel_alt", "text", "muted", "accent",
            "accent_hover", "expense", "expense_hover", "border",
            "selected", "table_header", "grid", "shadow", "input",
            "sidebar", "success", "danger",
        }
        for theme_id, palette in THEMES.items():
            with self.subTest(theme=theme_id):
                self.assertTrue(required.issubset(palette))
                for role in required:
                    self.assertRegex(palette[role], r"^#[0-9A-Fa-f]{6}$")

    def test_theme_preference_persists_between_instances(self):
        with tempfile.TemporaryDirectory() as directory:
            settings = Path(directory) / "ui_preferences.json"
            manager = ThemeManager()
            manager.settings_path = settings
            manager.set_theme("oscuro")

            stored = json.loads(settings.read_text(encoding="utf-8"))
            self.assertEqual(stored["theme"], "oscuro")

            second = ThemeManager()
            second.settings_path = settings
            second.theme_id = second._load_theme()
            second.palette = THEMES[second.theme_id]
            self.assertEqual(second.theme_id, "oscuro")
            self.assertEqual(second.palette["bg"], THEMES["oscuro"]["bg"])

    def test_theme_color_roles_allow_repeated_switching(self):
        for palette in THEMES.values():
            for role in ("bg", "panel", "text", "muted", "accent", "expense", "border"):
                self.assertEqual(_role_for_color(palette[role]), role)


class DatePickerCalendarTests(unittest.TestCase):
    def test_month_grid_contains_all_days_and_seven_columns(self):
        weeks = month_weeks(2026, 11)
        days = [day for week in weeks for day in week if day]
        self.assertTrue(all(len(week) == 7 for week in weeks))
        self.assertEqual(days, list(range(1, 31)))

    def test_month_grid_uses_monday_as_first_column(self):
        # 1 November 2026 is Sunday, hence it belongs in the seventh column.
        weeks = month_weeks(2026, 11)
        self.assertEqual(weeks[0][6], 1)
        self.assertEqual(weeks[0][:6], [0, 0, 0, 0, 0, 0])

    def test_invalid_month_is_rejected(self):
        with self.assertRaises(ValueError):
            month_weeks(2026, 13)

    def test_calendar_overlay_works_inside_a_modal_form_without_stealing_grab(self):
        import os
        if os.environ.get("GF_RUN_UI_TESTS") != "1":
            self.skipTest("Activa GF_RUN_UI_TESTS=1 para ejecutar pruebas visuales Tkinter")
        import tkinter as tk
        from datetime import date
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No hay un entorno gráfico disponible: {exc}")
        try:
            root.geometry("900x700+10+10")
            form = tk.Toplevel(root)
            form.geometry("500x480+40+40")
            form.transient(root)
            form.grab_set()
            variable = tk.StringVar(value=date.today().isoformat())
            picker = DatePickerEntry(form, textvariable=variable)
            picker.pack(padx=20, pady=170, fill="x")
            root.update()

            previous_grab = root.grab_current()
            top_levels_before = len(root.winfo_children())
            picker.open_calendar()
            root.update()

            self.assertIsNotNone(picker._popup)
            self.assertTrue(picker._popup.winfo_ismapped())
            self.assertEqual(len(root.winfo_children()), top_levels_before)
            self.assertIs(root.grab_current(), previous_grab)

            day_button = next(button for button in picker._day_buttons if button.cget("text") == "15")
            day_button.invoke()
            root.update()
            self.assertEqual(variable.get(), date.today().replace(day=15).isoformat())
            self.assertIsNone(picker._popup)
            self.assertIs(root.grab_current(), previous_grab)
        finally:
            root.destroy()

    def test_nested_premium_dialog_restores_the_parent_modal_grab(self):
        import os
        if os.environ.get("GF_RUN_UI_TESTS") != "1":
            self.skipTest("Activa GF_RUN_UI_TESTS=1 para ejecutar pruebas visuales Tkinter")
        import tkinter as tk
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No hay un entorno gráfico disponible: {exc}")
        try:
            root.geometry("700x500+10+10")
            form = tk.Toplevel(root)
            form.geometry("480x360+50+50")
            form.grab_set()
            root.update()
            original_grab = root.grab_current()

            from src.ui.premium import PremiumMessageDialog, PremiumWindow
            message = PremiumMessageDialog(form, "Prueba", "Mensaje de prueba", confirm=True)
            root.update()
            self.assertIs(root.grab_current(), message)
            message.destroy()
            root.update()
            self.assertIs(root.grab_current(), original_grab)

            nested = PremiumWindow(form, "Ventana de prueba", "420x260", modal=True)
            root.update()
            self.assertIs(root.grab_current(), nested)
            nested.destroy()
            root.update()
            self.assertIs(root.grab_current(), original_grab)
        finally:
            root.destroy()

    def test_date_picker_is_visible_in_actual_client_and_rate_dialogs(self):
        import os
        if os.environ.get("GF_RUN_UI_TESTS") != "1":
            self.skipTest("Activa GF_RUN_UI_TESTS=1 para ejecutar pruebas visuales Tkinter")
        import tkinter as tk
        from unittest.mock import patch
        from src.ui.dialogs import ClientDialog, RateDialog, MovementDialog
        try:
            root = tk.Tk()
        except tk.TclError as exc:
            self.skipTest(f"No hay un entorno gráfico disponible: {exc}")
        try:
            root.geometry("900x700+10+10")
            client = ClientDialog(root, lambda: None)
            root.update()
            client_pickers = [
                widget for widget in self._walk_widgets(client)
                if isinstance(widget, DatePickerEntry)
            ]
            self.assertEqual(len(client_pickers), 1)
            client_pickers[0].open_calendar()
            root.update()
            self.assertTrue(client_pickers[0]._popup.winfo_ismapped())
            self.assertIs(root.grab_current(), client)
            client_pickers[0]._close_calendar()
            client.destroy()
            root.update()

            fake_client = {"id": 1, "name": "Cliente de prueba", "current_rate_cents": 2300}
            with patch("src.ui.dialogs.list_clients", return_value=[fake_client]):
                rate = RateDialog(root, lambda: None, initial_client_id=1)
            root.update()
            rate_pickers = [
                widget for widget in self._walk_widgets(rate)
                if isinstance(widget, DatePickerEntry)
            ]
            self.assertEqual(len(rate_pickers), 1)
            rate_pickers[0].open_calendar()
            root.update()
            self.assertTrue(rate_pickers[0]._popup.winfo_ismapped())
            self.assertIs(root.grab_current(), rate)
            rate_pickers[0]._close_calendar()
            rate.destroy()
            root.update()

            with patch("src.ui.dialogs.list_clients", return_value=[fake_client]):
                movement = MovementDialog(root, "income", lambda: None)
            root.update()
            movement_pickers = [
                widget for widget in self._walk_widgets(movement)
                if isinstance(widget, DatePickerEntry)
            ]
            self.assertEqual(len(movement_pickers), 1)
            movement_pickers[0].open_calendar()
            root.update()
            self.assertTrue(movement_pickers[0]._popup.winfo_ismapped())
            self.assertIs(root.grab_current(), movement)
            movement_pickers[0]._close_calendar()
            movement.destroy()
        finally:
            root.destroy()

    @staticmethod
    def _walk_widgets(parent):
        for child in parent.winfo_children():
            yield child
            yield from DatePickerCalendarTests._walk_widgets(child)


if __name__ == "__main__":
    unittest.main()
