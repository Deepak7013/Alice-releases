from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_installer_uses_isolated_pytest_temp_and_sanitized_verification_env():
    text = (ROOT / "INSTALL_ALICE.ps1").read_text(encoding="utf-8")
    assert "--basetemp" in text
    assert "PYTHON_DOTENV_DISABLED" in text
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" in text
    assert "Remove-Item Env:PYTHONPATH" in text
    assert "-p no:cacheprovider" in text


def test_updater_verification_uses_isolated_temp_and_sanitized_environment():
    text = (ROOT / "alice/deployment/updater.py").read_text(encoding="utf-8")
    assert "--basetemp" in text
    assert "PYTHON_DOTENV_DISABLED" in text
    assert "PYTEST_DISABLE_PLUGIN_AUTOLOAD" in text
    assert "PYTHONPATH" in text


def test_router_hardening_test_is_not_dependent_on_user_model_settings():
    text = (ROOT / "alice/tests/test_v137_final_hardening.py").read_text(encoding="utf-8")
    assert '"OPENAI_MODEL"' in text
    assert '"ALICE_PROVIDER"' in text
    assert '"ALICE_PRIMARY_PROVIDER"' in text


def test_updater_fixture_does_not_require_windows_symlink_privilege():
    text = (ROOT / "alice/tests/test_v310_inplace_updater.py").read_text(encoding="utf-8")
    assert "symlink_to(Path(sys.executable))" not in text
    assert 'python.exe").write_bytes' in text
