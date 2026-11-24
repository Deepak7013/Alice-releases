from alice.voice.voice import Voice
from alice.voice.reliability import VoiceReliability

class FakeVoice:
    def provider_status(self):
        return {"ready": True, "last_error": "", "spoken_count": 2, "failure_count": 0}

def test_voice_reliability_reports_ready():
    r=VoiceReliability(FakeVoice()).diagnose()
    assert r["ready"] is True
    assert "available" in r["recommendation"]

def test_voice_queue_api_exists():
    assert callable(getattr(Voice, "speak_async"))
    assert callable(getattr(Voice, "provider_status"))

def test_voice_retries_after_engine_failure():
    class V(Voice):
        def __init__(self):
            self.calls=0; self._last_error=""; self._last_provider=""; self._spoken_count=0; self._failure_count=0
        def _speak_pyttsx3(self,text,force_new=False):
            self.calls += 1
            if self.calls == 1: raise RuntimeError("engine broke")
            return True
        def _speak_powershell(self,text): return False
    v=V()
    assert v._speak_with_recovery("hello") is True
    assert v.calls == 2
    assert v._spoken_count == 1
