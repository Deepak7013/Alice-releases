"""Optional Fish Audio TTS adapter for an explicitly configured saved voice."""
from __future__ import annotations

import importlib.util
import os
import tempfile
from pathlib import Path
from typing import Callable

from .secret_store import FishAudioSecretStore


class FishAudioProvider:
    name = "fish_audio"
    TEST_SENTENCE = "Hello. This is a short ALICE Fish Audio voice test."

    def __init__(self, secrets: FishAudioSecretStore, cache_dir: str | Path, *,
                 client_factory: Callable | None = None, playback: Callable | None = None):
        self.secrets = secrets
        self.cache_dir = Path(cache_dir)
        self.client_factory = client_factory
        self.playback = playback

    def sdk_available(self) -> bool:
        if self.client_factory is not None:
            return True
        try:
            return importlib.util.find_spec("fishaudio") is not None
        except (ImportError, ValueError):
            return False

    def status(self, voice_id: str) -> dict:
        key_configured = self.secrets.has()
        voice_configured = bool(str(voice_id or "").strip())
        sdk_ready = self.sdk_available()
        ready = key_configured and voice_configured and sdk_ready
        reason = "ready" if ready else (
            "api_key_missing" if not key_configured else
            "voice_id_missing" if not voice_configured else "fish_audio_sdk_missing"
        )
        return {"provider": self.name, "key_configured": key_configured,
                "voice_id_configured": voice_configured, "sdk_available": sdk_ready,
                "ready": ready, "reason": reason}

    def _client(self, key: str):
        if self.client_factory is not None:
            return self.client_factory(key)
        try:
            from fishaudio import FishAudio
        except Exception as exc:
            raise RuntimeError("fish_audio_sdk_missing") from exc
        return FishAudio(api_key=key)

    @staticmethod
    def _safe_error(exc: Exception) -> str:
        status = getattr(exc, "status_code", None) or getattr(exc, "status", None)
        if isinstance(status, int) and 400 <= status <= 599:
            return f"fish_audio_http_{status}"
        return "fish_audio_request_failed"

    def speak(self, text: str, voice_id: str, cancel_event=None) -> bool:
        clean_text = str(text or "").strip()
        clean_voice = str(voice_id or "").strip()
        key = self.secrets.get()
        if not key or not clean_voice:
            raise RuntimeError("fish_audio_configuration_missing")
        if not clean_text:
            return False
        if cancel_event is not None and cancel_event.is_set():
            return False
        try:
            audio = self._client(key).tts.convert(text=clean_text, reference_id=clean_voice)
        except Exception as exc:
            raise RuntimeError(self._safe_error(exc)) from None
        finally:
            key = ""
        if not isinstance(audio, (bytes, bytearray)) or not audio:
            raise RuntimeError("fish_audio_empty_audio")
        if cancel_event is not None and cancel_event.is_set():
            return False
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        fd, temporary = tempfile.mkstemp(prefix="alice_fish_audio_", suffix=".mp3", dir=str(self.cache_dir))
        path = Path(temporary)
        try:
            with os.fdopen(fd, "wb") as stream:
                stream.write(audio)
                stream.flush()
                os.fsync(stream.fileno())
            if cancel_event is not None and cancel_event.is_set():
                return False
            if self.playback is None:
                raise RuntimeError("fish_audio_playback_unavailable")
            try:
                return bool(self.playback(path, cancel_event=cancel_event))
            except Exception:
                raise RuntimeError("fish_audio_playback_failed") from None
        finally:
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
