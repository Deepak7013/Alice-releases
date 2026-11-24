"""Fail-closed request authentication and action policy for a future phone link.

This module deliberately does not open a listener, expose ADB, or perform phone
actions. It is the host-side security boundary to be wired to a private-network
transport and a separately permissioned Android companion.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import re
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Mapping


class RemoteMobileAuthError(PermissionError):
    """A remote request failed authentication or replay checks."""


class RemoteMobilePolicyError(PermissionError):
    """A remote command is outside the deliberately small initial policy."""


@dataclass(frozen=True)
class RemoteMobileIdentity:
    client_id: str
    scopes: frozenset[str]


class RemoteMobileAuthenticator:
    """Verify HMAC-authenticated requests and reject stale/replayed envelopes.

    The caller must provide a per-paired-client random secret of at least 256
    bits, keep it in OS-protected storage, and transport requests only through
    an authenticated encrypted channel (for example, a private VPN).
    """

    def __init__(
        self,
        secret: bytes,
        identity: RemoteMobileIdentity,
        *,
        clock: Callable[[], float] = time.time,
        max_clock_skew_seconds: int = 60,
        nonce_ttl_seconds: int = 120,
        max_cached_nonces: int = 4096,
    ) -> None:
        if not isinstance(secret, bytes) or len(secret) < 32:
            raise ValueError("remote pairing secret must contain at least 32 bytes")
        if not identity.client_id.strip() or not identity.scopes:
            raise ValueError("paired client identity and scopes are required")
        self._secret = secret
        self.identity = identity
        self._clock = clock
        self._max_skew = max(1, int(max_clock_skew_seconds))
        self._nonce_ttl = max(self._max_skew, int(nonce_ttl_seconds))
        self._max_cached_nonces = max(32, int(max_cached_nonces))
        self._seen: dict[str, float] = {}
        self._lock = threading.Lock()

    @staticmethod
    def canonical_request(method: str, path: str, timestamp: str, nonce: str, body: bytes) -> bytes:
        method = str(method).upper()
        path = str(path)
        if not re.fullmatch(r"[A-Z]{3,10}", method):
            raise RemoteMobileAuthError("invalid request method")
        if not path.startswith("/") or "\n" in path or "\r" in path:
            raise RemoteMobileAuthError("invalid request path")
        if "?" in path or "#" in path:
            raise RemoteMobileAuthError("query strings and fragments must be canonicalized separately")
        body_digest = hashlib.sha256(body).hexdigest()
        return f"ALICE-MOBILE-v1\n{method}\n{path}\n{timestamp}\n{nonce}\n{body_digest}".encode("utf-8")

    @classmethod
    def sign_for_client(
        cls, secret: bytes, method: str, path: str, body: bytes, *, timestamp: int, nonce: str
    ) -> str:
        message = cls.canonical_request(method, path, str(timestamp), nonce, body)
        return hmac.new(secret, message, hashlib.sha256).hexdigest()

    def verify(
        self,
        method: str,
        path: str,
        body: bytes,
        headers: Mapping[str, str],
        *,
        required_scope: str,
    ) -> RemoteMobileIdentity:
        normalized = {str(k).lower(): str(v).strip() for k, v in headers.items()}
        timestamp = normalized.get("x-alice-timestamp", "")
        nonce = normalized.get("x-alice-nonce", "")
        supplied = normalized.get("x-alice-signature", "")
        if not timestamp.isascii() or not timestamp.isdecimal() or len(timestamp) > 12:
            raise RemoteMobileAuthError("missing or invalid request timestamp")
        if not re.fullmatch(r"[A-Za-z0-9_-]{16,128}", nonce):
            raise RemoteMobileAuthError("missing or invalid request nonce")
        if not re.fullmatch(r"[0-9a-fA-F]{64}", supplied):
            raise RemoteMobileAuthError("missing or invalid request signature")
        now = self._clock()
        if abs(now - int(timestamp)) > self._max_skew:
            raise RemoteMobileAuthError("request timestamp is outside the allowed window")
        if required_scope not in self.identity.scopes:
            raise RemoteMobilePolicyError("paired client lacks the required scope")
        message = self.canonical_request(method, path, timestamp, nonce, body)
        expected = hmac.new(self._secret, message, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(expected, supplied.lower()):
            raise RemoteMobileAuthError("request signature does not match")
        with self._lock:
            cutoff = now - self._nonce_ttl
            self._seen = {key: seen_at for key, seen_at in self._seen.items() if seen_at >= cutoff}
            if nonce in self._seen:
                raise RemoteMobileAuthError("request nonce was already used")
            if len(self._seen) >= self._max_cached_nonces:
                raise RemoteMobileAuthError("request replay cache is at capacity")
            self._seen[nonce] = now
        return self.identity


# First release of the remote link is intentionally limited to non-mutating
# requests plus local draft creation. Phone UI actions and message sends remain
# unavailable until the Android companion, explicit confirmation, and observers
# are implemented and tested.
REMOTE_MOBILE_COMMAND_SCOPES: dict[str, str] = {
    "alice.status.read": "status.read",
    "alice.chat": "chat",
    "email.count_today": "email.read",
    "email.draft.create": "email.draft",
    "phone.notifications.read": "notifications.read",
}


def authorize_remote_mobile_command(command: str, scopes: frozenset[str]) -> str:
    """Return the required scope, rejecting unknown or consequential actions."""
    required = REMOTE_MOBILE_COMMAND_SCOPES.get(str(command).strip())
    if required is None:
        raise RemoteMobilePolicyError("remote command is not enabled")
    if required not in scopes:
        raise RemoteMobilePolicyError("paired client lacks the required scope")
    return required


class RemoteMobileDispatcher:
    """Authenticate a bounded JSON request, then call an injected safe handler.

    The transport/server must enforce HTTPS over a private network and request
    size/rate limits. This class never discovers or invokes arbitrary tools.
    """

    def __init__(
        self,
        authenticator: RemoteMobileAuthenticator,
        handlers: Mapping[str, Callable[[Mapping[str, Any]], Any]],
        *,
        max_body_bytes: int = 16_384,
    ) -> None:
        self._authenticator = authenticator
        self._handlers = dict(handlers)
        self._max_body_bytes = max(256, int(max_body_bytes))

    def dispatch(self, method: str, path: str, body: bytes, headers: Mapping[str, str]) -> dict[str, Any]:
        if not isinstance(body, bytes) or len(body) > self._max_body_bytes:
            raise RemoteMobilePolicyError("request body is invalid or too large")
        try:
            payload = json.loads(body.decode("utf-8"))
        except (UnicodeDecodeError, json.JSONDecodeError) as exc:
            raise RemoteMobilePolicyError("request body must be valid UTF-8 JSON") from exc
        if not isinstance(payload, dict):
            raise RemoteMobilePolicyError("request body must be a JSON object")
        command = payload.get("command")
        scope = authorize_remote_mobile_command(command, self._authenticator.identity.scopes)
        self._authenticator.verify(method, path, body, headers, required_scope=scope)
        handler = self._handlers.get(command)
        if handler is None:
            raise RemoteMobilePolicyError("remote command has no installed handler")
        arguments = {key: value for key, value in payload.items() if key != "command"}
        return {"ok": True, "command": command, "result": handler(arguments)}

