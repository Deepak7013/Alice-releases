import threading
from types import SimpleNamespace
from alice.voice.voice import Voice


class Router:
    def __init__(self): self.calls=[]
    def speak(self, text):
        self.calls.append(text)
        return SimpleNamespace(spoken=True, provider='alice_piper_local_neural', reason='ok')


def make_voice():
    v=Voice.__new__(Voice)
    v._voice_mode='piper'; v._neural_voice=''; v._selected_name=''
    v._speech_generation=0; v._speech_generation_lock=threading.Lock()
    v._active_speech_cancel=threading.Event(); v._spoken_count=0; v._failure_count=0
    v._last_provider=''; v._last_error=''; v._local_voice_router=Router()
    return v


def test_speech_path_removes_literal_emoji_urls_and_markdown_only_for_audio():
    v=make_voice()
    canonical='**Hello** there! https://example.com/path 😊'
    assert v._speak_with_recovery(canonical)
    assert v._local_voice_router.calls == ['Hello there!']
    assert canonical == '**Hello** there! https://example.com/path 😊'


def test_emoji_only_response_does_not_send_empty_speech():
    v=make_voice()
    assert not v._speak_with_recovery('😊🎉')
    assert v._local_voice_router.calls == []


def test_plain_text_is_preserved_for_speech():
    v=make_voice()
    assert v._speak_with_recovery('Hello, Alice.')
    assert v._local_voice_router.calls == ['Hello, Alice.']
