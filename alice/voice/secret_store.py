"""User-scoped DPAPI storage for the optional Fish Audio credential."""
from __future__ import annotations

import ctypes
import os
import tempfile
from ctypes import wintypes
from pathlib import Path
from typing import Callable


class _DataBlob(ctypes.Structure):
    _fields_ = [("cbData", wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_byte))]


def _dpapi_transform(data: bytes, *, protect: bool) -> bytes:
    if os.name != "nt":
        raise RuntimeError("windows_user_protected_storage_required")
    crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    crypt32.CryptProtectData.argtypes = [
        ctypes.POINTER(_DataBlob), wintypes.LPCWSTR, ctypes.POINTER(_DataBlob),
        wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptProtectData.restype = wintypes.BOOL
    crypt32.CryptUnprotectData.argtypes = [
        ctypes.POINTER(_DataBlob), ctypes.POINTER(wintypes.LPWSTR), ctypes.POINTER(_DataBlob),
        wintypes.LPVOID, wintypes.LPVOID, wintypes.DWORD, ctypes.POINTER(_DataBlob),
    ]
    crypt32.CryptUnprotectData.restype = wintypes.BOOL
    kernel32.LocalFree.argtypes = [wintypes.HLOCAL]
    kernel32.LocalFree.restype = wintypes.HLOCAL
    source_buffer = ctypes.create_string_buffer(data)
    source = _DataBlob(len(data), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_byte)))
    result = _DataBlob()
    description = wintypes.LPWSTR()
    if protect:
        ok = crypt32.CryptProtectData(ctypes.byref(source), "ALICE Fish Audio key", None, None, None, 0x1, ctypes.byref(result))
    else:
        ok = crypt32.CryptUnprotectData(ctypes.byref(source), ctypes.byref(description), None, None, None, 0x1, ctypes.byref(result))
    if not ok:
        raise RuntimeError("windows_user_protected_storage_failed")
    try:
        return ctypes.string_at(result.pbData, result.cbData)
    finally:
        kernel32.LocalFree(result.pbData)
        if description:
            kernel32.LocalFree(description)


class FishAudioSecretStore:
    """Store one API token encrypted for the current Windows user profile.

    The protector hooks are exposed for deterministic unit tests. Production code
    uses Windows DPAPI and never falls back to plaintext storage.
    """

    MAX_BYTES = 16 * 1024

    def __init__(self, path: str | Path, *, protect: Callable[[bytes], bytes] | None = None,
                 unprotect: Callable[[bytes], bytes] | None = None):
        self.path = Path(path)
        self._protect = protect or (lambda value: _dpapi_transform(value, protect=True))
        self._unprotect = unprotect or (lambda value: _dpapi_transform(value, protect=False))

    def has(self) -> bool:
        try:
            return self.path.is_file() and 0 < self.path.stat().st_size <= self.MAX_BYTES
        except OSError:
            return False

    def set(self, secret: str) -> None:
        value = str(secret or "").strip()
        raw = value.encode("utf-8")
        if not raw or len(raw) > self.MAX_BYTES or b"\n" in raw or b"\r" in raw:
            raise ValueError("fish_audio_key_invalid")
        encrypted = self._protect(raw)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=self.path.name + ".", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(encrypted)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def get(self) -> str:
        if not self.has():
            return ""
        try:
            raw = self._unprotect(self.path.read_bytes())
            value = raw.decode("utf-8").strip()
            return value if value and len(raw) <= self.MAX_BYTES else ""
        except Exception:
            return ""

    def delete(self) -> None:
        try:
            self.path.unlink(missing_ok=True)
        except OSError as exc:
            raise RuntimeError("fish_audio_key_remove_failed") from exc
