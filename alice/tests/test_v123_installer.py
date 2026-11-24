from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_installer_is_staged_and_uses_powershell():
    text = (ROOT / "INSTALL_ALICE.bat").read_text(encoding="utf-8")
    assert "INSTALL_ALICE.ps1" in text
    assert "powershell.exe -NoProfile -ExecutionPolicy Bypass" in text


def test_powershell_installer_uses_staging_and_cache_free_tests():
    text = (ROOT / "INSTALL_ALICE.ps1").read_text(encoding="utf-8")
    assert ".installing" in text
    assert "Move-Item $Stage $Root" in text
    assert "-p no:cacheprovider" in text
    assert "Robocopy exit code $rc" in text


def test_upgrade_launcher_knows_current_and_legacy_roots():
    text = (ROOT / "UPGRADE_ALICE.bat").read_text(encoding="utf-8")
    assert "C:\\Alice_v3.12.4" in text
    assert "C:\\Alice_v3.12.3" in text
    assert "C:\\Alice_v3.7.3" in text
    assert "C:\\Alice_v3.10" in text


def test_version():
    assert (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip() .startswith("ALICE v")
