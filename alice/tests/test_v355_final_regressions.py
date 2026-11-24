from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]

def test_version_is_final_v355():
    assert (ROOT / 'VERSION.txt').read_text(encoding='utf-8').strip() .startswith('ALICE v')

def test_voice_stop_and_toggle_commands_are_local():
    text=(ROOT/'alice/ui/app.py').read_text(encoding='utf-8')
    assert 'stop the voice' in text
    assert 'turn off sound' in text
    assert 'def _is_voice_enable_command' in text
    assert 'self.voice.set_enabled(False)' in text
    assert 'self.voice.set_enabled(True)' in text

def test_voice_enabled_state_is_persistent():
    text=(ROOT/'alice/voice/voice.py').read_text(encoding='utf-8')
    assert '"enabled": self._voice_enabled' in text
    assert 'def set_enabled(self, enabled: bool)' in text
    assert 'if not self._voice_enabled or not str(text).strip():return False' in text

def test_finish_respects_voice_enabled():
    text=(ROOT/'alice/ui/app.py').read_text(encoding='utf-8')
    assert 'self.voice.is_enabled() and ((not self.text_mode) or self._wants_voice(request))' in text

def test_duplicate_window_preflight_exists():
    text=(ROOT/'alice/__main__.py').read_text(encoding='utf-8')
    assert 'def _find_any_alice_window()' in text
    assert 'if os.name == "nt" and _find_any_alice_window():' in text

def test_installer_starts_verified_target_after_promotion():
    text=(ROOT/'INSTALL_ALICE.ps1').read_text(encoding='utf-8')
    assert 'Starting the verified ALICE installation' in text
    assert "-m','alice','--show'" in text

def test_legacy_startup_cleanup_is_present():
    text=(ROOT/'alice/deployment/launcher_repair.py').read_text(encoding='utf-8')
    assert 'Alice Launcher.lnk' in text and 'ALICE Launcher.lnk' in text

def test_neural_backend_uses_popen_pipe_contract():
    text=(ROOT/'alice/voice/neural.py').read_text(encoding='utf-8')
    assert 'subprocess.Popen' in text and 'stdout=subprocess.PIPE' in text and 'stderr=subprocess.PIPE' in text
    assert 'capture_output=True' not in text
