from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "alice/ui/assets/alice-premium-ui.html").read_text(encoding="utf-8")
CSS = (ROOT / "alice/ui/assets/alice-approved-ui.css").read_text(encoding="utf-8")

def test_command_console_has_real_mic_and_hidden_text_input():
    assert 'id="voiceConsoleMic"' in HTML
    assert 'id="voiceConsoleInput"' in HTML
    assert 'type="text"' in HTML
    assert 'tabindex="-1"' in HTML

def test_double_tap_reveals_text_and_single_tap_reuses_existing_voice_path():
    assert "openConsoleText()" in HTML
    assert "ev.detail>1" in HTML
    assert "voiceButton.click()" in HTML
    assert "voiceConsoleInput.addEventListener('keydown'" in HTML

def test_text_submission_reuses_existing_composer():
    assert "$('#promptInput')" in HTML
    assert "$('#composerForm').requestSubmit()" in HTML

def test_command_console_has_responsive_teal_glass_styling():
    assert "PHASE 6 — bottom command console" in CSS
    assert ".voice-console.text-open .voice-console-input" in CSS
    assert "@media(max-width:600px)" in CSS
    assert "@media(prefers-reduced-motion:reduce)" in CSS
