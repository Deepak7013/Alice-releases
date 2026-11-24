import os
from pathlib import Path
import tkinter as tk

import pytest

from alice.ui.windows_accessibility import WindowsAccessibleEntry, set_native_accessible_name


class _Entry:
    def __init__(self, value):
        self.value = value
    def get(self):
        return self.value
    def delete(self, *_args):
        self.value = ""
    def insert(self, _index, value):
        self.value = value


class _Native:
    available = True
    def __init__(self, value, focused=False):
        self.value = value
        self.focused = focused
    def get_value(self):
        return self.value
    def has_focus(self):
        return self.focused


def test_empty_unfocused_native_mirror_does_not_erase_tk_draft():
    from alice.ui.app import AliceUI
    app = AliceUI.__new__(AliceUI)
    app.entry = _Entry("hello Alice")
    app._native_accessible_entry = _Native("")
    app._sync_message_from_native()
    assert app.entry.get() == "hello Alice"


def test_native_composer_exact_text_is_copied_to_backing_entry():
    from alice.ui.app import AliceUI
    app = AliceUI.__new__(AliceUI)
    app.entry = _Entry("")
    app._native_accessible_entry = _Native("hello Alice")
    app._sync_message_from_native()
    assert app.entry.get() == "hello Alice"


def test_focused_empty_native_composer_remains_authoritative():
    from alice.ui.app import AliceUI
    app = AliceUI.__new__(AliceUI)
    app.entry = _Entry("stale text")
    app._native_accessible_entry = _Native("", focused=True)
    app._sync_message_from_native()
    assert app.entry.get() == ""


def test_failed_stream_renders_visible_assistant_error():
    import threading
    from alice.ui.app import AliceUI

    class Widget:
        def config(self, **_kwargs): pass
    class Root:
        def after_idle(self, callback): pass
    class Voice:
        def is_enabled(self): return False

    app = AliceUI.__new__(AliceUI)
    app._cancel_event = threading.Event()
    event = app._cancel_event
    app._last_request_text = "hello"
    app.stop_button = Widget()
    app.activity = Widget()
    app.root = Root()
    app.voice = Voice()
    app._hud_chatbox = None
    app.provider_status = lambda: "provider unavailable"
    app._stream_end = lambda _event: None
    visible = []
    app.say = lambda speaker, text: visible.append((speaker, text))

    AliceUI.finish(app, {"status": "failed", "error": "provider rejected request", "streamed": True}, event)

    assert visible == [("Alice", "Error: provider rejected request")]


def test_windows_accessible_entry_has_stable_native_control_ids():
    assert WindowsAccessibleEntry.CONTROL_ID == 8101
    assert WindowsAccessibleEntry.LABEL_ID == 8100


def test_main_composer_is_read_from_native_control_before_dispatch():
    app_source = (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")
    send_body = app_source[app_source.index("    def send(self):"):app_source.index("    def stop_current")]

    assert "self._sync_message_from_native()" in send_body
    assert "self._sync_message_to_native()" in send_body
    assert "self._focus_message_entry()" in send_body
    assert "WindowsAccessibleEntry(self.root,bottom,self.entry,self.send)" in app_source


@pytest.mark.skipif(os.name != "nt", reason="Windows native controls are required")
def test_native_edit_round_trips_exact_text_and_button_accessible_name():
    import ctypes
    from ctypes import wintypes

    root = tk.Tk()
    root.withdraw()
    parent = tk.Frame(root)
    parent.pack(fill="x")
    anchor = tk.Entry(parent)
    anchor.pack(fill="x")
    button = tk.Button(parent, text="Send")
    button.pack()
    root.update_idletasks()
    submitted = []
    native = WindowsAccessibleEntry(root, parent, anchor, lambda: submitted.append(native.get_value()))
    try:
        assert native.available, native.error
        native.set_value("fresh exact text 104")
        assert native.get_value() == "fresh exact text 104"
        assert set_native_accessible_name(button, "Send")
        get_text = ctypes.WinDLL("user32", use_last_error=True).GetWindowTextW
        get_text.argtypes = [wintypes.HWND, wintypes.LPWSTR, ctypes.c_int]
        get_text.restype = ctypes.c_int
        label = ctypes.create_unicode_buffer(32)
        assert get_text(int(button.winfo_id()), label, len(label)) == 4
        assert label.value == "Send"
    finally:
        native.close()
        root.destroy()


@pytest.mark.skipif(os.name == "nt", reason="Non-Windows fallback path only")
def test_native_entry_degrades_cleanly_off_windows():
    root = object()
    native = WindowsAccessibleEntry(root, object(), object(), lambda: None)

    assert native.available is False
    assert native.hwnd == 0
