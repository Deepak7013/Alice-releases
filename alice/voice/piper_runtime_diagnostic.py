"""Privacy-conscious Piper-only runtime diagnostic with explicit stage evidence."""
from __future__ import annotations
import json, os, tempfile, platform, time
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable
from .engine_registry import LocalVoiceEngineRegistry
from .piper_bootstrap import bootstrap_piper_engine
from .piper_model_provenance import audit_model_receipt, sha256_file

_TEST_TEXT = "Hello. This is ALICE's offline voice test."
_ALLOWED_ERRORS = {"windows_playback_unavailable", "audio_playback_failed", "piper_synthesis_timeout",
 "local_model_or_input_not_ready", "local_model_or_executable_unavailable", "generated_audio_invalid_or_too_large",
 "piper_synthesis_failed", "windows_playback_failed", "local_model_or_executable_not_ready"}

def run_piper_runtime_diagnostic(config_file: str | Path, receipt_path: str | Path, *,
                                 confirm_female: bool = False,
                                 bootstrapper: Callable = bootstrap_piper_engine,
                                 platform_name: str | None = None) -> dict:
    """Run Piper without fallback and atomically write a minimal, path-free receipt.

    The receipt reports the engine's synthesis/playback return value, not proof that a
    human heard the audio. Human confirmation remains a separate deployment check.
    """
    if not confirm_female:
        raise ValueError("female_profile_confirmation_required")
    target = Path(receipt_path).expanduser().resolve()
    effective_platform = platform_name or platform.system()
    result = {"format": 2, "created_utc": datetime.now(timezone.utc).isoformat(),
              "platform": effective_platform, "test": "piper_only_synthesis_and_playback",
              "female_profile_user_confirmed": True, "passed": False,
              "reason": "not_started", "model_sha256": None, "config_sha256": None,
              "engine_sha256": None, "error_category": None,
              "stages": {"configuration": "not_run", "provenance": "not_run",
                         "artifacts": "not_run", "engine_admission": "not_run",
                         "synthesis_playback": "not_run"},
              "elapsed_ms": 0, "playback_claim": "engine_return_value_only; human_hearing_not_verified"}
    started = time.monotonic()
    cfg = Path(config_file).expanduser()
    try:
        cfg = cfg.resolve(strict=True)
        if not cfg.is_file() or cfg.stat().st_size > 16 * 1024:
            raise ValueError("config_missing_or_too_large")
        data = json.loads(cfg.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            raise ValueError("config_must_be_object")
        result["stages"]["configuration"] = "passed"
        root = Path(data.get("model_root", "")).expanduser()
        if not root.is_absolute(): root = cfg.parent / root
        root = root.resolve(strict=True)
        audit = audit_model_receipt(root)
        if not audit.get("ok"):
            result["stages"]["provenance"] = "failed"
            result["reason"] = "model_provenance_audit_failed"
            return _finish(target, result, started)
        result["stages"]["provenance"] = "passed"
        model = (root / str(data.get("model_path", ""))).resolve(strict=True)
        model_config = (root / str(data.get("config_path", ""))).resolve(strict=True)
        if (not model.is_relative_to(root) or not model.is_file() or
                not model_config.is_relative_to(root) or not model_config.is_file()):
            result["stages"]["artifacts"] = "failed"
            result["reason"] = "configured_artifact_invalid"
            return _finish(target, result, started)
        result["model_sha256"] = sha256_file(model)
        result["config_sha256"] = sha256_file(model_config)
        result["stages"]["artifacts"] = "passed"
        registry = LocalVoiceEngineRegistry()
        admission = bootstrapper(registry, cfg)
        engine = getattr(admission, "engine", None)
        if not getattr(admission, "registered", False) or engine is None:
            result["stages"]["engine_admission"] = "failed"
            result["reason"] = "piper_engine_not_admitted"
            return _finish(target, result, started)
        result["stages"]["engine_admission"] = "passed"
        try:
            executable = engine._resolve_executable()
            if executable and Path(executable).is_file(): result["engine_sha256"] = sha256_file(executable)
        except (OSError, ValueError, AttributeError):
            pass
        speech_started = time.monotonic()
        result["passed"] = bool(engine.speak(_TEST_TEXT))
        result["speech_elapsed_ms"] = round((time.monotonic() - speech_started) * 1000)
        result["stages"]["synthesis_playback"] = "passed" if result["passed"] else "failed"
        result["reason"] = "piper_synthesis_and_playback_passed" if result["passed"] else "piper_synthesis_or_playback_failed"
        error = str(getattr(engine, "last_error", "") or "")
        result["error_category"] = error if error in _ALLOWED_ERRORS else (None if result["passed"] else "unclassified_engine_failure")
        if effective_platform != "Windows" and result["passed"]:
            result["reason"] = "engine_reported_success_non_windows_playback_unverified"
            result["passed"] = False
            result["stages"]["synthesis_playback"] = "unverified_platform"
    except (OSError, ValueError, KeyError, TypeError, json.JSONDecodeError):
        if result["stages"]["configuration"] == "not_run":
            result["stages"]["configuration"] = "failed"
        result["reason"] = "configuration_or_model_validation_failed"
    except Exception:
        result["reason"] = "diagnostic_unexpected_failure"
    return _finish(target, result, started)

def _finish(target: Path, result: dict, started: float) -> dict:
    result["elapsed_ms"] = max(0, round((time.monotonic() - started) * 1000))
    return _write_receipt(target, result)

def _write_receipt(target: Path, result: dict) -> dict:
    target.parent.mkdir(parents=True, exist_ok=True); temp = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=target.parent,
                                         prefix=target.name + ".", suffix=".tmp", delete=False) as stream:
            temp = stream.name; json.dump(result, stream, indent=2, ensure_ascii=False); stream.write("\n")
            stream.flush(); os.fsync(stream.fileno())
        os.replace(temp, target); temp = None
    finally:
        if temp:
            try: Path(temp).unlink(missing_ok=True)
            except OSError: pass
    # The saved receipt intentionally contains no absolute local paths or spoken text.
    return {**result, "receipt_path": str(target)}
