"""Governed admission policy for verified local voice models."""
from __future__ import annotations
from dataclasses import dataclass

SUPPORTED_FORMATS = frozenset({"onnx", "piper", "safetensors", "pt", "pth", "f5-tts", "styletts2"})

@dataclass(frozen=True)
class ModelAdmission:
    admitted: bool
    model_name: str
    reason: str

class LocalVoiceModelAdmissionGate:
    """Side-effect-free policy gate; it never loads a model or grants permissions."""
    def evaluate(self, *, model_name: object, model_format: object,
                 local_owned: object, offline: object, manifest_verified: object,
                 license_reviewed: object, runtime_ready: object) -> ModelAdmission:
        name = str(model_name or "").strip()
        fmt = str(model_format or "").strip().lower()
        if not name:
            return ModelAdmission(False, "", "model_name_missing")
        if fmt not in SUPPORTED_FORMATS:
            return ModelAdmission(False, name, "model_format_unsupported")
        if local_owned is not True:
            return ModelAdmission(False, name, "local_ownership_required")
        if offline is not True:
            return ModelAdmission(False, name, "offline_capability_required")
        if manifest_verified is not True:
            return ModelAdmission(False, name, "model_artifacts_not_verified")
        if license_reviewed is not True:
            return ModelAdmission(False, name, "license_review_required")
        if runtime_ready is not True:
            return ModelAdmission(False, name, "runtime_readiness_unverified")
        return ModelAdmission(True, name, "local_model_admitted")
