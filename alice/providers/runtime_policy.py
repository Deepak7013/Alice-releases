"""Provider-independent runtime policy for normal reasoning."""
from dataclasses import dataclass
import os

@dataclass(frozen=True)
class RuntimePolicy:
    mode: str
    allow_remote_fallback: bool

    @classmethod
    def from_env(cls):
        mode = str(os.getenv("ALICE_RUNTIME_MODE", "gemini_primary") or "gemini_primary").strip().lower()
        if mode in {"local", "local-only", "local_only", "offline", "local_required"}:
            return cls("local_required", False)
        if mode in {"gemini", "gemini_primary", "gemini-primary"}:
            return cls("gemini_primary", False)
        for provider in ("openai", "anthropic", "groq", "openrouter", "nvidia"):
            if mode in {provider, provider + "_primary", provider + "-primary"}:
                return cls(provider + "_primary", False)
        # Unknown values fail closed to the explicitly selected primary brain.
        return cls("gemini_primary", False)

    def order(self, candidates, local_ready=False):
        candidates=list(candidates)
        if self.mode=="local_required": return ["local"] if local_ready else []
        if self.mode=="gemini_primary": return ["gemini"] if "gemini" in candidates else []
        for provider in ("openai", "anthropic", "groq", "openrouter", "nvidia"):
            if self.mode == provider + "_primary":
                return [provider] if provider in candidates else []
        if self.mode=="local_first" and local_ready and "local" in candidates:
            return ["local"]+[p for p in candidates if p!="local"]
        return candidates
