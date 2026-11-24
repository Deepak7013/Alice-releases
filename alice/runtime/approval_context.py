"""Thread-local context for a user-approved UI request."""
from __future__ import annotations

from contextlib import contextmanager
from contextvars import ContextVar


_UI_APPROVED = ContextVar("alice_ui_approved_action",default=False)


@contextmanager
def ui_approved_action(enabled=True):
    token=_UI_APPROVED.set(bool(enabled))
    try:
        yield
    finally:
        _UI_APPROVED.reset(token)


def is_ui_approved_action():
    return _UI_APPROVED.get() is True
