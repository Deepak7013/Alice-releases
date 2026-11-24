from types import SimpleNamespace

import pytest

from alice.android_intelligence.summary import read_mail_unread_count


class FakeController:
    def __init__(self, package, elements):
        self.package = package
        self.elements = elements
        self.serials = []

    def observe(self, serial):
        self.serials.append(serial)
        return SimpleNamespace(package=self.package, elements=self.elements)


def el(text="", desc="", resource="", cls="android.view.View", focused=False):
    return SimpleNamespace(text=text, content_desc=desc, resource_id=resource,
                           class_name=cls, focused=focused)


def test_gmail_unread_badge_returns_only_count():
    controller = FakeController("com.google.android.gm", [
        el(desc="7 unread messages", resource="gmail:inbox_badge"),
        el(text="Quarterly invoice from Example Corp"),
    ])
    result = read_mail_unread_count(controller, "device-1")
    assert result["ok"] is True
    assert result["unread_count"] == 7
    assert result["received_today"] is False
    assert result["message_bodies_read"] is False
    assert "invoice" not in repr(result).lower()
    assert controller.serials == ["device-1"]


def test_focused_editable_content_is_never_used_as_badge():
    controller = FakeController("com.google.android.gm", [
        el(text="9 unread messages", cls="android.widget.EditText", focused=True),
        el(text="Inbox"),
    ])
    result = read_mail_unread_count(controller, "device-1")
    assert result["status"] == "count_not_visible"
    assert "unread_count" not in result


def test_conflicting_visible_badges_fail_closed():
    controller = FakeController("com.google.android.gm", [
        el(text="7 unread messages"), el(desc="8 new emails"),
    ])
    result = read_mail_unread_count(controller, "device-1")
    assert result["status"] == "ambiguous_count"
    assert "unread_count" not in result


def test_unsupported_app_does_not_inspect_or_return_mail_labels():
    controller = FakeController("com.example.other", [el(text="12 unread messages")])
    result = read_mail_unread_count(controller, "device-1")
    assert result["status"] == "unsupported_app"
    assert "12 unread" not in repr(result)


@pytest.mark.parametrize("serial", ["", "bad serial", "x;bad", "x&bad"])
def test_invalid_device_serial_rejected_before_observation(serial):
    controller = FakeController("com.google.android.gm", [])
    with pytest.raises(ValueError):
        read_mail_unread_count(controller, serial)
    assert controller.serials == []
