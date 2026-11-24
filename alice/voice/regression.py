from __future__ import annotations
from dataclasses import dataclass,asdict
from alice.voice.continuity import VoiceContinuityGuard

@dataclass(frozen=True)
class VoiceRegressionResult:
    ok:bool; state:str; expected:str=""; current:str=""
    def as_dict(self): return asdict(self)

def verify_voice_continuity(path, *, voice_id="", name="", mode="sapi", neural_voice=""):
    r=VoiceContinuityGuard(path).compare(voice_id=voice_id,name=name,mode=mode,neural_voice=neural_voice)
    return VoiceRegressionResult(bool(r.get("ok")),str(r.get("state","unknown")),str(r.get("expected","")),str(r.get("current","")))
