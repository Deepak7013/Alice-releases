from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_upgrade_runner_loads_package_updater_explicitly():
    text = (ROOT / "upgrade_runner.py").read_text(encoding="utf-8")
    assert "package / \"alice\" / \"deployment\" / \"updater.py\"" in text
    assert "sys.path.insert(0, str(root))" not in text


def test_full_installer_uses_cache_independent_pytest():
    text = (ROOT / "INSTALL_ALICE.ps1").read_text(encoding="utf-8")
    assert "-p no:cacheprovider" in text
    assert "--cache-clear" not in text


def test_version_is_full_build():
    assert (ROOT / "VERSION.txt").read_text(encoding="utf-8").strip() .startswith("ALICE v")
