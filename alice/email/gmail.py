"""Read-only Gmail metadata adapter and user-initiated Desktop OAuth flow.

Only Gmail's read-only OAuth scope is requested. Mail bodies are never fetched;
counting uses message IDs plus internalDate metadata to enforce a local-time
half-open interval. OAuth credentials are encrypted with current-user DPAPI.
"""
from __future__ import annotations

import hashlib
import hmac
import base64
import re
import json
import os
import secrets
import tempfile
import threading
import time
import urllib.error
import urllib.parse
import urllib.request
import webbrowser
from datetime import datetime
from email.header import decode_header, make_header
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from ..voice.secret_store import _dpapi_transform


SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
API_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages"
MAX_MESSAGES = 1000
MAX_API_RESPONSE_BYTES = 1024 * 1024
_MESSAGE_ID = re.compile(r"^[A-Za-z0-9_-]{1,200}$")


class GmailError(RuntimeError):
    """Sanitized Gmail/OAuth error. Never includes provider response bodies."""


class GmailCredentialStore:
    """Atomic current-Windows-user DPAPI storage for installed OAuth data."""

    MAX_BYTES = 32 * 1024

    def __init__(self, path, *, protect=None, unprotect=None):
        self.path = Path(path)
        self._protect = protect or (lambda data: _dpapi_transform(data, protect=True))
        self._unprotect = unprotect or (lambda data: _dpapi_transform(data, protect=False))

    def has(self):
        try:
            return self.path.is_file() and 0 < self.path.stat().st_size <= self.MAX_BYTES
        except OSError:
            return False

    def save(self, credentials: dict) -> None:
        if not isinstance(credentials, dict):
            raise ValueError("invalid_gmail_credentials")
        clean = {key: str(credentials.get(key, "")) for key in
                 ("client_id", "client_secret", "refresh_token")}
        if not all(clean.values()) or any(len(value) > 8192 for value in clean.values()):
            raise ValueError("invalid_gmail_credentials")
        payload = json.dumps(clean, separators=(",", ":")).encode("utf-8")
        if len(payload) > self.MAX_BYTES:
            raise ValueError("gmail_credentials_too_large")
        encrypted = self._protect(payload)
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

    def load(self) -> dict:
        if not self.has():
            return {}
        try:
            raw = self._unprotect(self.path.read_bytes())
            value = json.loads(raw.decode("utf-8"))
            if not isinstance(value, dict) or not all(value.get(key) for key in
                    ("client_id", "client_secret", "refresh_token")):
                return {}
            return {key: str(value[key]) for key in
                    ("client_id", "client_secret", "refresh_token")}
        except Exception:
            return {}

    def delete(self):
        self.path.unlink(missing_ok=True)


def _post_form(url: str, form: dict, *, timeout=20) -> dict:
    data = urllib.parse.urlencode(form).encode("ascii")
    request = urllib.request.Request(url, data=data, headers={
        "Content-Type": "application/x-www-form-urlencoded",
        "Accept": "application/json",
    })
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = json.loads(response.read(256 * 1024).decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, OSError, ValueError):
        raise GmailError("Google OAuth request failed; details were withheld.") from None
    if not isinstance(payload, dict):
        raise GmailError("Google OAuth returned an invalid response.")
    return payload


def connect_gmail(client_json_path, store: GmailCredentialStore, *, open_browser=webbrowser.open,
                  timeout=600, post_form=_post_form):
    """Run explicit loopback OAuth consent for a Google Desktop OAuth client.

    The downloaded client JSON is read once and never copied. Browser opening
    and the user's Google consent are required; this function has no silent path.
    """
    try:
        config = json.loads(Path(client_json_path).read_text(encoding="utf-8"))
        app = config.get("installed")
        client_id = str(app.get("client_id", ""))
        client_secret = str(app.get("client_secret", ""))
    except Exception:
        raise GmailError("Choose a valid Google OAuth Desktop client JSON file.") from None
    if not client_id or not client_secret or len(client_id) > 4096 or len(client_secret) > 4096:
        raise GmailError("Google OAuth client JSON must contain an installed Desktop client.")

    verifier = secrets.token_urlsafe(64)
    challenge = __import__("base64").urlsafe_b64encode(
        hashlib.sha256(verifier.encode("ascii")).digest()).rstrip(b"=").decode("ascii")
    state = secrets.token_urlsafe(32)
    received = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            received["state"] = params.get("state", [""])[0]
            received["code"] = params.get("code", [""])[0]
            received["error"] = params.get("error", [""])[0]
            body = (b"<html><title>ALICE Gmail setup</title><p>Google authorization returned. "
                    b"You may close this tab and return to ALICE.</p></html>")
            self.send_response(200 if not received["error"] else 400)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            return

    server = HTTPServer(("127.0.0.1", 0), Callback)
    server.timeout = max(1, min(int(timeout), 900))
    redirect = f"http://127.0.0.1:{server.server_port}/oauth2callback"
    query = urllib.parse.urlencode({
        "client_id": client_id, "redirect_uri": redirect,
        "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    try:
        if not open_browser(f"{AUTH_URL}?{query}"):
            raise GmailError("Could not open the browser for Google consent.")
        server.handle_request()
    finally:
        server.server_close()
    if not received:
        raise GmailError("Google consent timed out.")
    if not hmac.compare_digest(str(received.get("state", "")), state):
        raise GmailError("Google OAuth state validation failed.")
    if received.get("error") or not received.get("code"):
        raise GmailError("Google authorization was not completed.")
    token = post_form(TOKEN_URL, {
        "code": received["code"], "client_id": client_id,
        "client_secret": client_secret, "redirect_uri": redirect,
        "grant_type": "authorization_code", "code_verifier": verifier,
    })
    refresh_token = str(token.get("refresh_token", ""))
    access_token = str(token.get("access_token", ""))
    if not refresh_token or not access_token:
        raise GmailError("Google did not return offline access; ALICE was not connected.")
    store.save({"client_id": client_id, "client_secret": client_secret,
                "refresh_token": refresh_token})
    return {"ok": True, "status": "connected", "scope": SCOPE}


class GmailReadOnlyProvider:
    source_name = "Gmail read-only access (excludes Sent, Spam and Trash)"

    def __init__(self, store: GmailCredentialStore, *, opener=urllib.request.urlopen,
                 post_form=_post_form, clock=time.time):
        self.store = store
        self.opener = opener
        self.post_form = post_form
        self.clock = clock
        self._access_token = ""
        self._expires_at = 0.0
        self._lock = threading.Lock()
        self._recent_search_ids = set()

    @property
    def configured(self):
        return bool(self.store.load())

    def _get_access_token(self):
        with self._lock:
            if self._access_token and self.clock() < self._expires_at - 60:
                return self._access_token
            credentials = self.store.load()
            if not credentials:
                raise GmailError("Gmail is not connected. No mailbox was accessed.")
            token = self.post_form(TOKEN_URL, {
                "client_id": credentials["client_id"],
                "client_secret": credentials["client_secret"],
                "refresh_token": credentials["refresh_token"],
                "grant_type": "refresh_token",
            })
            access = str(token.get("access_token", ""))
            if not access:
                raise GmailError("Google OAuth refresh failed; response details were withheld.")
            self._access_token = access
            self._expires_at = self.clock() + max(60, int(token.get("expires_in", 3600)))
            return access

    def _get_json(self, url: str, access_token: str) -> dict:
        request = urllib.request.Request(url, headers={
            "Authorization": "Bearer " + access_token,
            "Accept": "application/json",
        })
        try:
            with self.opener(request, timeout=20) as response:
                raw = response.read(MAX_API_RESPONSE_BYTES + 1)
                if len(raw) > MAX_API_RESPONSE_BYTES:
                    raise GmailError("Gmail response exceeded ALICE's safe size limit.")
                payload = json.loads(raw.decode("utf-8"))
        except GmailError:
            raise
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            # Do not propagate HTTP bodies, request URLs or Authorization headers.
            raise GmailError("Gmail API request failed; response details were withheld.") from None
        if not isinstance(payload, dict):
            raise GmailError("Gmail API returned an invalid response.")
        return payload

    def count_received(self, start: datetime, end: datetime) -> int:
        if start.tzinfo is None or end.tzinfo is None or end <= start:
            raise ValueError("start/end must be timezone-aware and ordered")
        access_token = self._get_access_token()
        start_epoch = int(start.timestamp())
        end_epoch = int(end.timestamp())
        # Search has exclusive second-resolution bounds. Widen by one second,
        # then filter exact internalDate metadata locally for boundary accuracy.
        query = f"after:{start_epoch - 1} before:{end_epoch + 1} -in:sent"
        page_token = ""
        seen = set()
        while True:
            params = {"q": query, "maxResults": "500", "fields": "messages(id),nextPageToken"}
            if page_token:
                params["pageToken"] = page_token
            url = API_URL + "?" + urllib.parse.urlencode(params)
            page = self._get_json(url, access_token)
            messages = page.get("messages", [])
            if not isinstance(messages, list):
                raise GmailError("Gmail returned an invalid message list.")
            for item in messages:
                message_id = str(item.get("id", "")) if isinstance(item, dict) else ""
                if not message_id or len(message_id) > 200:
                    raise GmailError("Gmail returned an invalid message reference.")
                seen.add(message_id)
                if len(seen) > MAX_MESSAGES:
                    raise GmailError(f"Count exceeds the safe limit of {MAX_MESSAGES}; no partial count returned.")
            page_token = str(page.get("nextPageToken", ""))
            if not page_token:
                break

        start_ms = start.timestamp() * 1000
        end_ms = end.timestamp() * 1000
        exact = 0
        for message_id in sorted(seen):
            metadata_url = API_URL + "/" + urllib.parse.quote(message_id, safe="") + "?" + urllib.parse.urlencode({
                "format": "metadata", "fields": "id,internalDate"})
            metadata = self._get_json(metadata_url, access_token)
            try:
                internal_ms = int(metadata["internalDate"])
            except (KeyError, TypeError, ValueError) as exc:
                raise GmailError("Gmail omitted a required timestamp; no count returned.") from exc
            if start_ms <= internal_ms < end_ms:
                exact += 1
        return exact

    @staticmethod
    def _validate_search(query: str, limit: int) -> str:
        text = str(query or "").strip()
        if not text or len(text) > 500 or any(ord(char) < 32 for char in text):
            raise ValueError("Gmail search query must be 1-500 printable characters")
        if isinstance(limit, bool) or not isinstance(limit, int) or not 1 <= limit <= 10:
            raise ValueError("Gmail search limit must be between 1 and 10")
        return text

    def search_messages(self, query: str, limit: int = 5) -> dict:
        """Search Gmail and return a small metadata/snippet result set, no bodies."""
        query = self._validate_search(query, limit)
        self._recent_search_ids = set()
        access_token = self._get_access_token()
        params = urllib.parse.urlencode({
            "q": query, "maxResults": str(limit),
            "fields": "messages(id,threadId),resultSizeEstimate",
        })
        page = self._get_json(API_URL + "?" + params, access_token)
        rows = page.get("messages", [])
        if not isinstance(rows, list):
            raise GmailError("Gmail returned an invalid message list.")
        results = []
        for row in rows[:limit]:
            message_id = str(row.get("id", "")) if isinstance(row, dict) else ""
            if not _MESSAGE_ID.fullmatch(message_id):
                raise GmailError("Gmail returned an invalid message reference.")
            self._recent_search_ids.add(message_id)
            url = API_URL + "/" + urllib.parse.quote(message_id, safe="") + "?" + urllib.parse.urlencode({
                "format": "metadata", "metadataHeaders": ["From", "To", "Subject", "Date"],
                "fields": "id,threadId,internalDate,snippet,payload(headers(name,value))",
            }, doseq=True)
            message = self._get_json(url, access_token)
            headers = {}
            payload = message.get("payload", {})
            for header in payload.get("headers", []) if isinstance(payload, dict) else []:
                if isinstance(header, dict):
                    name = str(header.get("name", "")).casefold()
                    if name in {"from", "to", "subject", "date"} and name not in headers:
                        try:
                            headers[name] = str(make_header(decode_header(str(header.get("value", "")))))[:500]
                        except (LookupError, UnicodeError, ValueError):
                            headers[name] = str(header.get("value", ""))[:500]
            results.append({
                "message_id": message_id,
                "thread_id": str(message.get("threadId", row.get("threadId", "")))[:200],
                "from": headers.get("from", ""), "to": headers.get("to", ""),
                "subject": headers.get("subject", ""), "date": headers.get("date", ""),
                "snippet": str(message.get("snippet", ""))[:240],
                "content_trust": "untrusted_email_content",
            })
        return {"ok": True, "status": "observed", "messages": results,
                "result_size_estimate": page.get("resultSizeEstimate"),
                "bodies_read": False}

    @staticmethod
    def _plain_text_parts(payload) -> list[str]:
        output = []
        if not isinstance(payload, dict):
            return output
        mime = str(payload.get("mimeType", "")).casefold()
        filename = str(payload.get("filename", ""))
        body = payload.get("body", {})
        if mime == "text/plain" and not filename and isinstance(body, dict) and not body.get("attachmentId"):
            data = body.get("data")
            if isinstance(data, str) and data:
                try:
                    decoded = base64.urlsafe_b64decode(data + "=" * (-len(data) % 4))
                    output.append(decoded.decode("utf-8", errors="replace"))
                except (ValueError, UnicodeError):
                    pass
        for part in payload.get("parts", []) if isinstance(payload.get("parts", []), list) else []:
            output.extend(GmailReadOnlyProvider._plain_text_parts(part))
        return output

    def read_message(self, message_id: str) -> dict:
        """Read one explicitly selected Gmail message's plain text, never attachments."""
        message_id = str(message_id or "").strip()
        if not _MESSAGE_ID.fullmatch(message_id):
            raise ValueError("invalid Gmail message ID")
        if message_id not in self._recent_search_ids:
            raise ValueError("message must be selected from the latest Gmail search results")
        access_token = self._get_access_token()
        params = urllib.parse.urlencode({"format": "full", "fields": "id,payload"})
        url = API_URL + "/" + urllib.parse.quote(message_id, safe="") + "?" + params
        message = self._get_json(url, access_token)
        content = "\n".join(self._plain_text_parts(message.get("payload", {}))).strip()
        if not content:
            return {"ok": False, "status": "plain_text_unavailable", "message_id": message_id,
                    "message": "No eligible plain-text body was available; attachments are not decoded or exposed, and HTML-only bodies are not returned."}
        return {"ok": True, "status": "observed", "message_id": message_id,
                "body_text": content[:12000], "truncated": len(content) > 12000,
                "content_trust": "untrusted_email_content", "attachments_exposed": False}
