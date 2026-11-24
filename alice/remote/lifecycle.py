"""Opt-in ALICE host lifecycle for a single paired mobile client."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any, Callable, Mapping

from .http_service import RemoteMobileHTTPService
from .mobile_link import RemoteMobileAuthenticator, RemoteMobileDispatcher, RemoteMobileIdentity
from .pairing_store import DPAPIPairingStore
from .runtime_handlers import build_remote_mobile_handlers


DEFAULT_LOOPBACK_PORT = 17840
CONFIG_RELATIVE_PATH = Path("alice_workspace") / "runtime" / "remote_mobile.json"


def read_config(root: str | Path) -> dict[str, Any]:
    """Read an opt-in config. Missing or disabled configuration starts nothing."""
    path = Path(root) / CONFIG_RELATIVE_PATH
    if not path.exists():
        return {"enabled": False}
    value = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(value, dict) or not isinstance(value.get("enabled"), bool):
        raise ValueError("remote mobile configuration is invalid")
    if not value["enabled"]:
        return {"enabled": False}
    client_id = value.get("client_id")
    port = value.get("port", DEFAULT_LOOPBACK_PORT)
    if client_id is not None and (not isinstance(client_id, str) or not client_id or len(client_id) > 64):
        raise ValueError("remote mobile client_id is invalid")
    if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
        raise ValueError("remote mobile port is invalid")
    return {"enabled": True, "client_id": client_id, "port": port}


def write_config(root: str | Path, *, enabled: bool, client_id: str = "", port: int = DEFAULT_LOOPBACK_PORT) -> Path:
    """Atomically persist non-secret opt-in state; pairing keys stay in DPAPI."""
    if not isinstance(enabled, bool):
        raise ValueError("enabled must be a boolean")
    payload: dict[str, Any] = {"enabled": enabled}
    if enabled:
        if client_id and (not isinstance(client_id, str) or len(client_id) > 64):
            raise ValueError("remote mobile client_id is invalid")
        if isinstance(port, bool) or not isinstance(port, int) or not 1024 <= port <= 65535:
            raise ValueError("remote mobile port is invalid")
        payload["port"] = port
        if client_id:
            payload["client_id"] = client_id
    path = Path(root) / CONFIG_RELATIVE_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".remote-mobile-", suffix=".tmp", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            json.dump(payload, stream, separators=(",", ":"))
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
    return path


class RemoteMobileServiceController:
    """Start/stop the loopback bridge using one DPAPI-protected phone key."""

    def __init__(
        self,
        agent: Any,
        store: DPAPIPairingStore | None,
        *,
        port: int = DEFAULT_LOOPBACK_PORT,
        version: str = "",
        email_service: Any | None = None,
        service_factory: Callable[..., RemoteMobileHTTPService] = RemoteMobileHTTPService,
    ) -> None:
        self.agent = agent
        self.store = store
        self.port = port
        self.version = str(version)[:80]
        self.email_service = email_service
        self._service_factory = service_factory
        self._service: RemoteMobileHTTPService | None = None
        self.client_id: str | None = None

    def start(self, client_id: str) -> tuple[str, int]:
        if self._service is not None:
            self.shutdown()
        if self.store is None:
            raise RuntimeError("pairing storage is required before authenticated service startup")
        credential = self.store.credential(client_id)
        identity = RemoteMobileIdentity(credential.client.client_id, credential.client.scopes)
        auth = RemoteMobileAuthenticator(credential.secret, identity)

        def safe_status() -> Mapping[str, Any]:
            return {"version": self.version, "state": "ready"}

        handlers = build_remote_mobile_handlers(self.agent, status_provider=safe_status,
                                                email_service=self.email_service)
        dispatcher = RemoteMobileDispatcher(auth, handlers)
        service = self._service_factory(dispatcher, host="127.0.0.1", port=self.port)
        try:
            address = service.start()
        except Exception:
            try:
                service.shutdown()
            except Exception:
                pass
            raise
        self._service = service
        self.client_id = credential.client.client_id
        return address

    def prepare(self) -> tuple[str, int]:
        """Start the loopback health endpoint before issuing a pairing secret."""
        if self._service is not None:
            return self._service.address
        service = self._service_factory(None, host="127.0.0.1", port=self.port)
        try:
            address = service.start()
        except Exception:
            try:
                service.shutdown()
            except Exception:
                pass
            raise
        self._service = service
        self.client_id = None
        return address

    def shutdown(self) -> None:
        service, self._service = self._service, None
        self.client_id = None
        if service is not None:
            service.shutdown()


def start_configured_service(
    agent: Any,
    root: str | Path,
    *,
    store: DPAPIPairingStore | None = None,
    service_factory: Callable[..., RemoteMobileHTTPService] = RemoteMobileHTTPService,
    version: str = "",
    email_service: Any | None = None,
) -> RemoteMobileServiceController | None:
    """Start only when a local config explicitly enables one existing pairing."""
    config = read_config(root)
    if not config["enabled"]:
        return None
    client_id = config.get("client_id")
    if client_id and store is None:
        store = DPAPIPairingStore()
    controller = RemoteMobileServiceController(
        agent,
        store,
        port=config["port"],
        version=version,
        email_service=email_service,
        service_factory=service_factory,
    )
    if client_id:
        controller.start(client_id)
    else:
        controller.prepare()
    return controller

