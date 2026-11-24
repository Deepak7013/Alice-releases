from pathlib import Path


def test_voice_never_initializes_on_gui_thread():
    text=Path("alice/voice/voice.py").read_text(encoding="utf-8")
    assert 'self._speech_thread = threading.Thread(target=self._speech_worker' in text
    assert 'self._warm_up()' in text[text.index('def _speech_worker'):text.index('    def _speak_powershell')]
    assert 'threading.Thread(target=self._warm_up' not in text
    assert 'self._speech_queue.put(("speak",str(text),generation))' in text
    assert 'def stop(self):' in text and 'self._speech_queue.put(("stop",))' in text


def test_voice_uses_persistent_windows_sapi_broker():
    text=Path("alice/voice/voice.py").read_text(encoding="utf-8")
    assert 'System.Speech.Synthesis.SpeechSynthesizer' in text
    assert '__ALICE_READY__' in text and '__ALICE_DONE__' in text
    assert 'CREATE_NO_WINDOW' in text


def test_blank_stream_retries_non_stream_response():
    text=Path("alice/ui/app.py").read_text(encoding="utf-8")
    assert 'if not state.completed and not cancel_event.is_set():' in text
    assert 'self.agent.respond_text(text,concise=self.concise_mode' in text
    assert 'respond_text_recovery' in text


def test_update_request_is_handled_before_normal_chat():
    text=Path("alice/ui/app.py").read_text(encoding="utf-8")
    assert 'def _is_update_request(text):' in text
    assert 'if self._is_update_request(text):' in text
    assert 'self.updates.check()' in text


def test_update_center_exists():
    text=Path("alice/ui/app.py").read_text(encoding="utf-8")
    assert 'label="Updates"' in text
    assert 'askyesno("ALICE self-update"' in text


def test_update_check_does_not_install_automatically():
    text=Path("alice/ui/app.py").read_text(encoding="utf-8")
    assert 'def _wants_update_install(self, text):' in text
    assert 'if not self._wants_update_install(text):' in text
    assert 'askyesno("ALICE self-update"' in text
