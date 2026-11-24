"""Privacy-limited summaries of explicitly observed Android mail screens."""
from __future__ import annotations

import re
from datetime import datetime, timezone


_MAIL_APPS = {
    "com.google.android.gm": "gmail",
    "com.microsoft.office.outlook": "outlook",
}
_UNREAD_PATTERNS = (
    re.compile(r"\b(\d{1,6})\s+(?:unread|new)\s+(?:emails?|messages?)\b", re.I),
    re.compile(r"\b(?:unread|new)\s+(?:emails?|messages?)\s*[:(]?\s*(\d{1,6})\b", re.I),
    re.compile(r"\bInbox\s*\(\s*(\d{1,6})\s*\)", re.I),
)


def read_mail_unread_count(controller, serial: str) -> dict:
    """Read only an unread badge count from a supported foreground mail app.

    The accessibility hierarchy is filtered locally. Message bodies, subjects,
    sender names, editable values, and raw labels are never returned.
    """
    if not serial or any(ch in str(serial) for ch in " \t\r\n;|&"):
        raise ValueError("an explicit valid Android device serial is required")
    state = controller.observe(str(serial))
    package = str(getattr(state, "package", "") or "").strip().casefold()
    app = _MAIL_APPS.get(package)
    observed_at = datetime.now(timezone.utc).isoformat()
    if app is None:
        return {"ok": False, "status": "unsupported_app", "package": package[:120],
                "message": "Open Gmail or Outlook on the connected device first."}

    candidates = set()
    for element in getattr(state, "elements", ()):
        class_name = str(getattr(element, "class_name", "") or "").casefold()
        if getattr(element, "focused", False) or "edittext" in class_name:
            continue
        resource_id = str(getattr(element, "resource_id", "") or "").casefold()
        # Text strings are inspected only in-process and only count-like matches
        # are retained. Never return the original labels to the model or logs.
        for field in ("text", "content_desc"):
            raw = str(getattr(element, field, "") or "").strip()
            if not raw or len(raw) > 120:
                continue
            for pattern in _UNREAD_PATTERNS:
                match = pattern.search(raw)
                if match:
                    candidates.add(int(match.group(1)))
            if re.fullmatch(r"\d{1,6}", raw) and any(x in resource_id for x in ("badge", "unread", "counter")):
                candidates.add(int(raw))

    if len(candidates) == 1:
        return {"ok": True, "status": "observed", "app": app,
                "unread_count": next(iter(candidates)), "basis": "visible_unread_badge",
                "received_today": False, "message_bodies_read": False,
                "observed_at": observed_at}
    if len(candidates) > 1:
        return {"ok": False, "status": "ambiguous_count", "app": app,
                "received_today": False, "message_bodies_read": False,
                "observed_at": observed_at,
                "message": "The screen showed conflicting unread counts; no count was selected."}
    return {"ok": False, "status": "count_not_visible", "app": app,
            "received_today": False, "message_bodies_read": False,
            "observed_at": observed_at,
            "message": "No unambiguous unread badge was visible. This does not determine today's received-mail total."}
