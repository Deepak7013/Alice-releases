from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "alice/ui/assets/alice-premium-ui.html").read_text(encoding="utf-8")
CSS = (ROOT / "alice/ui/assets/alice-approved-ui.css").read_text(encoding="utf-8")

def test_theme_switch_is_existing_persistent_user_control():
    assert 'id="themeSwitch"' in HTML
    assert "localStorage.getItem('alice.ui.theme')" in HTML
    assert "localStorage.setItem('alice.ui.theme'" in HTML
    assert "Switch to Immersive theme" in HTML
    assert "Switch to Workspace theme" in HTML

def test_workspace_theme_retains_sidebar_and_right_rail_composition():
    assert 'body[data-theme="workspace"] .shell' in CSS
    assert 'body[data-theme="workspace"] .sidebar' in CSS
    assert 'body[data-theme="workspace"] .rail .panel' in CSS

def test_immersive_theme_expands_neural_chamber_and_hides_sidebars():
    assert 'body[data-theme="immersive"] .shell' in CSS
    assert 'body[data-theme="immersive"] .core-card' in CSS
    assert 'body[data-theme="immersive"] .sidebar,body[data-theme="immersive"] .rail{display:none}' in HTML

def test_theme_switch_keyboard_and_mobile_support():
    assert "#themeSwitch:focus-visible" in CSS
    assert "@media(max-width:720px)" in CSS
    assert "@media(prefers-reduced-motion:reduce)" in CSS
