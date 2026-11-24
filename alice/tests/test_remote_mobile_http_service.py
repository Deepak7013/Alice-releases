import http.client
import json
import time

import pytest

from alice.remote.http_service import RemoteMobileHTTPService
from alice.remote.mobile_link import (
    RemoteMobileAuthenticator,
    RemoteMobileDispatcher,
    RemoteMobileIdentity,
)


def make_service(handler, *, max_body_bytes=16_384):
    secret = b"s" * 32
    identity = RemoteMobileIdentity("test-phone", frozenset({"status.read"}))
    auth = RemoteMobileAuthenticator(secret, identity)
    dispatcher = RemoteMobileDispatcher(auth, {"alice.status.read": handler})
    service = RemoteMobileHTTPService(dispatcher, max_body_bytes=max_body_bytes)
    service.start()
    return service, secret


def signed_headers(secret, body):
    timestamp = int(time.time())
    nonce = "testNonce_1234567"
    signature = RemoteMobileAuthenticator.sign_for_client(
        secret, "POST", "/api/mobile/command", body, timestamp=timestamp, nonce=nonce
    )
    return {
        "Content-Type": "application/json",
        "X-ALICE-Timestamp": str(timestamp),
        "X-ALICE-Nonce": nonce,
        "X-ALICE-Signature": signature,
    }


def test_http_service_health_and_authenticated_loopback_dispatch():
    service, secret = make_service(lambda args: {"state": "ready", "detail": args["detail"]})
    try:
        host, port = service.address
        assert host in {"127.0.0.1", "::1"}
        connection = http.client.HTTPConnection(host, port, timeout=3)
        connection.request("GET", "/health")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read()) == {"ok": True, "service": "alice-mobile-bridge"}

        body = json.dumps({"command": "alice.status.read", "detail": "brief"}, separators=(",", ":")).encode()
        connection.request("POST", "/api/mobile/command", body, signed_headers(secret, body))
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read()) == {
            "ok": True,
            "command": "alice.status.read",
            "result": {"state": "ready", "detail": "brief"},
        }
        connection.close()
    finally:
        service.shutdown()


def test_http_service_rejects_unauthenticated_commands_and_unknown_routes():
    calls = []
    service, _secret = make_service(lambda args: calls.append(args))
    try:
        host, port = service.address
        connection = http.client.HTTPConnection(host, port, timeout=3)
        body = b'{"command":"alice.status.read"}'
        connection.request("POST", "/api/mobile/command", body,
                           {"Content-Type": "application/json", "X-ALICE-Nonce": "missing-signature"})
        response = connection.getresponse()
        assert response.status == 401
        assert json.loads(response.read()) == {"ok": False, "error": "unauthorized"}
        connection.close()
        connection = http.client.HTTPConnection(host, port, timeout=3)
        connection.request("POST", "/other", body)
        response = connection.getresponse()
        assert response.status == 404
        assert calls == []
        connection.close()
    finally:
        service.shutdown()


def test_http_service_enforces_request_size_and_loopback_binding():
    service, _secret = make_service(lambda _args: None, max_body_bytes=256)
    try:
        host, port = service.address
        connection = http.client.HTTPConnection(host, port, timeout=3)
        body = b"x" * 257
        connection.request("POST", "/api/mobile/command", body,
                           {"Content-Type": "application/json"})
        response = connection.getresponse()
        assert response.status == 413
        assert json.loads(response.read()) == {"ok": False, "error": "body_too_large"}
        connection.close()
    finally:
        service.shutdown()

    service, _ = make_service(lambda _args: None)
    service.shutdown()
    with pytest.raises(ValueError, match="loopback only"):
        RemoteMobileHTTPService(service.dispatcher, host="0.0.0.0", port=8765)


def test_http_service_shutdown_is_idempotent():
    service, _ = make_service(lambda _args: None)
    service.shutdown()
    service.shutdown()


def test_health_only_service_rejects_all_commands_until_pairing():
    service = RemoteMobileHTTPService(None)
    service.start()
    try:
        host, port = service.address
        connection = http.client.HTTPConnection(host, port, timeout=3)
        connection.request("GET", "/health")
        response = connection.getresponse()
        assert response.status == 200
        assert json.loads(response.read()) == {"ok": True, "service": "alice-mobile-bridge"}
        connection.request("POST", "/api/mobile/command", b'{"command":"alice.status.read"}')
        response = connection.getresponse()
        assert response.status == 503
        assert json.loads(response.read()) == {"ok": False, "error": "pairing_required"}
        connection.close()
    finally:
        service.shutdown()


@pytest.mark.parametrize("value", [
    "http://alice.tailnet.ts.net", "https://localhost", "https://example.com",
    "https://alice.tailnet.ts.net/path", "https://alice.tailnet.ts.net/?x=1",
    "https://user@alice.tailnet.ts.net", "https://alice.tailnet.ts.net:8443",
])
def test_private_health_url_requires_canonical_tailscale_https_url(value):
    from alice.remote.http_service import verify_private_health_url

    assert verify_private_health_url(value) is False
