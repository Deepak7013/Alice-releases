from pathlib import Path
from types import SimpleNamespace

from alice.voice.piper_runtime_install import install_piper_runtime


class FakeRunner:
    def __init__(self, *, fail_at=None, help_text="usage: piper --model FILE --output_file FILE"):
        self.calls = []
        self.fail_at = fail_at
        self.help_text = help_text
    def __call__(self, command, **kwargs):
        self.calls.append((list(command), kwargs))
        assert kwargs.get("shell") is False
        assert kwargs.get("timeout", 0) > 0
        root = None
        if "-m" in command and "venv" in command:
            root = Path(command[-1])
            (root / "Scripts").mkdir(parents=True, exist_ok=True)
            (root / "Scripts" / "python.exe").write_bytes(b"fake python")
        elif "pip" in command and "install" in command:
            vpy = Path(command[0])
            (vpy.parent / "piper.exe").write_bytes(b"fake piper")
        index = len(self.calls)
        if self.fail_at == index:
            return SimpleNamespace(returncode=1, stdout="", stderr="controlled failure")
        if command[-1] == "--help":
            return SimpleNamespace(returncode=0, stdout=self.help_text, stderr="")
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")


def test_install_requires_explicit_consent_and_runs_no_commands(tmp_path):
    python = tmp_path / "python.exe"
    python.write_bytes(b"python")
    runner = FakeRunner()
    result = install_piper_runtime(tmp_path, consent=False, python_executable=python,
                                   platform_name="Windows", runner=runner)
    assert not result.ok and result.reason == "explicit_install_consent_required"
    assert runner.calls == []


def test_install_is_windows_only(tmp_path):
    python = tmp_path / "python"
    python.write_bytes(b"python")
    result = install_piper_runtime(tmp_path, consent=True, python_executable=python,
                                   platform_name="Linux", runner=FakeRunner())
    assert not result.ok and result.reason == "windows_runtime_required"


def test_install_uses_dedicated_venv_and_binary_wheels_only(tmp_path):
    python = tmp_path / "python.exe"
    python.write_bytes(b"python")
    runner = FakeRunner()
    result = install_piper_runtime(tmp_path, consent=True, python_executable=python,
                                   platform_name="Windows", runner=runner)
    assert result.ok and result.reason == "piper_runtime_installed_and_cli_checked"
    assert Path(result.executable).name.lower() == "piper.exe"
    assert "voice_runtime" in result.executable and "piper_tts_venv" in result.executable
    install_command = runner.calls[1][0]
    assert "--only-binary=:all:" in install_command
    assert install_command[-1] == "piper-tts"
    assert all(call[1]["shell"] is False for call in runner.calls)


def test_install_rejects_incompatible_cli(tmp_path):
    python = tmp_path / "python.exe"
    python.write_bytes(b"python")
    result = install_piper_runtime(tmp_path, consent=True, python_executable=python,
                                   platform_name="Windows", runner=FakeRunner(help_text="usage: other-command"))
    assert not result.ok and result.reason == "piper_cli_arguments_incompatible"


def test_install_reports_pip_failure(tmp_path):
    python = tmp_path / "python.exe"
    python.write_bytes(b"python")
    result = install_piper_runtime(tmp_path, consent=True, python_executable=python,
                                   platform_name="Windows", runner=FakeRunner(fail_at=2))
    assert not result.ok and result.reason == "pip_install_failed_binary_wheels_only"


def test_incomplete_existing_runtime_is_not_deleted_or_overwritten(tmp_path):
    python = tmp_path / "python.exe"
    python.write_bytes(b"python")
    runtime = tmp_path / "alice_workspace" / "voice_runtime" / "piper_tts_venv"
    runtime.mkdir(parents=True)
    marker = runtime / "keep.txt"
    marker.write_text("preserve", encoding="utf-8")
    result = install_piper_runtime(tmp_path, consent=True, python_executable=python,
                                   platform_name="Windows", runner=FakeRunner())
    assert not result.ok and result.reason == "existing_runtime_incomplete_manual_repair_required"
    assert marker.read_text(encoding="utf-8") == "preserve"


def test_install_rejects_missing_python(tmp_path):
    result = install_piper_runtime(tmp_path, consent=True, python_executable=tmp_path / "missing.exe",
                                   platform_name="Windows", runner=FakeRunner())
    assert not result.ok and result.reason == "python_executable_not_found"
