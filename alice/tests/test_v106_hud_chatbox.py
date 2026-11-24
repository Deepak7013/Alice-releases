from alice.ui.hud_chatbox import HUDChatbox


class FakeEntry:
    def __init__(self, value=""):
        self.value = value
        self.focused = False

    def get(self):
        return self.value

    def delete(self, _start, _end):
        self.value = ""

    def focus_set(self):
        self.focused = True


class FakeTranscript:
    def __init__(self):
        self.parts = []
        self.state = "disabled"

    def configure(self, **kwargs):
        self.state = kwargs.get("state", self.state)

    def insert(self, _where, text, tag=None):
        self.parts.append((text, tag))

    def see(self, _where):
        pass

    def delete(self, _start, _end):
        self.parts.clear()


class FakeWindow:
    def __init__(self):
        self.destroy_count = 0

    def destroy(self):
        self.destroy_count += 1


def test_hud_chatbox_submits_to_shared_conversation_and_clears_input():
    submitted = []
    box = HUDChatbox.__new__(HUDChatbox)
    box._closed = False
    box.input = FakeEntry("  status report  ")
    box.on_submit = submitted.append

    assert box.submit() is True
    assert box.input.value == ""
    assert submitted == ["status report"]
    assert box.submit() is False


def test_hud_chatbox_streams_and_tags_messages_without_copying_reference_art():
    box = HUDChatbox.__new__(HUDChatbox)
    box._closed = False
    box._streaming = False
    box.transcript = FakeTranscript()

    box.append("You", "hello")
    box.begin_stream()
    box.stream("ALICE response")
    box.end_stream()

    assert box.transcript.state == "disabled"
    assert ("You: ", "speaker_you") in box.transcript.parts
    assert ("Alice: ", "speaker_alice") in box.transcript.parts
    assert any(text == "ALICE response" for text, _tag in box.transcript.parts)
    assert HUDChatbox.COLORS["background"] == "#07131f"
    assert HUDChatbox.COLORS["cyan"] == "#61e6ff"


def test_hud_chatbox_close_calls_owner_once():
    closed = []
    box = HUDChatbox.__new__(HUDChatbox)
    box._closed = False
    box.window = FakeWindow()
    box.on_close = lambda: closed.append(True)

    box.close()
    box.close()

    assert box.window.destroy_count == 1
    assert closed == [True]


def test_main_window_offers_optional_hud_and_mirrors_streamed_conversation():
    from pathlib import Path

    source = Path("alice/ui/app.py").read_text(encoding="utf-8")
    assert 'text="HUD CHAT",command=self.toggle_hud_chat' in source
    assert "def _send_hud_text(self,text):" in source
    assert "self._hud_chatbox.begin_stream()" in source
    assert "self._hud_chatbox.stream(piece)" in source
    assert "self._hud_chatbox.append(speaker,text)" in source
