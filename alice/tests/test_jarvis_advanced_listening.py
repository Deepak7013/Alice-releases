import json
import sys
import threading
import types
from contextlib import contextmanager

import pytest

from alice.voice.input import MicrophoneManager
from alice.voice.jarvis_listener import JarvisAdvancedListener, ListeningConfig


class FakeMic:
    def __init__(self, settings=None):
        self.settings=dict(settings or {})
        self._lock=threading.Lock()
    @contextmanager
    def capture_session(self):
        if not self._lock.acquire(False): raise RuntimeError("microphone already busy")
        try: yield
        finally: self._lock.release()
    def list_devices(self): return [{"index": 4, "name": "Test headset"}]
    def choose_best(self, devices): return devices[0]


class FakeStream:
    def __init__(self, frames, **_kwargs):
        self.frames=list(frames); self.closed=False; self.last=self.frames[-1]
    def __enter__(self): return self
    def __exit__(self, *_args): self.closed=True
    def read(self, _count):
        if self.frames: return self.frames.pop(0), False
        threading.Event().wait(0.01)
        return self.last, False


def pcm(value, count=1024):
    return (int(value).to_bytes(2,"little",signed=True))*count


def test_jarvis_listener_requires_explicit_google_audio_consent():
    listener=JarvisAdvancedListener(FakeMic({"allow_cloud_stt":"false"}))
    with pytest.raises(RuntimeError,match="sends captured audio to Google"):
        listener.start()


def test_local_whisper_config_can_run_without_google_audio_consent(monkeypatch):
    monkeypatch.setitem(sys.modules,"faster_whisper",types.SimpleNamespace())
    listener=JarvisAdvancedListener(FakeMic({"recognition_backend":"local_whisper","allow_cloud_stt":False}))
    listener._run=lambda:None
    assert listener.start()
    listener._thread.join(1)
    assert not listener.running


def test_local_whisper_transcribes_pcm_without_cloud_or_audio_upload(monkeypatch):
    import numpy as np
    seen={}
    class Segment:
        text="The colors are red, blue, green. The numbers are four, five, six."
    class Model:
        def __init__(self,name,**kwargs): seen["model"]=(name,kwargs)
        def transcribe(self,samples,**kwargs):
            seen["samples"]=samples
            seen["options"]=kwargs
            return iter([Segment()]),types.SimpleNamespace(language="en")
    monkeypatch.setitem(sys.modules,"faster_whisper",types.SimpleNamespace(WhisperModel=Model))
    listener=JarvisAdvancedListener(FakeMic({"allow_cloud_stt":False}))
    received=[]
    listener.on_transcript=lambda text,translated:received.append((text,translated))
    audio=(np.zeros(1600,dtype="<i2")).tobytes()
    config=ListeningConfig(recognition_backend="local_whisper",whisper_model="small.en")
    listener._transcribe(audio,16000,config)
    assert received==[(Segment.text,None)]
    assert seen["model"]==("small.en",{"device":"cpu","compute_type":"int8"})
    assert seen["options"]=={"language":"en","beam_size":5,"vad_filter":True}
    assert len(seen["samples"])==1600


def test_local_whisper_translation_runs_only_after_recognition_when_enabled(monkeypatch):
    class Model:
        def __init__(self,*_args,**_kwargs): pass
        def transcribe(self,*_args,**_kwargs):
            return iter([types.SimpleNamespace(text="hola")]),types.SimpleNamespace(language="es")
    monkeypatch.setitem(sys.modules,"faster_whisper",types.SimpleNamespace(WhisperModel=Model))
    calls=[]
    class Language:
        def __init__(self,code): self.code=code
        def get_translation(self,target):
            return types.SimpleNamespace(translate=lambda text: calls.append((text,self.code,target.code)) or "hello")
    argos_package=types.ModuleType("argostranslate")
    argos_package.__path__=[]
    argos_translate=types.ModuleType("argostranslate.translate")
    argos_translate.get_installed_languages=lambda:[Language("es"),Language("en")]
    monkeypatch.setitem(sys.modules,"argostranslate",argos_package)
    monkeypatch.setitem(sys.modules,"argostranslate.translate",argos_translate)
    listener=JarvisAdvancedListener(FakeMic({"allow_cloud_stt":False}))
    received=[]
    listener.on_transcript=lambda text,translated:received.append((text,translated))
    config=ListeningConfig(recognition_backend="local_whisper",translate_enabled=True,
                           source_language="es",target_language="en",
                           translation_backend="argos_offline")
    listener._transcribe(pcm(2000),16000,config)
    assert received==[("hola","hello")]
    assert calls==[("hola","es","en")]


def test_offline_translation_missing_dependency_reports_actionable_error(monkeypatch):
    listener=JarvisAdvancedListener(FakeMic({"allow_cloud_stt":False}))
    config=ListeningConfig(translate_enabled=True,source_language="es",target_language="en",
                           translation_backend="argos_offline")
    monkeypatch.delitem(sys.modules,"argostranslate",raising=False)
    monkeypatch.delitem(sys.modules,"argostranslate.translate",raising=False)
    with pytest.raises(RuntimeError,match="install Argos Translate"):
        listener._deliver_transcript("hola",config)


def test_configurable_thresholds_are_bounded_and_languages_are_explicit():
    config=ListeningConfig.from_settings({"ambient_calibration_seconds":99,"pause_threshold":0.01,
        "minimum_energy_threshold":-1,"source_language":"es","target_language":"en"})
    assert config.ambient_calibration_seconds==5.0
    assert config.pause_threshold==0.2
    assert config.minimum_energy_threshold==20.0
    assert (config.source_language,config.target_language)==("es","en")
    assert ListeningConfig.from_settings({"translate_enabled":"false"}).translate_enabled is False


def test_listener_calibrates_and_recognizes_repeated_utterances_then_releases_mic(monkeypatch):
    monkeypatch.setitem(sys.modules,"speech_recognition",types.SimpleNamespace())
    zero=pcm(0); voice=pcm(1200)
    frames=[zero]*4+[voice]*4+[zero]*4+[voice]*4+[zero]*4
    stream=FakeStream(frames)
    mic=FakeMic({"allow_cloud_stt":True,"ambient_calibration_seconds":0.2,
                 "minimum_energy_threshold":100,"energy_threshold_multiplier":2,
                 "pause_threshold":0.2,"phrase_threshold":0.1,"listen_timeout":2})
    observed=[]; statuses=[]; ready=threading.Event(); listener=None
    def transcript(text, translated):
        observed.append((text,translated))
        if len(observed)>=2:
            listener.stop(); ready.set()
    listener=JarvisAdvancedListener(mic,on_status=statuses.append,on_transcript=transcript,stream_factory=lambda **kw:stream)
    listener._transcribe=lambda _pcm,_rate,_config: listener.on_transcript("recognized",None)
    assert listener.start()
    assert ready.wait(2), f"listener did not recognize two successive phrases: {statuses}"
    listener._thread.join(1)
    assert observed==[("recognized",None),("recognized",None)]
    assert stream.closed
    assert mic._lock.acquire(False)
    mic._lock.release()


def test_microphone_initialization_error_is_reported_and_claim_released(monkeypatch):
    monkeypatch.setitem(sys.modules,"speech_recognition",types.SimpleNamespace())
    class BrokenStream:
        def __enter__(self): raise OSError("device unavailable")
        def __exit__(self,*_args): pass
    mic=FakeMic({"allow_cloud_stt":True})
    statuses=[]
    listener=JarvisAdvancedListener(mic,on_status=statuses.append,
        stream_factory=lambda **_kw:BrokenStream())
    assert listener.start()
    listener._thread.join(1)
    assert any("device unavailable" in state for state in statuses)
    assert mic._lock.acquire(False)
    mic._lock.release()


def test_listener_falls_back_to_default_input_when_preferred_device_cannot_open(monkeypatch):
    monkeypatch.setitem(sys.modules,"speech_recognition",types.SimpleNamespace())
    preferred={"index":7,"name":"Bluetooth Headset","default":False}
    fallback={"index":1,"name":"Built-in Microphone","default":True}
    mic=FakeMic({"allow_cloud_stt":True,"ambient_calibration_seconds":0.2,
                 "minimum_energy_threshold":100,"pause_threshold":0.2,"phrase_threshold":0.1})
    mic.list_devices=lambda:[fallback,preferred]
    mic.choose_best=lambda _devices:preferred
    attempts=[]
    class BadStream:
        def __enter__(self): raise OSError("blocking API unsupported")
        def __exit__(self,*_args): pass
    good=FakeStream([pcm(0)]*5)
    def stream_factory(*,device,**kwargs):
        attempts.append(device["index"])
        return BadStream() if device["index"]==7 else good
    statuses=[]; listener=None
    def stop_after_fallback(status):
        statuses.append(status)
        if "Calibrating ambient" in status: listener.stop()
    listener=JarvisAdvancedListener(mic,on_status=stop_after_fallback,stream_factory=stream_factory)
    assert listener.start()
    listener._thread.join(1)
    assert attempts==[7,1]
    assert good.closed
    assert any("trying another available input" in state for state in statuses)
    assert mic._lock.acquire(False)
    mic._lock.release()


def test_google_translation_uses_configured_source_and_destination(monkeypatch):
    calls=[]
    class Recognizer:
        operation_timeout=None
        def recognize_google(self,audio): return "hola"
    class AudioData:
        def __init__(self,*args): self.args=args
    sr=types.SimpleNamespace(Recognizer=Recognizer,AudioData=AudioData,
        UnknownValueError=type("UnknownValueError",(Exception,),{}),RequestError=type("RequestError",(Exception,),{}))
    monkeypatch.setitem(sys.modules,"speech_recognition",sr)
    monkeypatch.setitem(sys.modules,"mtranslate",types.SimpleNamespace(translate=lambda text,to_language,from_language:
        calls.append((text,to_language,from_language)) or "hello"))
    mic=FakeMic()
    received=[]
    listener=JarvisAdvancedListener(mic,on_transcript=lambda text,translated:received.append((text,translated)))
    listener._transcribe(b"pcm",16000,ListeningConfig(translate_enabled=True,source_language="es",target_language="en",
                                                       translation_backend="mtranslate_online"))
    assert received==[("hola","hello")]
    assert calls==[("hola","en","es")]


def test_translation_dependency_failure_is_reported_without_crashing_listener(monkeypatch):
    class Recognizer:
        operation_timeout=None
        def recognize_google(self,_audio): return "hello"
    sr=types.SimpleNamespace(Recognizer=Recognizer,AudioData=lambda *args:args,
        UnknownValueError=type("UnknownValueError",(Exception,),{}),RequestError=type("RequestError",(Exception,),{}))
    monkeypatch.setitem(sys.modules,"speech_recognition",sr)
    monkeypatch.delitem(sys.modules,"mtranslate",raising=False)
    # Simulate an absent optional dependency even when installed in the test venv.
    import builtins
    real_import = builtins.__import__
    def import_without_mtranslate(name, *args, **kwargs):
        if name == "mtranslate":
            raise ModuleNotFoundError("No module named mtranslate")
        return real_import(name, *args, **kwargs)
    monkeypatch.setattr(builtins, "__import__", import_without_mtranslate)
    listener=JarvisAdvancedListener(FakeMic())
    with pytest.raises(ModuleNotFoundError):
        listener._transcribe(b"pcm",16000,ListeningConfig(translate_enabled=True,
                                                           source_language="es",target_language="en",
                                                           translation_backend="mtranslate_online"))
    assert "Translation dependency/status" in listener._recognition_error(ModuleNotFoundError("No module named mtranslate"))


def test_translation_timeout_is_bounded_and_does_not_spawn_duplicate_requests():
    entered=threading.Event(); release=threading.Event()
    def slow_translate(*_args,**_kwargs):
        entered.set(); release.wait(1); return "late"
    listener=JarvisAdvancedListener(FakeMic())
    config=ListeningConfig(recognition_timeout=0.02,source_language="es",target_language="en")
    with pytest.raises(TimeoutError,match="timed out"):
        listener._translate_bounded(slow_translate,"hola",config)
    assert entered.is_set()
    with pytest.raises(TimeoutError,match="previous translation"):
        listener._translate_bounded(lambda *_a,**_k:"duplicate","hola",config)
    release.set()


def test_recognition_and_network_errors_have_distinct_recoverable_statuses(monkeypatch):
    unknown=type("UnknownValueError",(Exception,),{})
    request=type("RequestError",(Exception,),{})
    monkeypatch.setitem(sys.modules,"speech_recognition",types.SimpleNamespace(
        UnknownValueError=unknown,RequestError=request))
    listener=JarvisAdvancedListener(FakeMic())
    assert "not recognized" in listener._recognition_error(unknown())
    assert "network error" in listener._recognition_error(request("offline"))


def test_input_mode_preferences_are_isolated_and_microphone_claim_is_exclusive(tmp_path):
    manager=MicrophoneManager.__new__(MicrophoneManager)
    manager._lock=threading.RLock(); manager._capture_lock=threading.Lock(); manager.settings={}
    manager.path=tmp_path/"audio_input.json"
    manager.save_input_preferences(input_mode="jarvis_advanced",allow_cloud_stt=True,
                                   translate_enabled=False,target_language="en")
    assert json.loads(manager.path.read_text()) ["input_mode"]=="jarvis_advanced"
    with manager.capture_session():
        with pytest.raises(RuntimeError,match="already in use"):
            with manager.capture_session(): pass
    assert manager.settings["allow_cloud_stt"] is True
    assert "mode" not in manager.settings  # TTS mode is a separate persisted setting.


def test_status_does_not_claim_recognition_ready_without_model_or_cloud_consent(tmp_path,monkeypatch):
    m=MicrophoneManager.__new__(MicrophoneManager); m.settings={}; m._lock=threading.RLock()
    m.list_devices=lambda:[{"index":0,"name":"test mic"}]
    m.choose_best=lambda devices:devices[0]
    monkeypatch.setitem(sys.modules,"speech_recognition",types.SimpleNamespace())
    monkeypatch.setitem(sys.modules,"sounddevice",types.SimpleNamespace())
    monkeypatch.setitem(sys.modules,"vosk",None)
    monkeypatch.delenv("ALICE_STT_ALLOW_CLOUD",raising=False)
    result=m.status()
    assert result["ok"] is True  # Capture stack is present.
    assert result["recognition_ready"] is False
    assert "No recognizer configured" in result["recognition_backend"]


def test_jarvis_ui_exposes_both_modes_and_explicit_network_controls():
    from pathlib import Path
    app=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text(encoding="utf-8")
    assert 'values=("ALICE local-first","Jarvis Advanced")' in app
    assert "I explicitly allow Google to receive microphone audio" in app
    assert '"Local Whisper (offline)":"local_whisper"' in app
    assert "audio stays on this device" in app
    assert "Translate recognized text using mtranslate (online)" in app
    assert 'command=self._stop_jarvis_listener' in app
    assert 'self.jarvis_listener.stop(timeout=0.2)' in app

