import json
import sys
import types
from pathlib import Path
import pytest
from alice.voice.input import MicrophoneManager


class FakeSpeechRecognition:
    class AudioData:
        def __init__(self, pcm, rate, width):
            self.pcm, self.rate, self.width = pcm, rate, width
    class UnknownValueError(Exception): pass
    class RequestError(Exception): pass
    class Recognizer:
        def recognize_google(self, audio):
            return 'cloud transcription'


def manager(tmp_path, settings=None):
    obj = MicrophoneManager.__new__(MicrophoneManager)
    obj.root = tmp_path
    obj.path = tmp_path / 'audio_input.json'
    obj.settings = dict(settings or {})
    return obj


def test_cloud_stt_is_not_used_without_explicit_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv('ALICE_STT_ALLOW_CLOUD', raising=False)
    m = manager(tmp_path)
    with pytest.raises(RuntimeError, match='Cloud speech recognition is disabled'):
        m._transcribe_pcm(b'pcm', 16000, FakeSpeechRecognition)


def test_cloud_stt_requires_and_respects_explicit_opt_in(tmp_path, monkeypatch):
    monkeypatch.delenv('ALICE_STT_ALLOW_CLOUD', raising=False)
    m = manager(tmp_path, {'stt_provider': 'google', 'allow_cloud_stt': True})
    assert m._transcribe_pcm(b'pcm', 16000, FakeSpeechRecognition) == 'cloud transcription'


def test_vosk_mode_requires_local_model_directory(tmp_path, monkeypatch):
    monkeypatch.delenv('ALICE_VOSK_MODEL_PATH', raising=False)
    m = manager(tmp_path, {'stt_provider': 'vosk'})
    with pytest.raises(RuntimeError, match='no valid model directory'):
        m._transcribe_pcm(b'pcm', 16000, FakeSpeechRecognition)


def test_vosk_local_model_is_preferred_and_transcribes_without_cloud(tmp_path, monkeypatch):
    model_dir = tmp_path / 'vosk-model'; model_dir.mkdir(); (model_dir / 'am').write_text('local')
    monkeypatch.delenv('ALICE_STT_ALLOW_CLOUD', raising=False)
    calls = []
    class Model:
        def __init__(self, path): calls.append(('model', path))
    class Recognizer:
        def __init__(self, model, rate): calls.append(('recognizer', rate))
        def AcceptWaveform(self, pcm): calls.append(('pcm', pcm))
        def FinalResult(self): return json.dumps({'text': 'hello alice'})
    monkeypatch.setitem(sys.modules, 'vosk', types.SimpleNamespace(Model=Model, KaldiRecognizer=Recognizer))
    m = manager(tmp_path, {'stt_provider': 'auto', 'vosk_model_path': str(model_dir)})
    assert m._transcribe_pcm(b'local-pcm', 16000, FakeSpeechRecognition) == 'hello alice'
    assert ('pcm', b'local-pcm') in calls
