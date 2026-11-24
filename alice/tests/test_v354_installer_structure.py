from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_installer_uses_explicit_source_target_structure():
    bat = (ROOT / 'INSTALL_ALICE.bat').read_text(encoding='utf-8')
    ps = (ROOT / 'INSTALL_ALICE.ps1').read_text(encoding='utf-8')
    assert 'C:\\ALICE_INSTALLER_v%VERSION%' in bat
    assert 'set "TARGET=C:\\Alice_v%VERSION%"' in bat
    assert "Installer source folder must use the format C:\\ALICE_INSTALLER_vX.Y.Z" in ps
    assert "$Root = 'C:\\Alice_v' + $Matches[1]" in ps


def test_launcher_repair_does_not_embed_trailing_backslash_inside_python_raw_string():
    bat = (ROOT / 'REPAIR_ALICE_STARTUP.bat').read_text(encoding='utf-8')
    assert "repair_windows_launchers(os.environ['ALICE_REPAIR_ROOT'])" in bat
    assert "repair_windows_launchers(r'%ROOT%')" not in bat


def test_installer_repairs_launcher_without_interactive_pause():
    ps = (ROOT / 'INSTALL_ALICE.ps1').read_text(encoding='utf-8')
    assert 'REPAIR_ALICE_STARTUP.bat" /nopause' in ps


def test_installer_migrates_latest_known_alice_roots():
    ps = (ROOT / 'INSTALL_ALICE.ps1').read_text(encoding='utf-8')
    for version in ('3.35.3', '3.34.3', '3.34.0', '3.33.0', '3.32.1'):
        assert f'C:\\Alice_v{version}' in ps


def test_ui_title_is_version_dynamic():
    text = (ROOT / 'alice/ui/app.py').read_text(encoding='utf-8')
    assert 'self.root.title(f"Alice — {self._generation_name()} {self._app_version()}")' in text
    assert 'GLUTTONY AI  •  {self._app_version()}' in text


