from pathlib import Path


def test_voice_engine_is_owned_by_one_worker_thread():
    text=Path("alice/voice/voice.py").read_text(encoding="utf-8")
    assert 'self._speech_thread = threading.Thread(target=self._speech_worker' in text
    assert 'self._warm_up()' in text[text.index('def _speech_worker'):text.index('    @staticmethod')]
    assert 'threading.Thread(target=self._warm_up' not in text
    assert 'self._speech_queue.put(("voice", self._selected_name))' in text


def test_voice_speech_path_does_not_enumerate_sapi_voices_per_utterance():
    text=Path("alice/voice/voice.py").read_text(encoding="utf-8")
    block=text[text.index('    def _speak_pyttsx3'):text.index('    def _speak_powershell')]
    assert 'current_voice()' not in block
    assert 'list_voices()' not in block


def test_fast_chat_prompt_removes_duplicate_acquired_knowledge():
    text=Path("alice/agent/agent.py").read_text(encoding="utf-8")
    stream=text[text.index('    def respond_text_stream'):text.index('    def run(')]
    assert stream.count('\nACQUIRED KNOWLEDGE:') <= 1
    assert '[-5000:]' in stream


def test_casual_chat_skips_expensive_knowledge_lookup():
    from alice.agent.agent import AliceAgent
    class K:
        def search(self,*a,**k):
            raise AssertionError("casual chat should not query acquired knowledge")
    a=AliceAgent.__new__(AliceAgent); a.knowledge_acquirer=K()
    assert a._knowledge_context("hello") == ""
    assert a._knowledge_context("what is your name") == ""
