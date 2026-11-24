"""Small native-control adapters for ALICE's Windows Tk interface.

Tk's painted entry and menu button are exposed as generic panes. Standard
Windows controls provide their own stable UI Automation providers, so the main
message entry is mirrored into a native EDIT control and the Tools menu uses a
standard button. Existing ALICE callbacks remain the source of behavior.
"""
from __future__ import annotations

import ctypes
import os
from ctypes import wintypes


def set_native_accessible_name(widget, name: str) -> bool:
    """Set the name read by the native Windows provider for a Tk HWND.

    Tk's Windows Button HWNDs already implement UI Automation; their caption
    just needs to be synchronized with the visible Tk caption.
    """
    if os.name != "nt":
        return False
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)
        set_text = user32.SetWindowTextW
        set_text.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
        set_text.restype = wintypes.BOOL
        return bool(set_text(int(widget.winfo_id()), str(name)))
    except Exception:
        return False


class WindowsAccessibleEntry:
    """Expose a labeled standard Windows EDIT control over ALICE's Tk entry."""

    CONTROL_ID = 8101
    LABEL_ID = 8100

    def __init__(self, root, parent, anchor, on_submit, accessible_label="Message:"):
        self.root = root
        self.parent = parent
        self.anchor = anchor
        self.on_submit = on_submit
        self.accessible_label = str(accessible_label or "")[:80]
        self.available = False
        self.error = ""
        self.hwnd = 0
        self.label_hwnd = 0
        self._font = 0
        self._wndproc = None
        self._old_wndproc = 0
        self._tk_binding = None
        if os.name == "nt":
            self._create()

    def _create(self):
        try:
            self.user32 = ctypes.WinDLL("user32", use_last_error=True)
            self.gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
            self._send_message = self.user32.SendMessageW
            self._send_message.argtypes = [wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_ssize_t]
            self._send_message.restype = ctypes.c_ssize_t
            self.user32.DestroyWindow.argtypes = [wintypes.HWND]
            self.user32.DestroyWindow.restype = wintypes.BOOL
            self.user32.SetFocus.argtypes = [wintypes.HWND]
            self.user32.SetFocus.restype = wintypes.HWND
            self.user32.SetWindowTextW.argtypes = [wintypes.HWND, wintypes.LPCWSTR]
            self.user32.SetWindowTextW.restype = wintypes.BOOL
            self.gdi32.CreateFontW.argtypes = [
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                wintypes.DWORD, wintypes.DWORD, wintypes.DWORD, wintypes.DWORD,
                wintypes.LPCWSTR,
            ]
            self.gdi32.CreateFontW.restype = wintypes.HFONT
            self.gdi32.DeleteObject.argtypes = [wintypes.HGDIOBJ]
            self.gdi32.DeleteObject.restype = wintypes.BOOL
            create = self.user32.CreateWindowExW
            create.argtypes = [
                wintypes.DWORD, wintypes.LPCWSTR, wintypes.LPCWSTR, wintypes.DWORD,
                ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                wintypes.HWND, wintypes.HMENU, wintypes.HINSTANCE, wintypes.LPVOID,
            ]
            create.restype = wintypes.HWND
            self._set_window_pos = self.user32.SetWindowPos
            self._set_window_pos.argtypes = [
                wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
                ctypes.c_int, ctypes.c_int, wintypes.UINT,
            ]
            self._set_window_pos.restype = wintypes.BOOL

            parent_hwnd = int(self.parent.winfo_id())
            self.label_hwnd = int(create(
                0x00000020, "STATIC", self.accessible_label,
                0x40000000 | 0x10000000 | 0x00000200,
                0, 0, 1, 1, parent_hwnd, self.LABEL_ID, None, None,
            ) or 0)
            self.hwnd = int(create(
                0x00000200, "EDIT", "",
                0x40000000 | 0x10000000 | 0x00010000 | 0x00000080,
                0, 0, 1, 1, parent_hwnd, self.CONTROL_ID, None, None,
            ) or 0)
            if not self.label_hwnd or not self.hwnd:
                raise ctypes.WinError(ctypes.get_last_error())

            self._font = int(self.gdi32.CreateFontW(
                -16, 0, 0, 0, 400, 0, 0, 0, 1, 0, 0, 5, 0, "Segoe UI",
            ) or 0)
            if self._font:
                self._send_message(self.label_hwnd, 0x0030, self._font, 1)
                self._send_message(self.hwnd, 0x0030, self._font, 1)

            self._install_enter_handler()
            self._tk_binding = self.parent.bind("<Configure>", self._on_parent_resize, add="+")
            self.parent.update_idletasks()
            self.sync_bounds()
            self.available = True
        except Exception as exc:
            self.error = f"{type(exc).__name__}: {exc}"
            self.close()

    def _install_enter_handler(self):
        wndproc_type = ctypes.WINFUNCTYPE(
            ctypes.c_ssize_t, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_ssize_t,
        )
        self._call_window_proc = self.user32.CallWindowProcW
        self._call_window_proc.argtypes = [
            ctypes.c_void_p, wintypes.HWND, wintypes.UINT, wintypes.WPARAM, ctypes.c_ssize_t,
        ]
        self._call_window_proc.restype = ctypes.c_ssize_t
        if ctypes.sizeof(ctypes.c_void_p) == 8:
            get_proc = self.user32.GetWindowLongPtrW
            set_proc = self.user32.SetWindowLongPtrW
        else:
            get_proc = self.user32.GetWindowLongW
            set_proc = self.user32.SetWindowLongW
        get_proc.argtypes = [wintypes.HWND, ctypes.c_int]
        get_proc.restype = ctypes.c_void_p
        set_proc.argtypes = [wintypes.HWND, ctypes.c_int, ctypes.c_void_p]
        set_proc.restype = ctypes.c_void_p
        old = int(get_proc(self.hwnd, -4) or 0)
        if not old:
            raise ctypes.WinError(ctypes.get_last_error())

        def edit_proc(hwnd, message, wparam, lparam):
            if message == 0x0100 and int(wparam) == 0x0D:  # WM_KEYDOWN / VK_RETURN
                self.root.after_idle(self.on_submit)
                return 0
            return self._call_window_proc(old, hwnd, message, wparam, lparam)

        self._wndproc = wndproc_type(edit_proc)
        if not set_proc(self.hwnd, -4, ctypes.cast(self._wndproc, ctypes.c_void_p)):
            raise ctypes.WinError(ctypes.get_last_error())
        self._old_wndproc = old
        self._set_window_proc = set_proc

    def _on_parent_resize(self, _event=None):
        try:
            self.root.after_idle(self.sync_bounds)
        except Exception:
            self.sync_bounds()

    def sync_bounds(self):
        if not self.hwnd or not self.label_hwnd:
            return
        try:
            x = int(self.anchor.winfo_x())
            y = int(self.anchor.winfo_y())
            width = int(self.anchor.winfo_width())
            height = int(self.anchor.winfo_height())
            label_width = 76
            flags = 0x0004 | 0x0010  # SWP_NOZORDER | SWP_NOACTIVATE
            self._set_window_pos(self.label_hwnd, 0, x, y, label_width, height, flags)
            self._set_window_pos(self.hwnd, 0, x + label_width, y,
                                 max(24, width - label_width), height, flags)
        except Exception:
            pass

    def get_value(self) -> str:
        if not self.hwnd:
            return ""
        length = int(self._send_message(self.hwnd, 0x000E, 0, 0))  # WM_GETTEXTLENGTH
        buffer = ctypes.create_unicode_buffer(max(1, length + 1))
        self._send_message(self.hwnd, 0x000D, len(buffer), ctypes.cast(buffer, ctypes.c_void_p).value)
        return buffer.value

    def has_focus(self) -> bool:
        """Return whether keyboard input is currently going to the native edit.

        Tk has a backing Entry for layout and non-Windows fallback. On Windows,
        keyboard input may instead go to this native EDIT. The backing Entry can
        therefore be stale (often empty); callers must not replace a visible Tk
        draft with an empty native value unless this edit is the active source.
        """
        if not self.hwnd:
            return False
        try:
            get_focus = self.user32.GetFocus
            get_focus.argtypes = []
            get_focus.restype = wintypes.HWND
            return int(get_focus() or 0) == self.hwnd
        except Exception:
            return False

    def set_value(self, value: str) -> None:
        if self.hwnd:
            self.user32.SetWindowTextW(self.hwnd, str(value))

    def focus_set(self) -> None:
        if self.hwnd:
            self.user32.SetFocus(self.hwnd)
        else:
            self.anchor.focus_set()

    def close(self):
        try:
            if self._old_wndproc and getattr(self,"_set_window_proc",None) and self.hwnd:
                self._set_window_proc(self.hwnd, -4, ctypes.c_void_p(self._old_wndproc))
        except Exception:
            pass
        self._old_wndproc = 0
        for hwnd in (self.hwnd, self.label_hwnd):
            try:
                if hwnd and self.user32:
                    self.user32.DestroyWindow(hwnd)
            except Exception:
                pass
        self.hwnd = 0
        self.label_hwnd = 0
        try:
            if self._font and self.gdi32:
                self.gdi32.DeleteObject(self._font)
        except Exception:
            pass
        self._font = 0
        self.available = False
