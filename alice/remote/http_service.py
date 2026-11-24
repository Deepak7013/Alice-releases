"""Loopback-only HTTP transport for the authenticated remote mobile dispatcher.

Use Tailscale Serve (not Funnel) to proxy this local service over HTTPS to the
tailnet. This service deliberately refuses non-loopback bind addresses.
"""

from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener

from .mobile_link import (
    RemoteMobileAuthError,
    RemoteMobileDispatcher,
    RemoteMobilePolicyError,
)


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req: Request, fp: Any, code: int, msg: str, headers: Any, newurl: str):
        return None


def verify_private_health_url(value: str, *, timeout: float = 5.0) -> bool:
    """Verify a Tailscale Serve HTTPS URL reaches this bridge's health route.

    Pairing secrets must not be issued until the authenticated private path is
    in place. Accept only HTTPS names in Tailscale's ts.net domain, reject
    redirects, and require the exact low-information bridge health response.
    """
    try:
        parsed = urlsplit(str(value).strip())
        if (parsed.scheme.lower() != "https" or not parsed.hostname
                or not parsed.hostname.lower().endswith(".ts.net")
                or parsed.username is not None or parsed.password is not None
                or parsed.port is not None or parsed.path not in {"", "/"}
                or parsed.query or parsed.fragment):
            return False
        request = Request(f"https://{parsed.hostname}/health", headers={"Accept": "application/json"})
        opener = build_opener(_NoRedirect())
        with opener.open(request, timeout=max(0.5, min(float(timeout), 10.0))) as response:
            if response.status != 200:
                return False
            payload = json.loads(response.read(1024).decode("utf-8"))
            return payload == {"ok": True, "service": "alice-mobile-bridge"}
    except (ValueError, TypeError, OSError, URLError, HTTPError, json.JSONDecodeError):
        return False


class RemoteMobileHTTPService:
    def __init__(
        self,
        dispatcher: RemoteMobileDispatcher | None,
        *,
        host: str = "127.0.0.1",
        port: int = 0,
        max_body_bytes: int = 16_384,
    ) -> None:
        if host not in {"127.0.0.1", "::1", "localhost"}:
            raise ValueError("remote mobile bridge must bind to loopback only")
        self.dispatcher = dispatcher
        self.max_body_bytes = max(256, int(max_body_bytes))
        self._server = self._make_server(host, int(port))

    def _make_server(self, host: str, port: int) -> ThreadingHTTPServer:
        service = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "ALICE-Mobile-Bridge"
            sys_version = ""

            def log_message(self, _format: str, *_args: Any) -> None:
                # Never log request paths, headers, payloads, or remote addresses.
                return

            def _reply(self, status: int, payload: dict[str, Any]) -> None:
                data = json.dumps(payload, ensure_ascii=True, separators=(",", ":")).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(data)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                if self.close_connection:
                    self.send_header("Connection", "close")
                self.end_headers()
                self.wfile.write(data)

            def do_GET(self) -> None:  # noqa: N802
                if self.path == "/health":
                    self._reply(200, {"ok": True, "service": "alice-mobile-bridge"})
                else:
                    self._reply(404, {"ok": False, "error": "not_found"})

            def do_POST(self) -> None:  # noqa: N802
                if self.headers.get("Transfer-Encoding"):
                    self.close_connection = True
                    self._reply(400, {"ok": False, "error": "unsupported_transfer_encoding"})
                    return
                raw_length = self.headers.get("Content-Length", "")
                if not raw_length.isascii() or not raw_length.isdecimal() or len(raw_length) > 8:
                    self.close_connection = True
                    self._reply(400, {"ok": False, "error": "invalid_content_length"})
                    return
                length = int(raw_length)
                if length > service.max_body_bytes:
                    # Drain only a small overrun so clients receive a clean 413
                    # on keep-alive connections. Large bodies are rejected and
                    # the connection is closed without allocating their payload.
                    if length <= service.max_body_bytes * 2:
                        self.rfile.read(length)
                    else:
                        self.close_connection = True
                    self._reply(413, {"ok": False, "error": "body_too_large"})
                    return
                body = self.rfile.read(length)
                if len(body) != length:
                    self.close_connection = True
                    self._reply(400, {"ok": False, "error": "incomplete_body"})
                    return
                # Drain the bounded request body before returning an early route
                # or pairing error. Otherwise keep-alive clients can leave bytes
                # in the socket and Windows may reset the connection while the
                # next HTTP request is parsed.
                if self.path != "/api/mobile/command":
                    self._reply(404, {"ok": False, "error": "not_found"})
                    return
                if service.dispatcher is None:
                    self._reply(503, {"ok": False, "error": "pairing_required"})
                    return
                try:
                    result = service.dispatcher.dispatch("POST", self.path, body, self.headers)
                except RemoteMobileAuthError:
                    self._reply(401, {"ok": False, "error": "unauthorized"})
                except RemoteMobilePolicyError:
                    self._reply(403, {"ok": False, "error": "forbidden"})
                except Exception:
                    # Keep internal errors and user data out of HTTP responses/logs.
                    self._reply(500, {"ok": False, "error": "internal_error"})
                else:
                    self._reply(200, result)

        return ThreadingHTTPServer((host, port), Handler)

    @property
    def address(self) -> tuple[str, int]:
        host, port = self._server.server_address[:2]
        return str(host), int(port)

    def serve_forever(self) -> None:
        self._server.serve_forever(poll_interval=0.2)

    def start(self) -> tuple[str, int]:
        if getattr(self, "_thread", None) and self._thread.is_alive():
            return self.address
        self._thread = threading.Thread(target=self.serve_forever, name="alice-mobile-bridge", daemon=True)
        self._thread.start()
        return self.address

    def shutdown(self) -> None:
        thread = getattr(self, "_thread", None)
        if thread and thread.is_alive():
            self._server.shutdown()
        self._server.server_close()
        if thread and thread.is_alive():
            thread.join(timeout=2)

