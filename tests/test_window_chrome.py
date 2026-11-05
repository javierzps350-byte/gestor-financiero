import unittest
from unittest.mock import patch

from src.ui.window_chrome import NativeWindowChrome


class NativeWindowChromeTests(unittest.TestCase):
    def test_install_is_noop_outside_windows(self):
        class DummyRoot:
            def update_idletasks(self):
                raise AssertionError("No debe tocar Tk fuera de Windows")

        chrome = NativeWindowChrome(DummyRoot())
        with patch("src.ui.window_chrome.sys.platform", "linux"):
            self.assertFalse(chrome.install())
        self.assertFalse(chrome.installed)

    def test_native_resize_and_system_buttons_are_preserved(self):
        self.assertTrue(NativeWindowChrome.WS_THICKFRAME)
        self.assertTrue(NativeWindowChrome.WS_SYSMENU)
        self.assertTrue(NativeWindowChrome.WS_MINIMIZEBOX)
        self.assertTrue(NativeWindowChrome.WS_MAXIMIZEBOX)
        self.assertTrue(NativeWindowChrome.SWP_FRAMECHANGED)
