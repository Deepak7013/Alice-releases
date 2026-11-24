"""Text-to-speech adapters with a safe no-op fallback."""
from __future__ import annotations
from typing import Callable

class TTSResult:
    def __init__(self, spoken: bool, provider: str = "", error: str = ""):
        self.spoken = bool(spoken); self.provider = provider; self.error = error
    def to_dict(self): return {"spoken": self.spoken, "provider": self.provider, "error": self.error}

class TextToSpeech:
    def speak(self, text: str) -> TTSResult: raise NotImplementedError

class CallableTTS(TextToSpeech):
    def __init__(self, fn: Callable): self.fn = fn
    def speak(self, text):
        try:
            self.fn(str(text)); return TTSResult(True, "callable")
        except Exception as e: return TTSResult(False, "callable", str(e))

class Pyttsx3TTS(TextToSpeech):
    def __init__(self): self.engine = None
    def speak(self, text):
        try:
            import pyttsx3
            if self.engine is None: self.engine = pyttsx3.init()
            self.engine.say(str(text)); self.engine.runAndWait()
            return TTSResult(True, "pyttsx3")
        except Exception as e:
            return TTSResult(False, "pyttsx3", str(e))
