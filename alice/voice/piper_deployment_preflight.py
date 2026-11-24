"""Preflight Piper deployment without speaking or executing the configured binary."""
from __future__ import annotations
import json, platform
from pathlib import Path
from .piper_model_provenance import audit_model_receipt, sha256_file

def run_piper_deployment_preflight(config_file, *, platform_name=None):
    """Check files/config/receipt and locate executable; does not run Piper or play audio."""
    effective_platform = platform_name or platform.system()
    report = {"format": 1, "platform": effective_platform, "test": "piper_deployment_preflight",
              "ready_for_runtime_test": False, "reason": "not_started",
              "stages": {"configuration": "not_run", "model_provenance": "not_run",
                         "model_artifacts": "not_run", "executable": "not_run",
                         "windows_playback_host": ("not_run" if effective_platform == "Windows" else "not_applicable_non_windows")},
              "model_sha256": None, "config_sha256": None, "executable_sha256": None,
              "execution_policy": "configured executable is not run by preflight"}
    try:
        cfg = Path(config_file).expanduser().resolve(strict=True)
        if not cfg.is_file() or cfg.stat().st_size > 16 * 1024: raise ValueError("config_missing_or_too_large")
        data = json.loads(cfg.read_text(encoding="utf-8"))
        if not isinstance(data, dict): raise ValueError("config_must_be_object")
        report["stages"]["configuration"] = "passed"
        root = Path(data.get("model_root", "")).expanduser()
        if not root.is_absolute(): root = cfg.parent / root
        root = root.resolve(strict=True)
        audit = audit_model_receipt(root)
        if not audit.get("ok"):
            report["stages"]["model_provenance"] = "failed"; report["reason"] = "model_provenance_audit_failed"
            return report
        report["stages"]["model_provenance"] = "passed"
        model = (root / str(data.get("model_path", ""))).resolve(strict=True)
        model_cfg = (root / str(data.get("config_path", ""))).resolve(strict=True)
        if not model.is_relative_to(root) or not model.is_file() or not model_cfg.is_relative_to(root) or not model_cfg.is_file():
            report["stages"]["model_artifacts"] = "failed"; report["reason"] = "model_artifact_invalid"
            return report
        report["model_sha256"] = sha256_file(model); report["config_sha256"] = sha256_file(model_cfg)
        report["stages"]["model_artifacts"] = "passed"
        executable = str(data.get("executable", "piper") or "piper").strip()
        candidate = Path(executable).expanduser()
        resolved = None
        if candidate.is_absolute() or candidate.parent != Path("."):
            try:
                target = candidate.resolve(strict=True)
                if target.is_file(): resolved = target
            except OSError: pass
        else:
            import shutil
            found = shutil.which(executable)
            if found: resolved = Path(found).resolve()
        if resolved is None:
            report["stages"]["executable"] = "failed"; report["reason"] = "piper_executable_not_found"
            return report
        report["executable_sha256"] = sha256_file(resolved)
        report["stages"]["executable"] = "passed"
        if effective_platform == "Windows":
            import shutil
            report["stages"]["windows_playback_host"] = "passed" if shutil.which("powershell") else "failed"
        else:
            report["stages"]["windows_playback_host"] = "not_applicable_non_windows"
        report["ready_for_runtime_test"] = (effective_platform == "Windows" and report["stages"]["windows_playback_host"] == "passed")
        report["reason"] = "preflight_ready_for_real_piper_test" if report["ready_for_runtime_test"] else "preflight_incomplete_or_non_windows"
        return report
    except (OSError, ValueError, TypeError, KeyError):
        if report["stages"]["configuration"] == "not_run": report["stages"]["configuration"] = "failed"
        report["reason"] = "configuration_or_model_validation_failed"
        return report
    except Exception:
        report["reason"] = "preflight_unexpected_failure"
        return report
