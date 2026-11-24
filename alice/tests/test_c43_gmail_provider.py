from datetime import datetime, timezone
import base64
import hashlib
import json
import os
import threading
from urllib.parse import parse_qs, urlparse, urlencode
from urllib.request import urlopen
from urllib.parse import parse_qs, urlparse

import pytest

from alice.email.gmail import (AUTH_URL, GmailCredentialStore, GmailError,
                               GmailReadOnlyProvider, connect_gmail)
from alice.email.service import EmailService


class Store:
    def __init__(self, credentials=None):
        self.credentials = credentials or {}

    def load(self):
        return dict(self.credentials)


def test_gmail_count_uses_readonly_metadata_and_exact_local_interval():
    start = datetime(2026, 10, 22, 0, 0, tzinfo=timezone.utc)
    end = datetime(2026, 10, 23, 0, 0, tzinfo=timezone.utc)
    calls = []

    def post_form(url, form):
        calls.append(("oauth", url, dict(form)))
        return {"access_token": "test-access", "expires_in": 3600}

    def opener(request, timeout):
        parsed = urlparse(request.full_url)
        query = parse_qs(parsed.query)
        calls.append(("api", request.full_url, request.headers.get("Authorization"), timeout))
        assert request.headers.get("Authorization") == "Bearer test-access"
        if parsed.path.endswith("/messages"):
            if query.get("pageToken") == ["next"]:
                return JsonResponse({"messages": [{"id": "edge_end"}]})
            return JsonResponse({"messages": [{"id": "at_start"}, {"id": "inside"}],
                                 "nextPageToken": "next"})
        message_id = parsed.path.rsplit("/", 1)[-1]
        timestamp = {
            "at_start": int(start.timestamp() * 1000),
            "inside": int((start.timestamp() + 10) * 1000),
            "edge_end": int(end.timestamp() * 1000),
        }[message_id]
        assert query["format"] == ["metadata"]
        assert query["fields"] == ["id,internalDate"]
        return JsonResponse({"id": message_id, "internalDate": str(timestamp)})

    provider = GmailReadOnlyProvider(Store({"client_id": "id", "client_secret": "secret",
                                            "refresh_token": "refresh"}),
                                    opener=opener, post_form=post_form,
                                    clock=lambda: 1000.0)
    assert provider.count_received(start, end) == 2
    query_strings = [parse_qs(urlparse(item[1]).query) for item in calls if item[0] == "api"]
    list_query = query_strings[0]["q"][0]
    assert f"after:{int(start.timestamp()) - 1}" in list_query
    assert f"before:{int(end.timestamp()) + 1}" in list_query
    assert "-in:sent" in list_query
    assert all("format" not in query or query["format"] == ["metadata"] for query in query_strings)


class JsonResponse:
    def __init__(self, value):
        import json
        self.data = json.dumps(value).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_args):
        return False

    def read(self, _size):
        return self.data


def test_gmail_not_configured_is_honest_and_no_network_call():
    called = []
    provider = GmailReadOnlyProvider(Store(), opener=lambda *_a, **_k: called.append(True))
    result = EmailService(object(), provider=provider).count_received_today()
    assert result["status"] == "not_configured"
    assert called == []


def test_invalid_metadata_fails_closed_without_partial_count():
    provider = GmailReadOnlyProvider(
        Store({"client_id": "id", "client_secret": "secret", "refresh_token": "refresh"}),
        post_form=lambda *_: {"access_token": "test-access"},
        opener=lambda *_a, **_k: JsonResponse({"messages": [{"id": "m1"}]}),
        clock=lambda: 0,
    )
    with pytest.raises(GmailError, match="required timestamp"):
        provider.count_received(datetime(2026, 1, 1, tzinfo=timezone.utc),
                                datetime(2026, 1, 2, tzinfo=timezone.utc))


def test_provider_failure_message_never_echoes_authorization_token():
    secret = "do-not-display-this-token"

    def fail(*_args, **_kwargs):
        raise OSError(secret)

    provider = GmailReadOnlyProvider(
        Store({"client_id": "id", "client_secret": "secret", "refresh_token": "refresh"}),
        post_form=lambda *_: {"access_token": "test-access"}, opener=fail, clock=lambda: 0)
    with pytest.raises(GmailError) as error:
        provider.count_received(datetime(2026, 1, 1, tzinfo=timezone.utc),
                                datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert secret not in str(error.value)
    assert secret not in repr(error.value)


def test_dpapi_store_uses_injected_protection_and_never_saves_cleartext(tmp_path):
    path = tmp_path / "gmail.dpapi"
    transform = lambda raw: bytes(byte ^ 0xA5 for byte in raw)
    store = GmailCredentialStore(path, protect=transform, unprotect=transform)
    credentials = {"client_id": "id", "client_secret": "client", "refresh_token": "refresh"}
    store.save(credentials)
    assert store.load() == credentials
    assert b"refresh" not in path.read_bytes()


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI is platform-specific")
def test_real_windows_dpapi_round_trip_and_ciphertext(tmp_path):
    path = tmp_path / "gmail-real.dpapi"
    store = GmailCredentialStore(path)
    credentials = {"client_id": "test-client", "client_secret": "test-secret",
                   "refresh_token": "test-refresh-token"}
    store.save(credentials)
    assert store.load() == credentials
    assert b"test-refresh-token" not in path.read_bytes()


def test_runtime_registry_wires_gmail_and_android_summary_without_ui_asset_changes():
    from pathlib import Path
    root = Path(__file__).resolve().parents[2]
    app = (root / "alice" / "ui" / "app.py").read_text(encoding="utf-8")
    assert "GmailReadOnlyProvider(gmail_credentials)" in app
    assert '"android_mail_unread_count"' in app
    assert "read_mail_unread_count(android_observer,serial)" in app


def test_provider_does_not_read_message_body_fields():
    requests = []

    def opener(request, timeout):
        url = urlparse(request.full_url)
        requests.append((url.path, parse_qs(url.query)))
        if url.path.endswith("/messages"):
            return JsonResponse({"messages": []})
        raise AssertionError("no message details should be fetched for an empty result")

    provider = GmailReadOnlyProvider(
        Store({"client_id": "id", "client_secret": "client", "refresh_token": "refresh"}),
        post_form=lambda *_: {"access_token": "test-access"}, opener=opener, clock=lambda: 0)
    assert provider.count_received(datetime(2026, 1, 1, tzinfo=timezone.utc),
                                   datetime(2026, 1, 2, tzinfo=timezone.utc)) == 0
    assert len(requests) == 1
    assert requests[0][1]["fields"] == ["messages(id),nextPageToken"]


def test_large_mail_count_fails_without_returning_partial_result():
    calls = []

    def opener(request, timeout):
        calls.append(request.full_url)
        return JsonResponse({"messages": [{"id": f"m{i}"} for i in range(1001)]})

    provider = GmailReadOnlyProvider(
        Store({"client_id": "id", "client_secret": "client", "refresh_token": "refresh"}),
        post_form=lambda *_: {"access_token": "test-access"}, opener=opener, clock=lambda: 0)
    with pytest.raises(GmailError, match="safe limit of 1000"):
        provider.count_received(datetime(2026, 1, 1, tzinfo=timezone.utc),
                                datetime(2026, 1, 2, tzinfo=timezone.utc))
    assert len(calls) == 1  # no metadata requests and no partial count


def test_gmail_search_reads_headers_and_short_snippet_without_body():
    requests = []

    def opener(request, timeout):
        url = urlparse(request.full_url)
        params = parse_qs(url.query)
        requests.append((url.path, params))
        if url.path.endswith("/messages"):
            assert params["q"] == ["from:boss subject:meeting"]
            assert params["maxResults"] == ["3"]
            return JsonResponse({"messages": [{"id": "message_1", "threadId": "thread_1"}],
                                 "resultSizeEstimate": 1})
        assert params["format"] == ["metadata"]
        assert params["metadataHeaders"] == ["From", "To", "Subject", "Date"]
        assert "snippet" in params["fields"][0]
        assert "body" not in params["fields"][0]
        return JsonResponse({"id": "message_1", "threadId": "thread_1",
                             "snippet": "Agenda attached; untrusted content",
                             "payload": {"headers": [
                                 {"name": "From", "value": "Boss <boss@example.com>"},
                                 {"name": "Subject", "value": "Weekly meeting"}]}})

    provider = GmailReadOnlyProvider(
        Store({"client_id": "id", "client_secret": "client", "refresh_token": "refresh"}),
        post_form=lambda *_: {"access_token": "test-access"}, opener=opener, clock=lambda: 0)
    result = provider.search_messages("from:boss subject:meeting", limit=3)
    assert result["bodies_read"] is False
    assert result["messages"][0]["message_id"] == "message_1"
    assert result["messages"][0]["subject"] == "Weekly meeting"
    assert result["messages"][0]["content_trust"] == "untrusted_email_content"
    assert len(requests) == 2


def test_read_message_returns_plain_text_only_and_skips_attachments_and_html():
    import base64

    body = base64.urlsafe_b64encode(b"Please review the attached report.").rstrip(b"=").decode()
    attachment = base64.urlsafe_b64encode(b"secret attachment bytes").rstrip(b"=").decode()
    calls = []

    def opener(request, timeout):
        url = urlparse(request.full_url)
        params = parse_qs(url.query)
        calls.append((url.path, params))
        if url.path.endswith("/messages"):
            return JsonResponse({"messages": [{"id": "message_1"}]})
        if params["format"] == ["metadata"]:
            return JsonResponse({"id": "message_1", "snippet": "report",
                                 "payload": {"headers": [{"name": "Subject", "value": "Report"}]}})
        assert params["format"] == ["full"]
        return JsonResponse({"id": "message_1", "payload": {"mimeType": "multipart/mixed", "parts": [
            {"mimeType": "text/plain", "body": {"data": body}},
            {"mimeType": "text/html", "body": {"data": attachment}},
            {"mimeType": "application/pdf", "filename": "report.pdf",
             "body": {"data": attachment}},
        ]}})

    provider = GmailReadOnlyProvider(
        Store({"client_id": "id", "client_secret": "client", "refresh_token": "refresh"}),
        post_form=lambda *_: {"access_token": "test-access"}, opener=opener, clock=lambda: 0)
    provider.search_messages("subject:report")
    result = provider.read_message("message_1")
    assert result["ok"] is True
    assert result["body_text"] == "Please review the attached report."
    assert result["attachments_exposed"] is False
    assert result["content_trust"] == "untrusted_email_content"
    assert len(calls) == 3


def test_invalid_message_id_fails_before_gmail_request():
    calls = []
    provider = GmailReadOnlyProvider(Store(), opener=lambda *a, **k: calls.append(a))
    with pytest.raises(ValueError, match="invalid Gmail message ID"):
        provider.read_message("../../messages/other")
    assert calls == []


def test_message_body_requires_id_from_latest_search_results():
    calls = []
    provider = GmailReadOnlyProvider(Store(), opener=lambda *a, **k: calls.append(a))
    with pytest.raises(ValueError, match="latest Gmail search"):
        provider.read_message("valid_but_unselected_id")
    assert calls == []


def _exercise_fake_oauth_callback(tmp_path, *, corrupt_state=False):
    client_file = tmp_path / "desktop-client.json"
    client_file.write_text(json.dumps({"installed": {
        "client_id": "offline-test-client", "client_secret": "offline-test-secret"}}),
        encoding="utf-8")
    transform = lambda raw: bytes(byte ^ 0xA5 for byte in raw)
    store = GmailCredentialStore(tmp_path / "credential.dpapi", protect=transform,
                                 unprotect=transform)
    observed = {}
    callback_done = threading.Event()

    def fake_browser(auth_url):
        assert auth_url.startswith(AUTH_URL + "?")
        auth = parse_qs(urlparse(auth_url).query)
        assert auth["scope"] == ["https://www.googleapis.com/auth/gmail.readonly"]
        assert auth["code_challenge_method"] == ["S256"]
        callback = auth["redirect_uri"][0]
        state = "wrong-state" if corrupt_state else auth["state"][0]

        def deliver():
            try:
                with urlopen(callback + "?" + urlencode(
                        {"state": state, "code": "offline-test-code"}), timeout=3) as response:
                    observed["callback_status"] = response.status
            except Exception as exc:
                observed["callback_error"] = type(exc).__name__
            finally:
                callback_done.set()

        threading.Thread(target=deliver, daemon=True).start()
        observed["auth"] = auth
        return True

    def fake_post(url, form):
        observed["token_url"] = url
        observed["form"] = dict(form)
        return {"access_token": "offline-access", "refresh_token": "offline-refresh"}

    result = connect_gmail(client_file, store, open_browser=fake_browser, timeout=3,
                           post_form=fake_post)
    assert callback_done.wait(3)
    return result, store, observed


def test_gmail_oauth_flow_uses_pkce_readonly_scope_and_encrypted_refresh(tmp_path):
    result, store, observed = _exercise_fake_oauth_callback(tmp_path)
    assert result == {"ok": True, "status": "connected",
                      "scope": "https://www.googleapis.com/auth/gmail.readonly"}
    verifier = observed["form"]["code_verifier"]
    expected = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    assert observed["auth"]["code_challenge"] == [expected]
    assert observed["form"]["grant_type"] == "authorization_code"
    assert observed["callback_status"] == 200
    assert store.load()["refresh_token"] == "offline-refresh"
    assert b"offline-refresh" not in store.path.read_bytes()


def test_gmail_oauth_state_mismatch_fails_without_storing_credentials(tmp_path):
    with pytest.raises(GmailError, match="state validation"):
        _exercise_fake_oauth_callback(tmp_path, corrupt_state=True)
    assert not (tmp_path / "credential.dpapi").exists()
