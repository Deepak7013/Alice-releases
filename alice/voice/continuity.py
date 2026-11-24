"""Female voice continuity guard for ALICE upgrades and restarts."""
from __future__ import annotations

import hashlib
import json
import time
from pathlib import Path


class VoiceContinuityGuard:
    VERSION = "v3.55.0"

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    @staticmethod
    def fingerprint(voice_id="", name="", mode="sapi", neural_voice=""):
        basis = "|".join(str(x or "").strip().lower() for x in (voice_id, name, mode, neural_voice))
        return hashlib.sha256(basis.encode("utf-8")).hexdigest()[:20]

    def remember(self, *, voice_id="", name="", mode="sapi", neural_voice=""):
        payload = {
            "schema": self.VERSION,
            "voice_id": str(voice_id or ""),
            "name": str(name or ""),
            "mode": str(mode or "sapi"),
            "neural_voice": str(neural_voice or ""),
            "fingerprint": self.fingerprint(voice_id, name, mode, neural_voice),
            "updated_at": time.time(),
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
        tmp.replace(self.path)
        return payload

    def load(self):
        try:
            value = json.loads(self.path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except Exception:
            return {}

    def compare(self, *, voice_id="", name="", mode="sapi", neural_voice=""):
        saved = self.load()
        current = self.fingerprint(voice_id, name, mode, neural_voice)
        if not saved:
            return {"ok": True, "state": "uninitialized", "current": current}
        expected = str(saved.get("fingerprint", ""))
        return {
            "ok": bool(expected and expected == current),
            "state": "preserved" if expected == current else "changed",
            "expected": expected,
            "current": current,
            "saved_name": saved.get("name", ""),
        }

    def recover_settings(self):
        """Return prior voice preferences only when the continuity record verifies."""
        saved = self.load()
        voice_id = str(saved.get("voice_id", "") or "")
        name = str(saved.get("name", "") or "")
        mode = str(saved.get("mode", "") or "")
        neural_voice = str(saved.get("neural_voice", "") or "")
        expected = str(saved.get("fingerprint", "") or "")
        if mode not in {"sapi", "neural", "piper", "fish_audio"} or not expected:
            return None
        if expected != self.fingerprint(voice_id, name, mode, neural_voice):
            return None
        if not (voice_id or neural_voice):
            return None
        recovered = {
            "voice_name": voice_id,
            "mode": mode,
            "neural_voice": neural_voice,
            "enabled": True,
        }
        if mode == "fish_audio":
            recovered["fish_audio_voice_id"] = voice_id
            recovered["voice_name"] = ""
        return recovered
