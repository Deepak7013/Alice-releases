"""Explicitly consented, isolated Piper CLI installation for Windows."""
from __future__ import annotations

import os
import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class PiperRuntimeInstallResult:
    ok: bool
    executable: str
    reason: str
    commands_run: int


def install_piper_runtime(
    project_root: str | Path,
    *,
    consent: bool = False,
    python_executable: str | Path,
    platform_name: str | None = None,
    runner: Callable = subprocess.run,
    timeout_seconds: int = 900,
) -> PiperRuntimeInstallResult:
    """Install piper-tts into ALICE's dedicated venv, never into the main environment.

    The package installation can execute third-party package code, so explicit user
    consent is mandatory. Only binary wheels are accepted; no source builds are run.
    """
    if not consent:
        return PiperRuntimeInstallResult(False, "", "explicit_install_consent_required", 0)
    os_name = platform_name or os.name
    if os_name not in {"nt", "Windows"}:
        return PiperRuntimeInstallResult(False, "", "windows_runtime_required", 0)
    if not 60 <= int(timeout_seconds) <= 3600:
        return PiperRuntimeInstallResult(False, "", "timeout_seconds_out_of_range", 0)
    root = Path(project_root).expanduser().resolve()
    python = Path(python_executable).expanduser().resolve()
    if not python.is_file():
        return PiperRuntimeInstallResult(False, "", "python_executable_not_found", 0)
    runtime_root = root / "alice_workspace" / "voice_runtime" / "piper_tts_venv"
    runtime_python = runtime_root / "Scripts" / "python.exe"
    piper_exe = runtime_root / "Scripts" / "piper.exe"
    if runtime_root.exists() and not runtime_python.is_file():
        return PiperRuntimeInstallResult(False, "", "existing_runtime_incomplete_manual_repair_required", 0)
    commands = []
    try:
        if not runtime_python.is_file():
            commands.append([str(python), "-m", "venv", str(runtime_root)])
            result = runner(commands[-1], capture_output=True, text=True, timeout=timeout_seconds,
                            check=False, shell=False)
            if int(getattr(result, "returncode", 1)) != 0 or not runtime_python.is_file():
                return PiperRuntimeInstallResult(False, "", "venv_creation_failed", len(commands))
        commands.append([str(runtime_python), "-m", "pip", "install", "--disable-pip-version-check",
                         "--only-binary=:all:", "piper-tts"])
        result = runner(commands[-1], capture_output=True, text=True, timeout=timeout_seconds,
                        check=False, shell=False)
        if int(getattr(result, "returncode", 1)) != 0:
            return PiperRuntimeInstallResult(False, "", "pip_install_failed_binary_wheels_only", len(commands))
        if not piper_exe.is_file():
            return PiperRuntimeInstallResult(False, "", "piper_cli_executable_missing_after_install", len(commands))
        commands.append([str(piper_exe), "--help"])
        result = runner(commands[-1], capture_output=True, text=True, timeout=min(timeout_seconds, 60),
                        check=False, shell=False)
        if int(getattr(result, "returncode", 1)) != 0:
            return PiperRuntimeInstallResult(False, "", "piper_cli_smoke_check_failed", len(commands))
        output = str(getattr(result, "stdout", "") or "") + "\n" + str(getattr(result, "stderr", "") or "")
        if "--model" not in output or "--output_file" not in output:
            return PiperRuntimeInstallResult(False, "", "piper_cli_arguments_incompatible", len(commands))
        return PiperRuntimeInstallResult(True, str(piper_exe), "piper_runtime_installed_and_cli_checked", len(commands))
    except subprocess.TimeoutExpired:
        return PiperRuntimeInstallResult(False, "", "piper_runtime_install_timeout", len(commands))
    except Exception:
        return PiperRuntimeInstallResult(False, "", "piper_runtime_install_error", len(commands))
