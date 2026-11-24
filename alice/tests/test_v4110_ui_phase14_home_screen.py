from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSS = ROOT / "alice" / "ui" / "assets" / "alice-approved-ui.css"
HTML = ROOT / "alice" / "ui" / "assets" / "alice-premium-ui.html"


def test_phase14_cinematic_home_screen_layer_is_present():
    text = CSS.read_text(encoding="utf-8")
    assert "PHASE 14 — Reference-led cinematic Home screen composition" in text
    assert "opacity:.94!important" in text
    assert "hue-rotate(34deg) saturate(1.72)" in text


def test_existing_live_canvas_is_preserved():
    text = HTML.read_text(encoding="utf-8")
    assert 'id="coreCanvas"' in text
    assert "requestAnimationFrame(draw)" in text
    assert "getContext('2d',{alpha:true})" in text


def test_system_health_and_notes_are_real_existing_panels():
    text = HTML.read_text(encoding="utf-8")
    assert 'id="systemHealthPanel"' in text
    assert 'id="notesRailPanel"' in text
    assert 'id="healthBattery"' in text
    assert 'id="healthStorage"' in text


def test_existing_voice_and_composer_routes_are_preserved():
    text = HTML.read_text(encoding="utf-8")
    assert 'id="voiceBtn"' in text
    assert 'id="composerForm"' in text
    assert 'id="promptInput"' in text
    assert 'id="voiceConsoleMic"' in text or 'id="voiceBtn"' in text


def test_mobile_and_reduced_motion_rules_exist():
    text = CSS.read_text(encoding="utf-8")
    assert "@media(max-width:720px)" in text
    assert "@media(prefers-reduced-motion:reduce)" in text


def test_workspace_and_immersive_modes_remain_available():
    text = CSS.read_text(encoding="utf-8")
    assert 'body[data-theme="immersive"]' in text
    assert 'body[data-theme="workspace"]' in text
