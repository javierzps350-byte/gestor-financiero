# Windows native non-client frame integration for the custom Tk title bar.
from __future__ import annotations

import ctypes
import sys
import tkinter as tk


class NativeWindowChrome:
    """Remove the Windows caption but preserve a normal, resizable HWND."""

    GWL_STYLE = -16
    WS_CAPTION = 0x00C00000
    WS_THICKFRAME = 0x00040000
    WS_SYSMENU = 0x00080000
    WS_MINIMIZEBOX = 0x00020000
    WS_MAXIMIZEBOX = 0x00010000
    SWP_NOSIZE = 0x0001
    SWP_NOMOVE = 0x0002
    SWP_NOZORDER = 0x0004
    SWP_NOACTIVATE = 0x0010
    SWP_FRAMECHANGED = 0x0020
    GA_ROOT = 2
    WM_NCLBUTTONDOWN = 0x00A1
    HTCAPTION = 2

    def __init__(self, root: tk.Tk):
        self.root = root
        self.hwnd = None
        self.installed = False
        self._user32 = None

    def install(self) -> bool:
        if sys.platform != "win32":
            return False
        try:
            self.root.update_idletasks()
            self._user32 = ctypes.windll.user32
            self._user32.GetAncestor.restype = ctypes.c_void_p
            self._user32.GetAncestor.argtypes = [ctypes.c_void_p, ctypes.c_uint]
            self.hwnd = self._user32.GetAncestor(
                ctypes.c_void_p(self.root.winfo_id()), self.GA_ROOT
            )
            if not self.hwnd:
                self.hwnd = ctypes.c_void_p(self.root.winfo_id())

            if ctypes.sizeof(ctypes.c_void_p) == 8:
                get_long = self._user32.GetWindowLongPtrW
                set_long = self._user32.SetWindowLongPtrW
                long_type = ctypes.c_ssize_t
            else:
                get_long = self._user32.GetWindowLongW
                set_long = self._user32.SetWindowLongW
                long_type = ctypes.c_long
            get_long.restype = long_type
            get_long.argtypes = [ctypes.c_void_p, ctypes.c_int]
            set_long.restype = long_type
            set_long.argtypes = [ctypes.c_void_p, ctypes.c_int, long_type]

            self._user32.SetWindowPos.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                ctypes.c_uint,
            ]
            self._user32.SetWindowPos.restype = ctypes.c_int
            style = int(get_long(self.hwnd, self.GWL_STYLE))
            style &= ~self.WS_CAPTION
            style |= self.WS_THICKFRAME | self.WS_SYSMENU | self.WS_MINIMIZEBOX | self.WS_MAXIMIZEBOX
            set_long(self.hwnd, self.GWL_STYLE, style)
            self._user32.SetWindowPos(
                self.hwnd, None, 0, 0, 0, 0,
                self.SWP_NOMOVE | self.SWP_NOSIZE | self.SWP_NOZORDER
                | self.SWP_NOACTIVATE | self.SWP_FRAMECHANGED,
            )
            self._apply_dwm_corners()
            self.installed = True
            return True
        except (AttributeError, OSError, TypeError, tk.TclError):
            self.installed = False
            return False

    def _apply_dwm_corners(self) -> None:
        try:
            dwmapi = ctypes.windll.dwmapi
            preference = ctypes.c_int(2)  # DWMWCP_ROUND
            dwmapi.DwmSetWindowAttribute(
                ctypes.c_void_p(self.hwnd), 33,
                ctypes.byref(preference), ctypes.sizeof(preference),
            )
        except (AttributeError, OSError):
            pass

    def begin_drag(self) -> None:
        if sys.platform != "win32" or not self.installed or not self.hwnd:
            return
        try:
            self._user32.ReleaseCapture()
            self._user32.SendMessageW.argtypes = [
                ctypes.c_void_p, ctypes.c_uint, ctypes.c_size_t, ctypes.c_ssize_t
            ]
            self._user32.SendMessageW.restype = ctypes.c_ssize_t
            self._user32.SendMessageW(
                ctypes.c_void_p(self.hwnd), self.WM_NCLBUTTONDOWN,
                self.HTCAPTION, 0,
            )
        except (AttributeError, OSError):
            pass
