"""Persistent Windows launcher for Alice's Ctrl+Alt+A control.

This tiny process remains alive when Alice's main UI is shut down. It owns the
hotkey, so Ctrl+Alt+A can reliably start Alice again even when Alice herself is
not running. When Alice is running, the same hotkey toggles her main window.
"""
from __future__ import annotations
import ctypes
import os
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

MOD_ALT = 0x0001
MOD_CONTROL = 0x0002
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
SW_HIDE = 0
SW_SHOW = 5
SW_RESTORE = 9


def _is_alice_window_title(title: str) -> bool:
    """Recognize current ALICE captions plus the legacy Gluttony caption."""
    normalized = str(title or "").strip().lower()
    return normalized.startswith((
        "alice — alice ", "alice - alice ",
        "alice — gluttony", "alice - gluttony",
    ))


def _root() -> Path:
    return Path(__file__).resolve().parents[2]


def _pythonw() -> Path:
    root = _root()
    candidate = root / ".venv" / "Scripts" / "pythonw.exe"
    return candidate if candidate.exists() else Path(sys.executable)


def _find_alice_window():
    """Return the first top-level Alice window handle, if present."""
    user32 = ctypes.windll.user32
    matches = []
    WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, wintypes.HWND, wintypes.LPARAM)

    def callback(hwnd, _lparam):
        if not user32.IsWindow(hwnd):
            return True
        length = user32.GetWindowTextLengthW(hwnd)
        if length <= 0:
            return True
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value.strip().lower()
        if _is_alice_window_title(title):
            matches.append(hwnd)
            return False
        return True

    user32.EnumWindows(WNDENUMPROC(callback), 0)
    return matches[0] if matches else None


def _toggle_or_start():
    user32 = ctypes.windll.user32
    hwnd = _find_alice_window()
    if hwnd:
        visible = bool(user32.IsWindowVisible(hwnd))
        # IsWindowVisible remains true for minimized top-level windows. Treat
        # those as hidden from the user's perspective and restore them on the
        # first hotkey press instead of hiding them again.
        minimized = bool(user32.IsIconic(hwnd))
        if visible and not minimized:
            user32.ShowWindow(hwnd, SW_HIDE)
        else:
            user32.ShowWindow(hwnd, SW_RESTORE)
            user32.ShowWindow(hwnd, SW_SHOW)
            try:
                user32.SetForegroundWindow(hwnd)
            except Exception:
                pass
        return "toggled"
    py = _pythonw()
    if not py.exists():
        return "pythonw-missing"
    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    subprocess.Popen([str(py), "-m", "alice", "--show"], cwd=str(_root()), creationflags=flags)
    return "started"


def _already_running():
    """Use a named Windows mutex so duplicate launcher tasks do not stack."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    name = "Global\\ALICE_GLUTTONY_CTRL_ALT_A_LAUNCHER_V3124"
    handle = kernel32.CreateMutexW(None, False, name)
    if not handle:
        return False, None
    already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
    return already, handle


def _poll_hotkey(stop_event):
    """Fallback when RegisterHotKey is unavailable/occupied."""
    user32 = ctypes.windll.user32
    CTRL = 0x11
    ALT = 0x12
    A = 0x41
    was_down = False
    while not stop_event.is_set():
        down = bool(user32.GetAsyncKeyState(CTRL) & 0x8000) and bool(user32.GetAsyncKeyState(ALT) & 0x8000) and bool(user32.GetAsyncKeyState(A) & 0x8000)
        if down and not was_down:
            try:
                _toggle_or_start()
            except Exception:
                pass
        was_down = down
        time.sleep(0.035)


def main():
    if os.name != "nt":
        return 0
    already, mutex = _already_running()
    if already:
        return 0
    user32 = ctypes.windll.user32
    hotkey_id = 0xA11CE
    registered = bool(user32.RegisterHotKey(None, hotkey_id, MOD_CONTROL | MOD_ALT | MOD_NOREPEAT, ord("A")))
    if registered:
        try:
            # Start Alice quietly at logon. If already running, do nothing.
            if _find_alice_window() is None:
                py = _pythonw()
                if py.exists():
                    flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
                    subprocess.Popen([str(py), "-m", "alice", "--hidden"], cwd=str(_root()), creationflags=flags)
            msg = wintypes.MSG()
            while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) > 0:
                if msg.message == WM_HOTKEY and msg.wParam == hotkey_id:
                    try:
                        _toggle_or_start()
                    except Exception:
                        pass
        finally:
            try:
                user32.UnregisterHotKey(None, hotkey_id)
            except Exception:
                pass
            if mutex:
                try:
                    user32.CloseHandle(mutex)
                except Exception:
                    pass
        return 0

    # If another application owns Ctrl+Alt+A, retain the same user experience
    # with a tiny low-frequency key-state fallback instead of silently failing.
    import threading
    stop = threading.Event()
    try:
        _poll_hotkey(stop)
    finally:
        stop.set()
        if mutex:
            try:
                user32.CloseHandle(mutex)
            except Exception:
                pass
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
