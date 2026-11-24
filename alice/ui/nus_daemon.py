"""Private loopback API used by the Nūs shell to reach ALICE's runtime.

Only explicit chat, status, task, and Gluttony operations are exposed. The
service binds to localhost, requires a per-launch random bearer token, limits
request sizes, and never exposes a generic Python/tool execution endpoint.
"""
from __future__ import annotations

import hmac
import json
import os
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import urlsplit


MAX_BODY = 1024 * 1024


class AliceNusServer:
    def __init__(self, app, token: str, ready_file: str):
        self.app = app
        self.token = str(token)
        self.ready_file = Path(ready_file)
        self.server = None
        self.thread = None

    def start(self):
        owner = self

        class Handler(BaseHTTPRequestHandler):
            server_version = "AliceNusBridge/1"

            def log_message(self, _format, *_args):
                return

            def _send(self, status, data):
                raw = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(raw)))
                self.send_header("Cache-Control", "no-store")
                self.send_header("X-Content-Type-Options", "nosniff")
                self.end_headers()
                self.wfile.write(raw)

            def _authorized(self):
                supplied = self.headers.get("Authorization", "")
                expected = "Bearer " + owner.token
                return hmac.compare_digest(supplied.encode(), expected.encode())

            def do_GET(self):
                if not self._authorized():
                    self._send(401, {"ok": False, "error": "Unauthorized"})
                    return
                route = urlsplit(self.path).path
                try:
                    if route == "/health":
                        result = {"ok": True, "ready": True, "version": owner.app._app_version()}
                    elif route == "/status":
                        result = {"ok": True, "provider": owner.app.provider_status(),
                                  "version": owner.app._app_version()}
                    elif route == "/events":
                        bridge = owner.app._nus_bridge
                        result = {"ok": True, "events": bridge.poll_events(0)}
                    elif route == "/tasks":
                        bridge = owner.app._nus_bridge
                        result = bridge.list_tasks(30)
                    elif route == "/gluttony":
                        result = owner._gluttony_status()
                    else:
                        self._send(404, {"ok": False, "error": "Unknown endpoint"})
                        return
                    self._send(200, result)
                except Exception:
                    self._send(500, {"ok": False, "error": "ALICE request failed"})

            def do_POST(self):
                if not self._authorized():
                    self._send(401, {"ok": False, "error": "Unauthorized"})
                    return
                try:
                    length = int(self.headers.get("Content-Length", "0"))
                except ValueError:
                    length = MAX_BODY + 1
                if length < 0 or length > MAX_BODY:
                    self._send(413, {"ok": False, "error": "Request too large"})
                    return
                try:
                    payload = json.loads(self.rfile.read(length) or b"{}")
                    if not isinstance(payload, dict):
                        raise ValueError("JSON object required")
                    route = urlsplit(self.path).path
                    if route == "/chat":
                        result = owner.app._nus_bridge.send_message(payload.get("text", ""))
                    elif route == "/providers":
                        result = owner._set_providers(payload)
                    elif route == "/gluttony/inspect-installer":
                        source = str(payload.get("path", ""))[:2048]
                        result = owner.app.devour.inspect_installer(source)
                        result = {"ok": True, **result}
                    elif route == "/gluttony/analyze":
                        source = str(payload.get("path", ""))[:2048]
                        result = owner.app.devour.devour(source)
                    elif route == "/gluttony/review":
                        result = owner._review_report(payload)
                    elif route == "/gluttony/review-capability":
                        result = owner._review_capability(payload)
                    else:
                        self._send(404, {"ok": False, "error": "Unknown endpoint"})
                        return
                    self._send(200, result)
                except (ValueError, TypeError) as exc:
                    self._send(400, {"ok": False, "error": str(exc)[:240]})
                except Exception as exc:
                    # Surface bounded, user-safe domain errors but never tracebacks,
                    # environment variables, or secret-bearing reprs.
                    from ..gluttony.evolver import DevourError
                    if isinstance(exc, DevourError):
                        self._send(400, {"ok": False, "error": str(exc)[:240]})
                    else:
                        self._send(500, {"ok": False, "error": "ALICE request failed"})

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.server.daemon_threads = True
        port = self.server.server_address[1]
        self.ready_file.parent.mkdir(parents=True, exist_ok=True)
        self.ready_file.write_text(json.dumps({"host": "127.0.0.1", "port": port}), encoding="utf-8")
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True,
                                       name="AliceNusLoopbackBridge")
        self.thread.start()

    def stop(self):
        if self.server:
            self.server.shutdown()
            self.server.server_close()
        try:
            self.ready_file.unlink(missing_ok=True)
        except OSError:
            pass

    def _gluttony_status(self):
        engine = self.app.devour
        rows = []
        try:
            base = Path(engine.base)
            for pattern in ("DIGEST_*.json", "MULTI_DIGEST_*.json", "INSTALLER_*.json"):
                for path in sorted(base.glob(pattern), key=lambda item: item.stat().st_mtime, reverse=True)[:30]:
                    try:
                        data = json.loads(path.read_text(encoding="utf-8"))
                    except (OSError, ValueError):
                        continue
                    rows.append({"kind": "installer" if path.name.startswith("INSTALLER_") else "digest",
                                 "name": path.name, "created": path.stat().st_mtime,
                                 "source": str(data.get("source_label") or data.get("file_name") or data.get("source") or data.get("path") or "")[:240],
                                 "status": str(data.get("status") or "inspected")[:40],
                                 "sha256": str(data.get("sha256") or data.get("tree_sha256") or "")[:64]})
            rows.sort(key=lambda row: row["created"], reverse=True)
        except OSError:
            pass
        return {"ok": True, "history": rows[:30], "policy": {
            "external_code_executed": False,
            "capability_activation_requires_approval": True}}

    def _report_path(self, name):
        import re
        from pathlib import Path
        selected = str(name or "")
        if not re.fullmatch(r"(?:DIGEST|MULTI_DIGEST)_[A-Za-z0-9_.-]{1,160}\.json", selected):
            raise ValueError("Choose a current Gluttony digest report.")
        base = Path(self.app.devour.base).resolve()
        raw = base / selected
        if raw.is_symlink():
            raise ValueError("Gluttony report links cannot be reviewed.")
        report = raw.resolve(strict=True)
        if report.parent != base or not report.is_file() or report.stat().st_size > self.app.devour.MAX_DIGEST_BYTES:
            raise ValueError("Gluttony report is outside the review store or too large.")
        return report

    def _review_report(self, payload):
        report = self._report_path(payload.get("name"))
        state = self.app.devour_reviews.inspect(str(report))
        security = state.get("security", {})
        license_info = state.get("license", {})
        capabilities = []
        for row in state.get("capabilities", [])[:120]:
            if not isinstance(row, dict):
                continue
            capabilities.append({"name": str(row.get("name", ""))[:120],
                                 "evidence_score": row.get("evidence_score", 0),
                                 "recommendation": str(row.get("recommendation", "manual_review"))[:180],
                                 "approved": bool(row.get("approved")),
                                 "evidence_terms": [str(x)[:160] for x in row.get("evidence_terms", [])[:12]],
                                 "evidence_files": [str(x)[:240] for x in row.get("evidence_files", [])[:12]]})
        return {"ok": True, "report_name": report.name,
                "source_label": str(state.get("source_label", ""))[:320],
                "multi_source": bool(state.get("multi_source")),
                "license": {"kind": str(license_info.get("kind", "unknown"))[:160],
                            "review_required": bool(license_info.get("review_required"))},
                "security": {"threat_count": int(security.get("threat_count", 0) or 0),
                             "files_scanned": int(security.get("files_scanned", 0) or 0)},
                "capabilities": capabilities,
                "policy": {"quarantined_code_executed": False,
                           "approval_allows_native_candidate_generation_only": True}}

    def _review_capability(self, payload):
        report = self._report_path(payload.get("name"))
        capability = str(payload.get("capability", ""))[:120]
        if payload.get("confirmed") is not True:
            raise ValueError("Confirm this individual capability review first.")
        if payload.get("approved") is True:
            result = self.app.devour_reviews.approve_capability(
                str(report), capability, confirmed=True, reviewer="local_user",
                decision="implement_native_equivalent")
        else:
            result = self.app.devour_reviews.revoke_capability(
                str(report), capability, confirmed=True, reviewer="local_user")
        return {"ok": True, "decision": result}

    def _set_providers(self, payload):
        keys = payload.get("keys", {})
        if not isinstance(keys, dict):
            return {"ok": False, "error": "Provider keys must be an object."}
        names = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY",
                 "openai": "OPENAI_API_KEY", "nvidia": "NVIDIA_API_KEY"}
        for name, variable in names.items():
            value = keys.get(name, "")
            if not isinstance(value, str) or len(value) > 4096:
                return {"ok": False, "error": "A provider key is invalid."}
            if value.strip():
                os.environ[variable] = value.strip()
            else:
                os.environ.pop(variable, None)
        provider = str(payload.get("provider", "gemini")).strip().lower()
        modes = {"gemini": "gemini_primary", "anthropic": "anthropic_primary",
                 "openai": "openai_primary", "nvidia": "nvidia_primary"}
        if provider not in modes:
            provider = "gemini" if os.environ.get("GEMINI_API_KEY") else "local"
        os.environ["ALICE_RUNTIME_MODE"] = modes.get(provider, "local")
        available = self.app.router.reload_config()
        return {"ok": True, "provider": provider,
                "available": {name: bool(available.get(name)) for name in names}}


def run():
    from .app import AliceUI
    from .premium_bridge import PremiumUIBridge

    app = AliceUI()
    bridge = PremiumUIBridge(app)
    app._nus_bridge = bridge
    server = AliceNusServer(app, os.environ["ALICE_NUS_TOKEN"], os.environ["ALICE_NUS_READY_FILE"])
    server.start()
    try:
        app.run()
    finally:
        server.stop()


if __name__ == "__main__":
    run()
