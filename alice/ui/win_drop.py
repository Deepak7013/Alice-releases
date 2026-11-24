"""Small Windows WM_DROPFILES adapter used by the Mini ALICE pill.

Dropped paths are reported to the UI only. This module never opens, reads,
copies, executes, or uploads the dropped files.
"""
from __future__ import annotations

import ctypes
import os
from pathlib import Path


def normalize_dropped_paths(paths, *, limit: int = 10) -> list[str]:
    """Return unique existing absolute paths, without following file contents."""
    result = []
    seen = set()
    for raw in list(paths or [])[: max(0, min(int(limit), 50))]:
        try:
            path = Path(str(raw)).expanduser().resolve(strict=True)
        except (OSError, RuntimeError, TypeError, ValueError):
            continue
        key = os.path.normcase(str(path))
        if key in seen or not (path.is_file() or path.is_dir()):
            continue
        seen.add(key)
        result.append(str(path))
    return result


def register_file_drop(hwnd: int, callback):
    """Register WM_DROPFILES on a Tk HWND and return strong callback refs.

    Unsupported platforms and registration failures return ``None`` so the
    rest of the Mini UI remains usable.
    """
    if os.name != "nt" or not hwnd or not callable(callback):
        return None
    try:
        from ctypes import wintypes

        shell32 = ctypes.WinDLL("shell32", use_last_error=True)
        comctl32 = ctypes.WinDLL("comctl32", use_last_error=True)
        LRESULT = ctypes.c_ssize_t
        WPARAM = ctypes.c_size_t
        LPARAM = ctypes.c_ssize_t
        UINT_PTR = ctypes.c_size_t
        DWORD_PTR = ctypes.c_size_t
        SUBCLASSPROC = ctypes.WINFUNCTYPE(
            LRESULT, wintypes.HWND, wintypes.UINT, WPARAM, LPARAM, UINT_PTR, DWORD_PTR
        )
        shell32.DragAcceptFiles.argtypes = [wintypes.HWND, wintypes.BOOL]
        shell32.DragAcceptFiles.restype = None
        shell32.DragQueryFileW.argtypes = [wintypes.HANDLE, wintypes.UINT, wintypes.LPWSTR, wintypes.UINT]
        shell32.DragQueryFileW.restype = wintypes.UINT
        shell32.DragFinish.argtypes = [wintypes.HANDLE]
        shell32.DragFinish.restype = None
        comctl32.DefSubclassProc.argtypes = [wintypes.HWND, wintypes.UINT, WPARAM, LPARAM]
        comctl32.DefSubclassProc.restype = LRESULT
        comctl32.SetWindowSubclass.argtypes = [wintypes.HWND, SUBCLASSPROC, UINT_PTR, DWORD_PTR]
        comctl32.SetWindowSubclass.restype = wintypes.BOOL
        WM_DROPFILES = 0x0233
        subclass_id = 0xA11CE

        def on_message(window, message, wparam, lparam, _subclass, _data):
            if message == WM_DROPFILES:
                handle = wintypes.HANDLE(wparam)
                try:
                    count = shell32.DragQueryFileW(handle, 0xFFFFFFFF, None, 0)
                    paths = []
                    for index in range(min(int(count), 50)):
                        length = shell32.DragQueryFileW(handle, index, None, 0)
                        buffer = ctypes.create_unicode_buffer(int(length) + 1)
                        shell32.DragQueryFileW(handle, index, buffer, len(buffer))
                        paths.append(buffer.value)
                    safe_paths = normalize_dropped_paths(paths)
                    if safe_paths:
                        callback(safe_paths)
                finally:
                    shell32.DragFinish(handle)
                return 0
            return comctl32.DefSubclassProc(window, message, wparam, lparam)

        proc = SUBCLASSPROC(on_message)
        shell32.DragAcceptFiles(hwnd, True)
        if not comctl32.SetWindowSubclass(hwnd, proc, subclass_id, 0):
            shell32.DragAcceptFiles(hwnd, False)
            return None
        return (proc, shell32, comctl32, hwnd, subclass_id)
    except Exception:
        return None
