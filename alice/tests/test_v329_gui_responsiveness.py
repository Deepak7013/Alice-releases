from pathlib import Path

def _text():
    return (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")

def test_persistence_is_not_on_tk_finish_path():
    text=_text()
    # Ignore nested Tk callbacks named ``finish``. The persistence boundary is
    # the actual AliceUI method, whose signature is stable and unambiguous.
    finish = text.index("    def finish(self,result,cancel_event):")
    voice_dialog = text.index("    def voice_dialog", finish)
    assert 'self.conversation.append("assistant", display)' not in text[finish:voice_dialog]
    segment = text[text.index("    def _persist_assistant_result"):finish]
    assert "self.memory.learn_outcome(request, display, self.updates.status().get(\"current_version\")" in segment

def test_stream_chunks_are_coalesced_before_tk_insert():
    text=_text()
    assert 'Coalesce adjacent stream chunks' in text
    assert 'pieces.append(str(nxt[1][1]))' in text

def test_entry_is_refocused_after_send_and_finish():
    text=_text()
    assert 'self.entry.delete(0,"end"); self._sync_message_to_native(); self._focus_message_entry()' in text
    focus=text[text.index("    def _focus_message_entry"):text.index("    def clear_visible_chat")]
    assert 'self.entry.focus_set()' in focus
    assert 'self.root.after_idle(self._refocus_entry)' in text

def test_version():
    root=Path(__file__).resolve().parents[2]
    assert (root/"VERSION.txt").read_text(encoding="utf-8").strip().startswith("ALICE v")
