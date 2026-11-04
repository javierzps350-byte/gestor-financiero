import json
import tempfile
import unittest
from pathlib import Path

from src.ui.date_picker import month_weeks
from src.ui.theme_manager import THEMES, ThemeManager, _role_for_color


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


if __name__ == "__main__":
    unittest.main()
