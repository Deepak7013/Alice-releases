from __future__ import annotations

import json
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Iterable, Optional

from ..devices.registry import DeviceRegistry
from ..devices.discovery import DeviceCandidate
from ..devices.selector import DeviceSelector
from ..security.device_consent import DeviceConsent


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(timezone.utc)


class AuthorizationError(RuntimeError):
    pass


class DeviceAuthorizationManager:
    """Explicit device authorization with scoped, persistent consent.

    Selecting or discovering a device never changes consent. Only approve()
    grants scopes, marks the device paired, and persists the authorization.
    """

    def __init__(
        self,
        root=None,
        *,
        registry: Optional[DeviceRegistry] = None,
        consent: Optional[DeviceConsent] = None,
        request_ttl_seconds: int = 300,
    ):
        self.root = Path(root or Path.cwd())
        self.path = self.root / "alice_workspace" / "security" / "authorization_requests.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.registry = registry or DeviceRegistry(self.root)
        self.consent = consent or DeviceConsent(self.root)
        if request_ttl_seconds <= 0:
            raise ValueError("request_ttl_seconds must be positive")
        self.ttl = int(request_ttl_seconds)
        self.data = self._load()

    def _load(self):
        try:
            value = json.loads(self.path.read_text())
            return value if isinstance(value, dict) else {}
        except (OSError, ValueError, TypeError):
            return {}

    def _save(self):
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self.data, indent=2, sort_keys=True))
        tmp.replace(self.path)

    @staticmethod
    def select_device(
        candidates: Iterable[DeviceCandidate],
        query: str,
        *,
        kind: Optional[str] = None,
    ) -> DeviceCandidate:
        return DeviceSelector.select(candidates, query, kind=kind)

    def request(self, device_id: str, scopes: Iterable[str]) -> dict:
        device = self.registry.get(device_id)
        if not device:
            raise AuthorizationError(f"unknown device: {device_id}")
        normalized = sorted({str(s).strip() for s in scopes if str(s).strip()})
        if not normalized:
            raise AuthorizationError("at least one scope is required")
        request_id = secrets.token_urlsafe(18)
        created = _now()
        record = {
            "id": request_id,
            "device_id": device_id,
            "scopes": normalized,
            "created_at": _iso(created),
            "expires_at": _iso(created + timedelta(seconds=self.ttl)),
            "status": "pending",
        }
        self.data[request_id] = record
        self._save()
        return dict(record)

    def get(self, request_id: str) -> Optional[dict]:
        record = self.data.get(request_id)
        return dict(record) if record else None

    def _expire_if_needed(self, record: dict) -> dict:
        if record["status"] == "pending" and _now() >= _parse(record["expires_at"]):
            record["status"] = "expired"
            self._save()
        return record

    def approve(self, request_id: str) -> dict:
        record = self.data.get(request_id)
        if not record:
            raise AuthorizationError(f"authorization request not found: {request_id}")
        record = self._expire_if_needed(record)
        if record["status"] != "pending":
            raise AuthorizationError(f"request is not pending: {record['status']}")
        # The only place in this class that grants consent.
        self.consent.grant(record["device_id"], record["scopes"])
        self.registry.pair(record["device_id"])
        record["status"] = "approved"
        record["approved_at"] = _iso(_now())
        self.data[request_id] = record
        self._save()
        return dict(record)

    def deny(self, request_id: str) -> dict:
        record = self.data.get(request_id)
        if not record:
            raise AuthorizationError(f"authorization request not found: {request_id}")
        record = self._expire_if_needed(record)
        if record["status"] != "pending":
            raise AuthorizationError(f"request is not pending: {record['status']}")
        record["status"] = "denied"
        record["denied_at"] = _iso(_now())
        self.data[request_id] = record
        self._save()
        return dict(record)
