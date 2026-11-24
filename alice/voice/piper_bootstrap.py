"""Strict opt-in bootstrap for registering a configured local Piper voice engine."""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from .engine_registry import EngineAdmission, LocalVoiceEngineRegistry
from .piper_engine import PiperLocalVoiceEngine

MAX_CONFIG_BYTES = 16 * 1024
_ALLOWED_KEYS = {
    "model_root", "model_path", "config_path", "executable",
    "max_text_chars", "max_audio_bytes", "timeout_seconds", "gender",
}
_REQUIRED_KEYS = {"model_root", "model_path", "config_path"}


@dataclass(frozen=True)
class PiperBootstrapResult:
    loaded: bool
    registered: bool
    reason: str
    admission: EngineAdmission | None = None
    engine: PiperLocalVoiceEngine | None = None
    diagnostic: str = ""


def bootstrap_piper_engine(
    registry: LocalVoiceEngineRegistry,
    config_file: str | Path,
    *,
    runner: Callable | None = None,
    playback: Callable | None = None,
) -> PiperBootstrapResult:
    """Load explicit local-model configuration and register only a ready engine.

    This function never downloads a model or changes UI/provider preferences. Invalid
    configuration leaves the registry untouched so the caller can retain its fallback.
    """
    try:
        config_path = Path(config_file).expanduser().resolve(strict=True)
    except FileNotFoundError:
        return PiperBootstrapResult(False, False, "config_unreadable_or_invalid", diagnostic="config_file_not_found")
    except (OSError, ValueError, RuntimeError):
        return PiperBootstrapResult(False, False, "config_unreadable_or_invalid", diagnostic="config_path_unreadable_or_invalid")
    try:
        if not config_path.is_file():
            return PiperBootstrapResult(False, False, "config_unreadable_or_invalid", diagnostic="config_path_not_a_file")
        if config_path.stat().st_size > MAX_CONFIG_BYTES:
            return PiperBootstrapResult(False, False, "config_missing_or_too_large", diagnostic="config_exceeds_size_limit")
        data = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return PiperBootstrapResult(False, False, "config_unreadable_or_invalid", diagnostic="config_json_invalid")
    except UnicodeDecodeError:
        return PiperBootstrapResult(False, False, "config_unreadable_or_invalid", diagnostic="config_not_utf8")
    except (OSError, ValueError):
        return PiperBootstrapResult(False, False, "config_unreadable_or_invalid", diagnostic="config_read_failed")
    if not isinstance(data, dict):
        return PiperBootstrapResult(False, False, "config_must_be_object", diagnostic="config_root_not_object")
    if set(data) - _ALLOWED_KEYS:
        return PiperBootstrapResult(False, False, "config_contains_unknown_fields", diagnostic="config_has_unsupported_fields")
    if not _REQUIRED_KEYS.issubset(data):
        return PiperBootstrapResult(False, False, "config_required_fields_missing", diagnostic="config_missing_required_fields")
    for key in _REQUIRED_KEYS:
        if not isinstance(data[key], str) or not data[key].strip():
            return PiperBootstrapResult(False, False, "config_field_invalid", diagnostic="config_required_field_not_nonempty_string")
    if "gender" in data and (not isinstance(data["gender"], str) or data["gender"].strip().lower() not in {"female", "f"}):
        return PiperBootstrapResult(False, False, "only_female_piper_profiles_are_allowed", diagnostic="config_gender_not_confirmed_female")
    model_root = Path(data["model_root"]).expanduser()
    if not model_root.is_absolute():
        model_root = config_path.parent / model_root
    kwargs = {
        "model_root": model_root,
        "model_path": data["model_path"],
        "config_path": data["config_path"],
        "executable": data.get("executable", "piper"),
        "max_text_chars": data.get("max_text_chars", 4000),
        "max_audio_bytes": data.get("max_audio_bytes", 25 * 1024 * 1024),
        "timeout_seconds": data.get("timeout_seconds", 45.0),
    }
    try:
        engine = PiperLocalVoiceEngine(**kwargs, **({"runner": runner} if runner is not None else {}),
                                       **({"playback": playback} if playback is not None else {}))
    except (TypeError, ValueError, OSError):
        return PiperBootstrapResult(False, False, "engine_configuration_rejected", diagnostic="engine_config_type_or_value_rejected")
    if not engine.can_generate("ALICE local voice readiness probe"):
        return PiperBootstrapResult(True, False, "local_model_or_executable_not_ready", engine=engine)
    try:
        admission = registry.register(engine)
    except Exception:
        return PiperBootstrapResult(True, False, "registry_admission_failed", engine=engine)
    if not admission.admitted:
        return PiperBootstrapResult(True, False, admission.reason, admission=admission, engine=engine)
    return PiperBootstrapResult(True, True, "local_piper_engine_registered", admission=admission, engine=engine)
