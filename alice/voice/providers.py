"""Voice provider contract.

Alice can use installed/system voices immediately and can later attach a
properly licensed external TTS provider without changing the UI contract.
This module deliberately does not ship or reproduce an unauthorized
performer's voice.
"""
from __future__ import annotations
from dataclasses import dataclass
from typing import Protocol

class VoiceProvider(Protocol):
    name: str
    def speak(self, text: str) -> bool: ...

@dataclass
class VoiceProviderInfo:
    name: str
    authorized: bool
    available: bool
    detail: str

class VoiceProviderRegistry:
    def __init__(self):
        self._providers = {}

    def register(self, provider, *, authorized=True, detail=""):
        name=str(getattr(provider,"name",provider.__class__.__name__))
        self._providers[name]= (provider, VoiceProviderInfo(name,bool(authorized),True,detail))

    def list(self):
        return [info for _,info in self._providers.values()]

    def get(self,name):
        item=self._providers.get(str(name)); return item[0] if item else None
