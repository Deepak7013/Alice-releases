"""Per-user DPAPI-protected remote companion keys for Windows hosts."""

from __future__ import annotations

import base64
import ctypes
import json
import os
import secrets
import tempfile
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable


# Pairing only grants operations with a concrete runtime handler in this build.
ALLOWED_SCOPES = frozenset({"chat", "status.read", "email.read", "email.draft"})
_MAGIC = b"ALICE-DPAPI-PAIRING-v1\n"
_MAX_CLIENTS = 1  # Multi-client dispatch is intentionally not enabled yet.


@dataclass(frozen=True)
class PairingGrant:
    client_id: str
    scopes: frozenset[str]
    secret_for_pairing: str = field(repr=False)


@dataclass(frozen=True)
class PairedClient:
    client_id: str
    label: str
    scopes: frozenset[str]
    created_at: float


@dataclass(frozen=True)
class PairingCredential:
    client: PairedClient
    secret: bytes = field(repr=False)


class DPAPIProtector:
    """Use Windows user-scope DPAPI; never fall back to plaintext storage."""

    @staticmethod
    def _api():
        if os.name != "nt":
            raise OSError("Windows DPAPI is required for remote pairing secrets")
        crypt32 = ctypes.WinDLL("crypt32", use_last_error=True)
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        class DATA_BLOB(ctypes.Structure):
            _fields_ = [("cbData", ctypes.c_ulong), ("pbData", ctypes.POINTER(ctypes.c_ubyte))]

        crypt32.CryptProtectData.argtypes = [
            ctypes.POINTER(DATA_BLOB), ctypes.c_wchar_p, ctypes.POINTER(DATA_BLOB),
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(DATA_BLOB),
        ]
        crypt32.CryptProtectData.restype = ctypes.c_int
        crypt32.CryptUnprotectData.argtypes = [
            ctypes.POINTER(DATA_BLOB), ctypes.POINTER(ctypes.c_wchar_p), ctypes.POINTER(DATA_BLOB),
            ctypes.c_void_p, ctypes.c_void_p, ctypes.c_ulong, ctypes.POINTER(DATA_BLOB),
        ]
        crypt32.CryptUnprotectData.restype = ctypes.c_int
        kernel32.LocalFree.argtypes = [ctypes.c_void_p]
        kernel32.LocalFree.restype = ctypes.c_void_p
        return DATA_BLOB, crypt32, kernel32

    @classmethod
    def protect(cls, plaintext: bytes) -> bytes:
        DATA_BLOB, crypt32, kernel32 = cls._api()
        source_buffer = ctypes.create_string_buffer(plaintext)
        source = DATA_BLOB(len(plaintext), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        target = DATA_BLOB()
        try:
            ok = crypt32.CryptProtectData(ctypes.byref(source), "ALICE companion pairing keys", None, None, None, 0x1, ctypes.byref(target))
            if not ok:
                raise ctypes.WinError(ctypes.get_last_error())
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            if target.pbData:
                kernel32.LocalFree(target.pbData)
            ctypes.memset(source_buffer, 0, len(plaintext))

    @classmethod
    def unprotect(cls, ciphertext: bytes) -> bytes:
        DATA_BLOB, crypt32, kernel32 = cls._api()
        source_buffer = ctypes.create_string_buffer(ciphertext)
        source = DATA_BLOB(len(ciphertext), ctypes.cast(source_buffer, ctypes.POINTER(ctypes.c_ubyte)))
        target = DATA_BLOB()
        description = ctypes.c_wchar_p()
        try:
            ok = crypt32.CryptUnprotectData(ctypes.byref(source), ctypes.byref(description), None, None, None, 0x1, ctypes.byref(target))
            if not ok:
                raise ctypes.WinError(ctypes.get_last_error())
            return ctypes.string_at(target.pbData, target.cbData)
        finally:
            if target.pbData:
                kernel32.LocalFree(target.pbData)
            if description:
                kernel32.LocalFree(description)
            ctypes.memset(source_buffer, 0, len(ciphertext))


def default_pairing_store_path() -> Path:
    local_app_data = os.environ.get("LOCALAPPDATA")
    if not local_app_data:
        raise OSError("Windows Local AppData is unavailable")
    return Path(local_app_data) / "ALICE" / "remote" / "paired_clients.dpapi"


class DPAPIPairingStore:
    """Store a bounded set of per-client secrets only as a DPAPI blob."""

    def __init__(
        self,
        path: str | Path | None = None,
        *,
        protect: Callable[[bytes], bytes] = DPAPIProtector.protect,
        unprotect: Callable[[bytes], bytes] = DPAPIProtector.unprotect,
    ) -> None:
        self.path = Path(path) if path is not None else default_pairing_store_path()
        self._protect = protect
        self._unprotect = unprotect
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def _load(self) -> dict[str, dict[str, object]]:
        if not self.path.exists():
            return {}
        raw = self.path.read_bytes()
        if not raw.startswith(_MAGIC):
            raise ValueError("pairing store format is invalid")
        try:
            payload = json.loads(self._unprotect(raw[len(_MAGIC):]).decode("utf-8"))
        except Exception as exc:
            raise ValueError("pairing store could not be opened for this Windows user") from exc
        if not isinstance(payload, dict) or payload.get("schema") != 1 or not isinstance(payload.get("clients"), list):
            raise ValueError("pairing store schema is invalid")
        clients: dict[str, dict[str, object]] = {}
        for row in payload["clients"]:
            if not isinstance(row, dict):
                raise ValueError("pairing store client record is invalid")
            client_id = row.get("client_id")
            secret = row.get("secret")
            scopes = row.get("scopes")
            label = row.get("label")
            created_at = row.get("created_at")
            if (not isinstance(client_id, str) or not client_id or len(client_id) > 64
                    or client_id in clients or not isinstance(secret, str)
                    or not isinstance(scopes, list) or not all(s in ALLOWED_SCOPES for s in scopes)
                    or not isinstance(label, str) or not isinstance(created_at, (int, float))):
                raise ValueError("pairing store client record is invalid")
            try:
                secret_bytes = base64.urlsafe_b64decode(secret.encode("ascii"))
            except Exception as exc:
                raise ValueError("pairing store secret encoding is invalid") from exc
            if len(secret_bytes) != 32:
                raise ValueError("pairing store secret length is invalid")
            clients[client_id] = dict(row)
        if len(clients) > _MAX_CLIENTS:
            raise ValueError("pairing store exceeds the client limit")
        return clients

    def _save(self, clients: dict[str, dict[str, object]]) -> None:
        plaintext = json.dumps({"schema": 1, "clients": list(clients.values())}, separators=(",", ":")).encode("utf-8")
        encrypted = _MAGIC + self._protect(plaintext)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix=".paired-", suffix=".tmp", dir=str(self.path.parent))
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

    @staticmethod
    def _client(row: dict[str, object]) -> PairedClient:
        return PairedClient(str(row["client_id"]), str(row["label"]), frozenset(row["scopes"]), float(row["created_at"]))

    def clients(self) -> tuple[PairedClient, ...]:
        return tuple(self._client(row) for row in self._load().values())

    def snapshot(self) -> bytes | None:
        """Capture the already-protected store blob for an atomic pairing replacement rollback."""
        return self.path.read_bytes() if self.path.exists() else None

    def restore_snapshot(self, protected_blob: bytes | None) -> None:
        """Restore a previously captured encrypted blob without decrypting or exposing keys."""
        if protected_blob is None:
            self.path.unlink(missing_ok=True)
            return
        fd, temporary = tempfile.mkstemp(prefix=".paired-restore-", suffix=".tmp", dir=str(self.path.parent))
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(protected_blob)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temporary, self.path)
        finally:
            try:
                os.unlink(temporary)
            except FileNotFoundError:
                pass

    def pair(self, label: str, scopes: set[str] | frozenset[str], *, replace_existing: bool = False) -> PairingGrant:
        clean_label = " ".join(str(label).split())[:48]
        selected = frozenset(scopes)
        if not clean_label:
            raise ValueError("client label is required")
        if not selected or not selected.issubset(ALLOWED_SCOPES):
            raise ValueError("pairing scopes are empty or unsupported")
        clients = self._load()
        if len(clients) >= _MAX_CLIENTS and replace_existing and len(clients) == 1:
            clients = {}
        elif len(clients) >= _MAX_CLIENTS:
            raise ValueError("maximum paired-client count reached")
        client_id = secrets.token_urlsafe(16)
        secret = secrets.token_bytes(32)
        clients[client_id] = {
            "client_id": client_id,
            "label": clean_label,
            "secret": base64.urlsafe_b64encode(secret).decode("ascii"),
            "scopes": sorted(selected),
            "created_at": time.time(),
        }
        self._save(clients)
        token = base64.urlsafe_b64encode(secret).decode("ascii").rstrip("=")
        return PairingGrant(client_id, selected, token)

    def credential(self, client_id: str) -> PairingCredential:
        row = self._load().get(client_id)
        if row is None:
            raise KeyError(client_id)
        secret = base64.urlsafe_b64decode(str(row["secret"]).encode("ascii"))
        return PairingCredential(self._client(row), secret)

    def revoke(self, client_id: str) -> bool:
        clients = self._load()
        if client_id not in clients:
            return False
        clients.pop(client_id)
        self._save(clients)
        return True

