"""Governed cache gateway for ALICE-owned local speech synthesis."""
from __future__ import annotations
from dataclasses import dataclass
from collections.abc import Mapping
from .cache_policy import speech_cache_key
from .cache_store import LocalSpeechCache

@dataclass(frozen=True)
class SynthesisCacheResult:
    ok: bool
    payload: bytes | None
    cache_hit: bool
    cache_key: str | None
    engine: str | None
    reason: str

class LocalSynthesisCacheGateway:
    """Reuse opaque synthesized audio only for a verified local/offline engine.

    The gateway does not play audio or make remote requests. Engines provide a
    synchronous synthesize(text) method returning bytes-like audio data.
    """
    def __init__(self, cache: LocalSpeechCache | None = None, *, max_payload_bytes: int = 32 * 1024 * 1024,
                 max_text_chars: int = 20000) -> None:
        if isinstance(max_payload_bytes, bool) or not isinstance(max_payload_bytes, int) or max_payload_bytes < 1:
            raise ValueError("max_payload_bytes_must_be_positive_integer")
        if isinstance(max_text_chars, bool) or not isinstance(max_text_chars, int) or max_text_chars < 1:
            raise ValueError("max_text_chars_must_be_positive_integer")
        self.cache=cache or LocalSpeechCache()
        self.max_payload_bytes=max_payload_bytes
        self.max_text_chars=max_text_chars

    def synthesize(self, engine: object | None, text: object, *, profile: str = "natural",
                   voice: object | None = None, engine_version: object | None = None,
                   locale: str = "en-US", pronunciation: Mapping[str,str] | None = None,
                   rate: object | None = None, emotion: str | None = None) -> SynthesisCacheResult:
        clean=str(text if text is not None else "").strip()
        name=str(getattr(engine,"name","") or "").strip() if engine is not None else ""
        if not clean: return SynthesisCacheResult(False,None,False,None,name or None,"text_missing")
        if len(clean) > self.max_text_chars:
            return SynthesisCacheResult(False,None,False,None,name or None,"text_too_large")
        if not name: return SynthesisCacheResult(False,None,False,None,None,"engine_name_missing")
        if not bool(getattr(engine,"local_owned",False)) or bool(getattr(engine,"remote_dependency",True)) or not bool(getattr(engine,"offline",False)):
            return SynthesisCacheResult(False,None,False,None,name,"local_engine_required")
        can_generate=getattr(engine,"can_generate",None)
        synthesize=getattr(engine,"synthesize",None)
        if not callable(can_generate) or not callable(synthesize):
            return SynthesisCacheResult(False,None,False,None,name,"synthesis_contract_missing")
        try:
            if not can_generate(clean): return SynthesisCacheResult(False,None,False,None,name,"engine_not_ready")
        except Exception:
            return SynthesisCacheResult(False,None,False,None,name,"engine_readiness_failed")
        key=speech_cache_key(clean,engine=engine,profile=profile,voice=voice,engine_version=engine_version,
                             locale=locale,pronunciation=pronunciation,rate=rate,emotion=emotion)
        if key is None: return SynthesisCacheResult(False,None,False,None,name,"cache_key_unavailable")
        cached=self.cache.get(key)
        if cached is not None: return SynthesisCacheResult(True,cached,True,key,name,"cache_hit")
        try: payload=synthesize(clean)
        except Exception: return SynthesisCacheResult(False,None,False,key,name,"synthesis_failed")
        if not isinstance(payload,(bytes,bytearray,memoryview)) or not payload:
            return SynthesisCacheResult(False,None,False,key,name,"invalid_audio_payload")
        # Check the bytes-like object's declared size before copying it.
        try:
            payload_size = len(payload)
        except Exception:
            return SynthesisCacheResult(False,None,False,key,name,"invalid_audio_payload")
        if payload_size > self.max_payload_bytes:
            return SynthesisCacheResult(False,None,False,key,name,"audio_payload_too_large")
        try:
            audio=bytes(payload)
        except Exception:
            return SynthesisCacheResult(False,None,False,key,name,"invalid_audio_payload")
        self.cache.put(key,audio)  # Cache capacity may be smaller than the output admission limit.
        return SynthesisCacheResult(True,audio,False,key,name,"synthesized_local_audio")
