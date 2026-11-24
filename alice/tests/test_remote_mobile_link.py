import pytest

from alice.remote.mobile_link import (
    RemoteMobileAuthError,
    RemoteMobileAuthenticator,
    RemoteMobileIdentity,
    RemoteMobileDispatcher,
    RemoteMobilePolicyError,
    authorize_remote_mobile_command,
)


SECRET = b"x" * 32
BODY = b'{"command":"alice.status.read"}'
IDENTITY = RemoteMobileIdentity("phone-1", frozenset({"status.read", "notifications.read"}))


def request(auth, *, nonce="abcdefghijklmnop", body=BODY, method="POST", path="/api/mobile/command", timestamp=1000):
    signature = auth.sign_for_client(SECRET, method, path, body, timestamp=timestamp, nonce=nonce)
    return {
        "X-ALICE-Timestamp": str(timestamp),
        "X-ALICE-Nonce": nonce,
        "X-ALICE-Signature": signature,
    }


def test_remote_request_authenticates_and_returns_paired_identity():
    auth = RemoteMobileAuthenticator(SECRET, IDENTITY, clock=lambda: 1000)
    assert auth.verify("POST", "/api/mobile/command", BODY, request(auth), required_scope="status.read") == IDENTITY


def test_remote_request_rejects_replay():
    auth = RemoteMobileAuthenticator(SECRET, IDENTITY, clock=lambda: 1000)
    headers = request(auth)
    auth.verify("POST", "/api/mobile/command", BODY, headers, required_scope="status.read")
    with pytest.raises(RemoteMobileAuthError, match="already used"):
        auth.verify("POST", "/api/mobile/command", BODY, headers, required_scope="status.read")


def test_replay_cache_has_a_bounded_fail_closed_capacity():
    auth = RemoteMobileAuthenticator(SECRET, IDENTITY, clock=lambda: 1000, max_cached_nonces=32)
    for n in range(32):
        nonce = f"nonce-{n:012d}"
        auth.verify("POST", "/api/mobile/command", BODY,
                    request(auth, nonce=nonce), required_scope="status.read")
    with pytest.raises(RemoteMobileAuthError, match="capacity"):
        auth.verify("POST", "/api/mobile/command", BODY,
                    request(auth, nonce="nonce-overflow000"), required_scope="status.read")


def test_remote_request_rejects_body_path_and_timestamp_tampering():
    auth = RemoteMobileAuthenticator(SECRET, IDENTITY, clock=lambda: 1000)
    headers = request(auth)
    with pytest.raises(RemoteMobileAuthError, match="signature"):
        auth.verify("POST", "/api/mobile/command", BODY + b"!", headers, required_scope="status.read")
    with pytest.raises(RemoteMobileAuthError, match="signature"):
        auth.verify("POST", "/api/mobile/other", BODY, headers, required_scope="status.read")
    with pytest.raises(RemoteMobileAuthError, match="timestamp"):
        auth.verify("POST", "/api/mobile/command", BODY,
                    request(auth, nonce="qrstuvwxyzABCDEF", timestamp=900), required_scope="status.read")


def test_remote_request_fails_closed_for_missing_scope_or_short_secret():
    with pytest.raises(ValueError, match="32 bytes"):
        RemoteMobileAuthenticator(b"short", IDENTITY)
    auth = RemoteMobileAuthenticator(SECRET, IDENTITY, clock=lambda: 1000)
    with pytest.raises(RemoteMobilePolicyError, match="scope"):
        auth.verify("POST", "/api/mobile/command", BODY, request(auth), required_scope="email.draft")


def test_remote_policy_allows_scoped_reads_but_not_arbitrary_or_send_actions():
    assert authorize_remote_mobile_command("phone.notifications.read", IDENTITY.scopes) == "notifications.read"
    with pytest.raises(RemoteMobilePolicyError, match="not enabled"):
        authorize_remote_mobile_command("shell.exec", IDENTITY.scopes)
    with pytest.raises(RemoteMobilePolicyError, match="not enabled"):
        authorize_remote_mobile_command("message.send", IDENTITY.scopes)


def test_dispatcher_authenticates_then_calls_only_injected_handler():
    import json

    auth = RemoteMobileAuthenticator(SECRET, IDENTITY, clock=lambda: 1000)
    body = json.dumps({"command": "alice.status.read", "detail": "brief"}).encode()
    headers = request(auth, body=body, nonce="dispatchNonce0001")
    dispatcher = RemoteMobileDispatcher(
        auth,
        {"alice.status.read": lambda args: {"state": "ready", "requested": args["detail"]}},
    )
    assert dispatcher.dispatch("POST", "/api/mobile/command", body, headers) == {
        "ok": True,
        "command": "alice.status.read",
        "result": {"state": "ready", "requested": "brief"},
    }


def test_dispatcher_does_not_call_handler_for_unauthenticated_or_unlisted_command():
    import json

    calls = []
    auth = RemoteMobileAuthenticator(SECRET, IDENTITY, clock=lambda: 1000)
    body = json.dumps({"command": "alice.status.read"}).encode()
    headers = request(auth, body=body, nonce="badSignatureNonce1")
    headers["X-ALICE-Signature"] = "0" * 64
    dispatcher = RemoteMobileDispatcher(auth, {"alice.status.read": lambda args: calls.append(args)})
    with pytest.raises(RemoteMobileAuthError, match="signature"):
        dispatcher.dispatch("POST", "/api/mobile/command", body, headers)
    denied = json.dumps({"command": "shell.exec"}).encode()
    with pytest.raises(RemoteMobilePolicyError, match="not enabled"):
        dispatcher.dispatch("POST", "/api/mobile/command", denied, headers)
    assert calls == []


def test_dispatcher_rejects_oversized_or_non_object_bodies():
    auth = RemoteMobileAuthenticator(SECRET, IDENTITY, clock=lambda: 1000)
    dispatcher = RemoteMobileDispatcher(auth, {}, max_body_bytes=256)
    with pytest.raises(RemoteMobilePolicyError, match="too large"):
        dispatcher.dispatch("POST", "/api/mobile/command", b"x" * 257, {})
    with pytest.raises(RemoteMobilePolicyError, match="JSON object"):
        dispatcher.dispatch("POST", "/api/mobile/command", b"[]", {})
