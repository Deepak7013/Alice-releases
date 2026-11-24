"""Safe local setup helpers for an explicitly user-supplied Piper voice profile."""
from __future__ import annotations

import json
import os
import shutil
import tempfile
from pathlib import Path
from typing import Any

from .engine_registry import LocalVoiceEngineRegistry
from .piper_bootstrap import bootstrap_piper_engine


_ALLOWED_MODEL_SUFFIXES = {".onnx"}


def _contained_file(root: Path, relative: str, *, suffixes: set[str] | None = None) -> Path:
    raw = str(relative or "").strip()
    candidate = Path(raw)
    if not raw or candidate.is_absolute() or "\\" in raw or any(p in {"", ".", ".."} for p in candidate.parts):
        raise ValueError("model_artifact_path_must_be_safe_relative_path")
    resolved_root = root.resolve(strict=True)
    resolved = (resolved_root / candidate).resolve(strict=True)
    if not resolved.is_relative_to(resolved_root) or not resolved.is_file():
        raise ValueError("model_artifact_must_be_file_inside_model_root")
    if suffixes and resolved.suffix.lower() not in suffixes:
        raise ValueError("model_artifact_extension_not_supported")
    if resolved.stat().st_size <= 0:
        raise ValueError("model_artifact_is_empty")
    return resolved


def prepare_piper_config(
    *,
    config_file: str | Path,
    model_root: str | Path,
    model_path: str,
    model_config_path: str,
    executable: str,
    confirm_female_profile: bool,
    timeout_seconds: float = 45.0,
    max_text_chars: int = 4000,
    max_audio_bytes: int = 25 * 1024 * 1024,
    overwrite: bool = False,
) -> dict[str, Any]:
    """Validate supplied local artifacts and atomically write ALICE's Piper config.

    This routine never downloads or executes the Piper binary. The caller must explicitly
    confirm that the selected model is a female voice and must opt in to overwriting.
    """
    if not confirm_female_profile:
        raise ValueError("female_voice_profile_confirmation_required")
    if not 1.0 <= float(timeout_seconds) <= 180.0:
        raise ValueError("timeout_seconds_out_of_range")
    if not 1 <= int(max_text_chars) <= 20000:
        raise ValueError("max_text_chars_out_of_range")
    if not 1024 <= int(max_audio_bytes) <= 256 * 1024 * 1024:
        raise ValueError("max_audio_bytes_out_of_range")

    root = Path(model_root).expanduser().resolve(strict=True)
    if not root.is_dir():
        raise ValueError("model_root_must_be_directory")
    model = _contained_file(root, model_path, suffixes=_ALLOWED_MODEL_SUFFIXES)
    model_config = _contained_file(root, model_config_path)
    try:
        parsed_model_config = json.loads(model_config.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise ValueError("model_config_must_be_valid_json") from exc
    if not isinstance(parsed_model_config, dict):
        raise ValueError("model_config_must_be_json_object")

    executable_text = str(executable or "").strip()
    if not executable_text:
        raise ValueError("piper_executable_required")
    executable_candidate = Path(executable_text).expanduser()
    if executable_candidate.is_absolute() or executable_candidate.parent != Path("."):
        try:
            resolved_executable = executable_candidate.resolve(strict=True)
        except OSError as exc:
            raise ValueError("piper_executable_not_found") from exc
        if not resolved_executable.is_file():
            raise ValueError("piper_executable_not_file")
        executable_text = str(resolved_executable)
    elif not shutil.which(executable_text):
        raise ValueError("piper_executable_not_found_on_path")

    target = Path(config_file).expanduser().resolve()
    if target.exists() and not overwrite:
        raise FileExistsError("piper_config_exists_use_overwrite_to_replace")
    previous_bytes = target.read_bytes() if target.exists() else None
    payload = {
        "model_root": str(root),
        "model_path": str(Path(model_path).as_posix()),
        "config_path": str(Path(model_config_path).as_posix()),
        "executable": executable_text,
        "gender": "female",
        "timeout_seconds": float(timeout_seconds),
        "max_text_chars": int(max_text_chars),
        "max_audio_bytes": int(max_audio_bytes),
    }
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="\n", dir=target.parent,
                                         prefix=target.name + ".", suffix=".tmp", delete=False) as stream:
            temp_name = stream.name
            json.dump(payload, stream, indent=2, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_name, target)
        temp_name = None
    finally:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass
    # Use ALICE's exact production bootstrap/admission path before reporting setup success.
    # It validates readiness but does not execute the Piper binary or synthesize audio.
    registry = LocalVoiceEngineRegistry()
    admission_result = bootstrap_piper_engine(registry, target)
    if not admission_result.registered:
        try:
            if previous_bytes is None:
                target.unlink(missing_ok=True)
            else:
                with tempfile.NamedTemporaryFile("wb", dir=target.parent, prefix=target.name + ".restore.",
                                                 suffix=".tmp", delete=False) as stream:
                    restore_name = stream.name
                    stream.write(previous_bytes)
                    stream.flush()
                    os.fsync(stream.fileno())
                os.replace(restore_name, target)
        except OSError:
            pass
        raise ValueError("alice_piper_admission_failed:" + str(admission_result.reason))
    return {"config_file": str(target), "model_file": str(model), "model_config_file": str(model_config),
            "executable": executable_text, "female_profile_confirmed": True, "written": True,
            "engine_ready": True, "admission_reason": admission_result.reason}
