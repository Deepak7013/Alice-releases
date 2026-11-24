"""Speech-to-text adapters. Hardware/network access is optional and injected."""
from __future__ import annotations
from typing import Callable, Optional

class STTResult:
    def __init__(self, text: str = "", confidence: float = 0.0, provider: str = ""):
        self.text = text.strip(); self.confidence = float(confidence); self.provider = provider
    def to_dict(self): return {"text": self.text, "confidence": self.confidence, "provider": self.provider}

class SpeechToText:
    def transcribe(self, audio) -> STTResult:
        raise NotImplementedError

class CallableSTT(SpeechToText):
    def __init__(self, fn: Callable): self.fn = fn
    def transcribe(self, audio):
        value = self.fn(audio)
        if isinstance(value, STTResult): return value
        return STTResult(str(value or ""), 1.0 if value else 0.0, "callable")

class SpeechRecognitionSTT(SpeechToText):
    """Optional adapter using SpeechRecognition. Import occurs only at runtime."""
    def __init__(self, recognizer=None): self.recognizer = recognizer
    def transcribe(self, audio) -> STTResult:
        import speech_recognition as sr
        r = self.recognizer or sr.Recognizer()
        try:
            text = r.recognize_google(audio)
            return STTResult(text, 0.8, "google-speech-recognition")
        except Exception:
            return STTResult("", 0.0, "google-speech-recognition")
