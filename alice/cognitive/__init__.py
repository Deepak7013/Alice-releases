"""Cognitive services with lazy exports to avoid reasoning import cycles."""

__all__ = ["CognitiveCore", "CoreDecision"]


def __getattr__(name):
    if name in __all__:
        from .core import CognitiveCore, CoreDecision
        return {"CognitiveCore": CognitiveCore, "CoreDecision": CoreDecision}[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
