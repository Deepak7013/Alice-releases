from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "alice/ui/assets/alice-premium-ui.html").read_text(encoding="utf-8")
CSS = (ROOT / "alice/ui/assets/alice-approved-ui.css").read_text(encoding="utf-8")

def test_existing_panel_controls_support_minimize_pin_size_dock_and_close():
    assert "function mountOrbitPanelControls()" in HTML
    assert "applyMinimized" in HTML
    assert "Keep this panel open while switching features" in HTML
    assert "Feature panel size" in HTML
    assert "Dock feature panel beside the orb" in HTML
    assert "Close feature panel" in HTML

def test_existing_panel_drag_and_keyboard_controls_are_preserved():
    assert "dataset.orbitDragHandle" in HTML
    assert "Alt plus arrow keys" in HTML
    assert "setOrbitPanelFloating" in HTML
    assert "saveOrbitPanelLayout" in HTML

def test_phase8_styles_holographic_panel_toolbar_and_controls():
    assert "PHASE 8 — holographic feature-panel controls" in CSS
    assert ".orbit-panel-toolbar" in CSS
    assert ".orbit-panel-control" in CSS
    assert ".is-orbit-floating" in CSS
    assert ".is-orbit-minimized" in CSS
    assert ".is-orbit-pinned" in CSS

def test_panel_controls_remain_responsive_and_keyboard_accessible():
    assert ".orbit-panel-toolbar:focus-visible" in CSS
    assert ".orbit-panel-size:focus-visible" in CSS
    assert "@media(max-width:760px)" in CSS
    assert "@media(prefers-reduced-motion:reduce)" in CSS
