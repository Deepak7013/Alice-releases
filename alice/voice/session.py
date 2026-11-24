"""Voice turn/session orchestration. It does not itself authorize actions."""
from __future__ import annotations
import time, uuid
from dataclasses import dataclass, field
from typing import Callable, Optional
from .stt import STTResult
from .tts import TTSResult

@dataclass
class VoiceTurn:
    id: str
    transcript: str
    response: str = ""
    stt: dict = field(default_factory=dict)
    tts: dict = field(default_factory=dict)
    status: str = "received"
    created_at: float = field(default_factory=time.time)

class VoiceSession:
    def __init__(self, stt=None, tts=None, command_handler: Optional[Callable]=None):
        self.stt, self.tts, self.command_handler = stt, tts, command_handler
        self.active = False; self.turns = []

    def start(self): self.active = True; return {"active": True}
    def stop(self): self.active = False; return {"active": False}

    def handle_audio(self, audio):
        if not self.active: raise RuntimeError("voice session is not active")
        if self.stt is None: raise RuntimeError("no speech-to-text adapter configured")
        result = self.stt.transcribe(audio)
        return self.handle_transcript(result)

    def handle_transcript(self, result):
        if isinstance(result, str): result = STTResult(result, 1.0, "direct")
        turn = VoiceTurn(uuid.uuid4().hex[:12], result.text, stt=result.to_dict())
        if not result.text:
            turn.status = "empty"; self.turns.append(turn); return turn
        try:
            response = self.command_handler(result.text) if self.command_handler else result.text
            turn.response = "" if response is None else str(response); turn.status = "completed"
            if self.tts and turn.response:
                spoken = self.tts.speak(turn.response); turn.tts = spoken.to_dict()
            self.turns.append(turn); return turn
        except Exception as e:
            turn.status = "failed"; turn.response = str(e); self.turns.append(turn); return turn
