"""Lightweight persistent themes for the Tkinter application."""
from __future__ import annotations

import json
from pathlib import Path
from tkinter import ttk

from src.config import DATA_DIR

THEMES = {
    "claro": {
        "label": "Claro premium",
        "bg": "#F2F6FA", "panel": "#FFFFFF", "panel_alt": "#EEF3F7",
        "text": "#243449", "muted": "#8190A2", "accent": "#2BAE9B",
        "accent_hover": "#239987", "expense": "#E9897D", "expense_hover": "#D9786D",
        "border": "#E1E8EF", "selected": "#D9F0EC", "table_header": "#F3F6F9",
        "grid": "#E9EEF4", "shadow": "#D8E1EA", "input": "#FFFFFF",
        "sidebar": "#FFFFFF", "success": "#208F7E", "danger": "#D9776B",
    },
    "suave": {
        "label": "Gris suave",
        "bg": "#E9E9E6", "panel": "#F7F7F4", "panel_alt": "#E3E5E2",
        "text": "#303A43", "muted": "#78838B", "accent": "#538F87",
        "accent_hover": "#427D75", "expense": "#C17D72", "expense_hover": "#AC6A60",
        "border": "#D6DAD7", "selected": "#D9E7E2", "table_header": "#ECEDEA",
        "grid": "#E0E3DF", "shadow": "#D0D4D0", "input": "#FAFAF8",
        "sidebar": "#F5F5F1", "success": "#477F73", "danger": "#B96E64",
    },
    "oscuro": {
        "label": "Oscuro elegante",
        "bg": "#111923", "panel": "#1B2632", "panel_alt": "#253342",
        "text": "#E7EDF4", "muted": "#9AAABD", "accent": "#59C5AF",
        "accent_hover": "#43AC98", "expense": "#E58F85", "expense_hover": "#D47B72",
        "border": "#2B3A49", "selected": "#29443F", "table_header": "#23303D",
        "grid": "#2A3947", "shadow": "#0B1118", "input": "#202D3A",
        "sidebar": "#17222D", "success": "#64C5AD", "danger": "#E58F85",
    },
}

DEFAULT_THEME = "claro"

# Translate the original v0.3.0 palette and its small set of utility colors.
_BASE_COLOR_ROLES = {
    "#F2F6FA": "bg", "#F3F6F9": "table_header", "#FFFFFF": "panel",
    "#EEF3F7": "panel_alt", "#243449": "text", "#8190A2": "muted",
    "#2BAE9B": "accent", "#239987": "accent_hover", "#E9897D": "expense",
    "#E1E8EF": "border", "#D9F0EC": "selected", "#E9EEF4": "grid",
    "#D8E1EA": "shadow", "#DAE3EC": "border", "#F0F4F7": "panel_alt",
    "#F0F3F6": "panel_alt", "#E4EDF4": "panel_alt", "#E7EDF3": "border",
    "#EAF5F3": "selected", "#E5F4F1": "selected", "#F1F7F6": "selected",
    "#EAF0F5": "panel_alt", "#E0EAF1": "panel_alt", "#DFE7EF": "border",
    "#748398": "muted", "#8290A1": "muted", "#8995A7": "muted",
    "#A5AFBA": "muted", "#99A5B3": "muted", "#718096": "muted",
    "#657489": "muted", "#AAB4BF": "muted", "#A0AAB7": "muted",
    "#208F7E": "success", "#238F80": "success", "#208E80": "success",
    "#D9776B": "danger", "#D9786D": "expense_hover",
    "#E8BA68": "expense", "#E8B765": "expense", "#D5DDE6": "border",
}


def _role_for_color(value: str):
    color = str(value).upper()
    role = _BASE_COLOR_ROLES.get(color)
    if role:
        return role
    # Allow switching repeatedly among presets: colors from every preset map
    # back to their semantic token before applying the next palette.
    for theme in THEMES.values():
        for theme_role, theme_color in theme.items():
            if theme_color.upper() == color:
                return theme_role
    return None


class ThemeManager:
    def __init__(self):
        self.settings_path = DATA_DIR / "ui_preferences.json"
        self.theme_id = self._load_theme()
        self.palette = THEMES[self.theme_id]

    def _load_theme(self) -> str:
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            theme_id = data.get("theme")
            return theme_id if theme_id in THEMES else DEFAULT_THEME
        except (OSError, ValueError, TypeError):
            return DEFAULT_THEME

    def save(self) -> None:
        self.settings_path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.settings_path.with_suffix(".tmp")
        temporary.write_text(json.dumps({"theme": self.theme_id}, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.settings_path)

    def set_theme(self, theme_id: str) -> None:
        if theme_id not in THEMES:
            raise ValueError("El tema seleccionado no existe.")
        self.theme_id = theme_id
        self.palette = THEMES[theme_id]
        self.save()

    def configure_styles(self, root) -> None:
        p = self.palette
        style = ttk.Style(root)
        style.theme_use("clam")
        style.configure("TFrame", background=p["bg"])
        style.configure("Panel.TFrame", background=p["panel"])
        style.configure("TLabel", background=p["bg"], foreground=p["text"], font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=p["bg"], foreground=p["muted"], font=("Segoe UI", 9))
        style.configure("Panel.TLabel", background=p["panel"], foreground=p["text"], font=("Segoe UI", 10))
        style.configure("Toolbar.TLabel", background=p["panel"], foreground=p["muted"], font=("Segoe UI", 9))
        style.configure("DialogTitle.TLabel", background=p["bg"], foreground=p["text"], font=("Segoe UI", 19, "bold"))
        style.configure("Hint.TLabel", background=p["bg"], foreground=p["muted"], font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=p["bg"], foreground=p["text"], font=("Segoe UI", 21, "bold"))
        style.configure("SubTitle.TLabel", background=p["bg"], foreground=p["muted"], font=("Segoe UI", 9))
        # A restrained visual system shared by every form and filter.
        style.configure(
            "TButton", font=("Segoe UI", 9), padding=(15, 9),
            background=p["panel_alt"], foreground=p["text"],
            borderwidth=0, relief="flat", focusthickness=0,
        )
        style.map(
            "TButton",
            background=[("pressed", p["border"]), ("active", p["selected"]), ("disabled", p["panel_alt"])],
            foreground=[("disabled", p["muted"])],
        )
        style.configure(
            "Accent.TButton", background=p["accent"], foreground=p["panel"],
            font=("Segoe UI", 9, "bold"), padding=(17, 10), borderwidth=0,
            relief="flat", focusthickness=0,
        )
        style.map("Accent.TButton", background=[("pressed", p["accent_hover"]), ("active", p["accent_hover"])])
        style.configure(
            "Quiet.TButton", background=p["panel"], foreground=p["muted"],
            font=("Segoe UI", 9, "bold"), padding=(12, 8), borderwidth=0,
            relief="flat", focusthickness=0,
        )
        style.map("Quiet.TButton", background=[("active", p["panel_alt"])], foreground=[("active", p["text"])])
        style.configure(
            "TEntry", fieldbackground=p["input"], foreground=p["text"],
            insertcolor=p["text"], bordercolor=p["border"], lightcolor=p["border"],
            darkcolor=p["border"], padding=(12, 9), borderwidth=1,
            relief="flat", font=("Segoe UI", 10),
        )
        style.map(
            "TEntry", fieldbackground=[("disabled", p["panel_alt"])],
            bordercolor=[("focus", p["accent"]), ("!focus", p["border"])],
            lightcolor=[("focus", p["accent"]), ("!focus", p["border"])],
            darkcolor=[("focus", p["accent"]), ("!focus", p["border"])],
        )
        # The down-arrow element is intentionally omitted. The standard ttk
        # combobox binding opens the popdown when any part of this field is
        # clicked, keeping the control compact and visually contemporary.
        style.layout("Elegant.TCombobox", [
            ("Combobox.field", {"sticky": "nswe", "children": [
                ("Combobox.padding", {"sticky": "nswe", "children": [
                    ("Combobox.textarea", {"sticky": "nswe"}),
                ]}),
            ]}),
        ])
        style.configure(
            "Elegant.TCombobox", fieldbackground=p["input"], background=p["input"],
            foreground=p["text"], bordercolor=p["border"], lightcolor=p["border"],
            darkcolor=p["border"], padding=(12, 9), borderwidth=1,
            relief="flat", font=("Segoe UI", 10),
        )
        style.map(
            "Elegant.TCombobox",
            fieldbackground=[("readonly", p["input"]), ("disabled", p["panel_alt"])],
            foreground=[("readonly", p["text"]), ("disabled", p["muted"])],
            bordercolor=[("focus", p["accent"]), ("!focus", p["border"])],
            lightcolor=[("focus", p["accent"]), ("!focus", p["border"])],
            darkcolor=[("focus", p["accent"]), ("!focus", p["border"])],
        )
        style.configure("TCheckbutton", background=p["bg"], foreground=p["text"], font=("Segoe UI", 9), padding=(3, 5))
        style.map("TCheckbutton", background=[("active", p["bg"])], foreground=[("disabled", p["muted"])])
        style.layout("Treeview", [("Treeview.treearea", {"sticky": "nswe"})])
        style.configure("Treeview", background=p["panel"], fieldbackground=p["panel"], foreground=p["text"], rowheight=34, borderwidth=0, relief="flat", font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background=p["table_header"], foreground=p["muted"], relief="flat", borderwidth=0, font=("Segoe UI", 8, "bold"), padding=(12, 11))
        style.map("Treeview", background=[("selected", p["selected"])], foreground=[("selected", p["text"])])
        style.layout("Vertical.TScrollbar", [("Vertical.Scrollbar.trough", {"sticky": "ns", "children": [("Vertical.Scrollbar.thumb", {"sticky": "nswe"})]})])
        style.layout("Horizontal.TScrollbar", [("Horizontal.Scrollbar.trough", {"sticky": "we", "children": [("Horizontal.Scrollbar.thumb", {"sticky": "nswe"})]})])
        style.configure("TScrollbar", background=p["panel_alt"], troughcolor=p["bg"], bordercolor=p["bg"], arrowcolor=p["muted"], width=10)

    def recolor_tree(self, widget) -> None:
        """Recolor classic Tk widgets using semantic roles from their current colors."""
        p = self.palette
        try:
            keys = set(widget.keys())
            updates = {}

            # Tk exposes aliases such as bg/background and fg/foreground.
            # Configure only one alias per setting to avoid Tcl rejecting the pair.
            background_key = next((key for key in ("background", "bg") if key in keys), None)
            foreground_key = next((key for key in ("foreground", "fg") if key in keys), None)
            if background_key:
                role = _role_for_color(widget.cget(background_key))
                if role:
                    updates[background_key] = p[role]
            if foreground_key:
                role = _role_for_color(widget.cget(foreground_key))
                if role:
                    updates[foreground_key] = p[role]

            for option in ("activebackground", "highlightbackground", "troughcolor", "insertbackground", "selectbackground"):
                if option in keys:
                    role = _role_for_color(widget.cget(option))
                    if role:
                        updates[option] = p[role]
            for option in ("activeforeground", "disabledforeground", "insertcolor", "selectforeground"):
                if option in keys:
                    role = _role_for_color(widget.cget(option))
                    if role:
                        updates[option] = p[role]

            for option, value in updates.items():
                try:
                    widget.configure(**{option: value})
                except Exception:
                    pass
        except Exception:
            pass
        try:
            children = widget.winfo_children()
        except Exception:
            children = []
        for child in children:
            self.recolor_tree(child)

    def apply(self, root, charts=()) -> None:
        root.configure(bg=self.palette["bg"])
        self.configure_styles(root)
        self.recolor_tree(root)
        for chart in charts:
            try:
                chart.set_theme(self.palette)
            except Exception:
                pass
