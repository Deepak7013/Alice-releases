
from __future__ import annotations
from dataclasses import dataclass
from typing import Any, Callable

@dataclass
class VisionProviderResult:
    ok: bool
    text: str = ""
    raw: Any = None
    provider: str = ""
    error: str = ""

class VisionProvider:
    name = "base"
    def analyze(self, image, prompt: str) -> VisionProviderResult:
        raise NotImplementedError

class VisionRouter:
    """Routes vision work through Alice's configured provider stack.

    Providers are injected rather than hard-coded so credentials and
    provider selection remain in the existing AI provider layer.
    """
    def __init__(self, providers=None):
        self.providers = list(providers or [])

    def analyze(self, image, prompt: str) -> VisionProviderResult:
        errors = []
        for provider in self.providers:
            try:
                result = provider.analyze(image, prompt)
                if result.ok:
                    if not result.provider:
                        result.provider = provider.name
                    return result
                errors.append(f"{provider.name}: {result.error}")
            except Exception as exc:
                errors.append(f"{getattr(provider, 'name', 'unknown')}: {exc}")
        return VisionProviderResult(
            ok=False, error="; ".join(errors) or "no vision providers configured"
        )
