"""Deterministic cache-key policy for local speech payloads."""
from __future__ import annotations
import hashlib
import json
from collections.abc import Mapping

def speech_cache_key(text: object, *, engine: object | None, profile: str = "natural",
                     voice: object | None = None, engine_version: object | None = None,
                     locale: str = "en-US", pronunciation: Mapping[str, str] | None = None,
                     rate: object | None = None, emotion: str | None = None) -> str | None:
    clean = str(text if text is not None else "").strip()
    name = str(getattr(engine, "name", "") or "").strip() if engine is not None else ""
    if not clean or not name:
        return None
    selected_voice = voice if voice is not None else getattr(engine, "voice", "")
    selected_version = engine_version if engine_version is not None else getattr(engine, "version", getattr(engine, "model_version", ""))
    dictionary = {str(k): str(v) for k, v in (pronunciation or {}).items()}
    payload = {
        "text": clean, "engine": name, "engine_version": str(selected_version or ""),
        "voice": str(selected_voice or ""), "profile": str(profile or "natural").strip().lower(),
        "locale": str(locale or "en-US").strip().lower(),
        "pronunciation": dict(sorted(dictionary.items())),
        "rate": None if rate is None else str(rate),
        "emotion": str(emotion or "").strip().lower(),
    }
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()
