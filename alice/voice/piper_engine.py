"""Opt-in offline Piper neural TTS adapter for ALICE.

This adapter uses an already-installed Piper executable and model artifacts.
It does not download models, contact network services, or bundle model weights.
The caller remains responsible for fallback to the existing Windows/SAPI voice.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Callable


class PiperLocalVoiceEngine:
    name = "alice_piper_local_neural"
    local_owned = True
    remote_dependency = False
    offline = True

    def __init__(
        self,
        *,
        model_root: str | Path,
        model_path: str,
        config_path: str,
        executable: str = "piper",
        cache_dir: str | Path | None = None,
        max_text_chars: int = 4000,
        max_audio_bytes: int = 25 * 1024 * 1024,
        timeout_seconds: float = 45.0,
        runner: Callable = subprocess.run,
        playback: Callable[[Path], bool] | None = None,
    ) -> None:
        if not 1 <= int(max_text_chars) <= 20000:
            raise ValueError("max_text_chars_out_of_range")
        if not 1024 <= int(max_audio_bytes) <= 256 * 1024 * 1024:
            raise ValueError("max_audio_bytes_out_of_range")
        if not 1.0 <= float(timeout_seconds) <= 180.0:
            raise ValueError("timeout_seconds_out_of_range")
        self.model_root = Path(model_root).expanduser().resolve()
        self.model_path = str(model_path)
        self.config_path = str(config_path)
        self.executable = str(executable or "piper").strip()
        self.cache_dir = Path(cache_dir).expanduser().resolve() if cache_dir else self.model_root / "runtime_cache"
        self.max_text_chars = int(max_text_chars)
        self.max_audio_bytes = int(max_audio_bytes)
        self.timeout_seconds = float(timeout_seconds)
        self._runner = runner
        self._playback = playback
        self.last_error = ""

    def _resolve_artifact(self, relative: str) -> Path | None:
        raw = str(relative or "").strip()
        if not raw or "\\" in raw or Path(raw).is_absolute():
            return None
        if any(part in {"", ".", ".."} for part in Path(raw).parts):
            return None
        try:
            root = self.model_root.resolve(strict=True)
            target = (root / Path(raw)).resolve(strict=True)
            if not target.is_relative_to(root) or not target.is_file():
                return None
            return target
        except (OSError, RuntimeError, ValueError):
            return None

    def _resolve_executable(self) -> str | None:
        if not self.executable:
            return None
        candidate = Path(self.executable).expanduser()
        if candidate.is_absolute() or candidate.parent != Path("."):
            try:
                resolved = candidate.resolve(strict=True)
                return str(resolved) if resolved.is_file() else None
            except OSError:
                return None
        return shutil.which(self.executable)

    def can_generate(self, text: str) -> bool:
        clean = str(text if text is not None else "").strip()
        if not clean or len(clean) > self.max_text_chars:
            return False
        if not self._resolve_executable():
            return False
        model = self._resolve_artifact(self.model_path)
        config = self._resolve_artifact(self.config_path)
        if model is None or config is None:
            return False
        try:
            if model.stat().st_size <= 0 or config.stat().st_size <= 0 or config.stat().st_size > 1024 * 1024:
                return False
            config_data = json.loads(config.read_text(encoding="utf-8"))
            return isinstance(config_data, dict)
        except (OSError, ValueError, json.JSONDecodeError):
            return False

    @staticmethod
    def _valid_wav(path: Path, max_bytes: int) -> bool:
        try:
            size = path.stat().st_size
            if size < 44 or size > max_bytes:
                return False
            with wave.open(str(path), "rb") as stream:
                return (stream.getnframes() > 0 and stream.getframerate() > 0
                        and stream.getnchannels() in (1, 2)
                        and stream.getsampwidth() in (1, 2, 3, 4))
        except (OSError, EOFError, wave.Error):
            return False

    def _play_windows(self, path: Path) -> bool:
        if os.name != "nt" or not shutil.which("powershell"):
            self.last_error = "windows_playback_unavailable"
            return False
        script = r'''Add-Type -AssemblyName PresentationCore
$p = New-Object System.Windows.Media.MediaPlayer
try {
  $target = $env:ALICE_PIPER_WAV
  if (-not $target -or -not (Test-Path -LiteralPath $target)) { throw "WAV file missing" }
  $p.Open([Uri]$target)
  $limit=[DateTime]::UtcNow.AddSeconds(10)
  while (-not $p.NaturalDuration.HasTimeSpan) {
    if ([DateTime]::UtcNow -gt $limit) { throw "WAV metadata timeout" }
    Start-Sleep -Milliseconds 50
  }
  $p.Play(); $duration=$p.NaturalDuration.TimeSpan
  $limit=[DateTime]::UtcNow.AddSeconds([Math]::Max(20,$duration.TotalSeconds+10))
  while ($p.Position -lt $duration) {
    if ([DateTime]::UtcNow -gt $limit) { throw "WAV playback timeout" }
    Start-Sleep -Milliseconds 60
  }
  exit 0
} catch { [Console]::Error.WriteLine($_.Exception.Message); exit 2 } finally { $p.Close() }
'''
        env = os.environ.copy()
        env["ALICE_PIPER_WAV"] = str(path)
        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-NonInteractive", "-STA", "-ExecutionPolicy", "Bypass", "-Command", script],
                env=env, capture_output=True, text=True, timeout=max(20.0, self.timeout_seconds),
                check=False, creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            if result.returncode != 0:
                self.last_error = (result.stderr or result.stdout or "windows_playback_failed")[:500]
                return False
            return True
        except Exception as exc:
            self.last_error = str(exc)[:500]
            return False

    def speak(self, text: str) -> bool:
        clean = str(text if text is not None else "").strip()
        self.last_error = ""
        if not self.can_generate(clean):
            self.last_error = "local_model_or_input_not_ready"
            return False
        model = self._resolve_artifact(self.model_path)
        config = self._resolve_artifact(self.config_path)
        executable = self._resolve_executable()
        if model is None or config is None or executable is None:
            self.last_error = "local_model_or_executable_unavailable"
            return False
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            with tempfile.NamedTemporaryFile(prefix="alice_piper_", suffix=".wav", dir=self.cache_dir, delete=False) as temp:
                output = Path(temp.name)
            try:
                result = self._runner(
                    [executable, "--model", str(model), "--config", str(config), "--output_file", str(output)],
                    input=clean, text=True, capture_output=True, timeout=self.timeout_seconds,
                    check=False, shell=False,
                )
                if int(getattr(result, "returncode", 1)) != 0:
                    self.last_error = (getattr(result, "stderr", "") or getattr(result, "stdout", "") or "piper_synthesis_failed")[:500]
                    return False
                if not self._valid_wav(output, self.max_audio_bytes):
                    self.last_error = "generated_audio_invalid_or_too_large"
                    return False
                played = self._playback(output) if self._playback is not None else self._play_windows(output)
                if not played:
                    if not self.last_error:
                        self.last_error = "audio_playback_failed"
                    return False
                return True
            finally:
                try:
                    output.unlink(missing_ok=True)
                except OSError:
                    pass
        except subprocess.TimeoutExpired:
            self.last_error = "piper_synthesis_timeout"
            return False
        except Exception as exc:
            self.last_error = str(exc)[:500] or "piper_synthesis_failed"
            return False
