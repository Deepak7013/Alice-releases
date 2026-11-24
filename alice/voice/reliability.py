"""Voice continuity state and deterministic diagnostics."""
from __future__ import annotations

class VoiceReliability:
    def __init__(self, voice): self.voice=voice
    def diagnose(self):
        status=self.voice.provider_status()
        if status.get("ready") and status.get("last_error"):
            status["recommendation"]="Voice engine recovered or has a recorded transient failure; retry the next utterance."
        elif status.get("ready"):
            status["recommendation"]="Voice output is available."
        else:
            status["recommendation"]="No usable Windows speech backend was detected."
        return status
