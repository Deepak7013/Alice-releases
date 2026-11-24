"""Alice package entry point.

Production launches are anchored to the installed package directory so the
configuration and persistent state do not depend on the caller's current
working directory. A Windows named mutex prevents duplicate UI processes.
"""
from __future__ import annotations

import ctypes
import os
import sys
from pathlib import Path

_LOCK_HANDLE = None

_ROOT = Path(__file__).resolve().parent.parent
_MUTEX_HANDLE = None


def _is_alice_window_title(title: str) -> bool:
    """Recognize current ALICE captions and older Gluttony window titles."""
    normalized = str(title or "").strip().lower()
    return normalized.startswith((
        "alice — alice ", "alice - alice ",
        "alice — gluttony", "alice - gluttony",
    ))


def _acquire_exclusive_lock() -> bool:
    """Acquire a per-user Windows file lock in addition to the named mutex.

    The lock is shared by all ALICE releases for this Windows user, including
    launches that come from older installers. The OS owns the handle, so it is
    released automatically if the process exits or crashes.
    """
    global _LOCK_HANDLE
    if os.name != "nt":
        return True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        appdata = os.environ.get("LOCALAPPDATA") or str(Path.home())
        lock_dir = Path(appdata) / "ALICE"
        lock_dir.mkdir(parents=True, exist_ok=True)
        lock_path = lock_dir / "alice-ui.lock"
        GENERIC_READ = 0x80000000
        GENERIC_WRITE = 0x40000000
        OPEN_ALWAYS = 4
        FILE_ATTRIBUTE_NORMAL = 0x80
        handle = kernel32.CreateFileW(str(lock_path), GENERIC_READ | GENERIC_WRITE, 0, None, OPEN_ALWAYS, FILE_ATTRIBUTE_NORMAL, None)
        invalid = ctypes.c_void_p(-1).value
        if handle in (0, invalid):
            return False
        _LOCK_HANDLE = handle
        return True
    except Exception:
        return True


def _prepare_runtime() -> None:
    os.chdir(_ROOT)
    try:
        from dotenv import load_dotenv
        env_file = _ROOT / ".env"
        if env_file.exists():
            # The installation's .env is authoritative. This also prevents
            # stale ALICE_* variables from a previous launcher/session from
            # silently overriding the user's current configuration.
            load_dotenv(env_file, override=True)
    except Exception:
        # Router-level configuration remains the final fallback.
        pass


def _activate_existing_window() -> None:
    if os.name != "nt":
        return
    try:
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_long)

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
                user32.ShowWindow(hwnd, 9)  # SW_RESTORE
                try:
                    user32.SetForegroundWindow(hwnd)
                except Exception:
                    pass
                return False
            return True

        user32.EnumWindows(WNDENUMPROC(callback), 0)
    except Exception:
        pass


def _acquire_single_instance() -> bool:
    """Return True when this process owns the ALICE UI mutex."""
    global _MUTEX_HANDLE
    if os.name != "nt":
        return True
    try:
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        name = r"Global\ALICE_GLUTTONY_UI_V3128"
        handle = kernel32.CreateMutexW(None, False, name)
        if not handle:
            return True
        already = ctypes.get_last_error() == 183  # ERROR_ALREADY_EXISTS
        if already:
            kernel32.CloseHandle(handle)
            return False
        _MUTEX_HANDLE = handle
        return True
    except Exception:
        # Never make Alice unusable because a platform mutex API is unavailable.
        return True


def _find_any_alice_window() -> bool:
    if os.name != "nt":
        return False
    found = False
    try:
        user32 = ctypes.windll.user32
        WNDENUMPROC = ctypes.WINFUNCTYPE(ctypes.c_bool, ctypes.c_void_p, ctypes.c_long)
        def callback(hwnd, _lparam):
            nonlocal found
            if not user32.IsWindow(hwnd): return True
            length=user32.GetWindowTextLengthW(hwnd)
            if length <= 0: return True
            buf=ctypes.create_unicode_buffer(length+1); user32.GetWindowTextW(hwnd,buf,length+1)
            title=buf.value.strip().lower()
            if _is_alice_window_title(title):
                found=True; return False
            return True
        user32.EnumWindows(WNDENUMPROC(callback),0)
    except Exception:
        return False
    return found


def main():
    _prepare_runtime()
    if os.name == "nt" and _find_any_alice_window():
        if "--show" in sys.argv:
            _activate_existing_window()
        return 0
    # Two independent OS-level guards prevent duplicate ALICE UI processes:
    # the named mutex handles normal launches and the exclusive lock also
    # covers legacy/direct launcher paths across side-by-side installations.
    if not _acquire_single_instance() or not _acquire_exclusive_lock():
        if "--show" in sys.argv:
            _activate_existing_window()
        return 0

    if "--hidden" in sys.argv:
        os.environ["ALICE_START_HIDDEN"] = "1"
    elif "--show" in sys.argv:
        os.environ["ALICE_START_HIDDEN"] = "0"
    from .ui.app import main as run_ui
    run_ui()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
