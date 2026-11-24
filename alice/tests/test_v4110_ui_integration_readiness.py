from pathlib import Path
import re

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "alice/ui/assets/alice-premium-ui.html").read_text(encoding="utf-8")
APPROVED = (ROOT / "alice/ui/assets/alice-approved-ui.css").read_text(encoding="utf-8")
NATIVE = (ROOT / "alice/ui/assets/alice-native-orbital-ui.css").read_text(encoding="utf-8")

def test_approved_stylesheets_load_in_intended_order():
    a = HTML.index('href="alice-approved-ui.css"')
    n = HTML.index('href="alice-native-orbital-ui.css"')
    assert a < n

def test_voice_console_keeps_existing_composer_route():
    assert 'id="voiceConsoleMic"' in HTML
    assert 'id="voiceConsoleInput"' in HTML
    assert 'id="composerForm"' in HTML
    assert 'id="promptInput"' in HTML
    assert "voiceConsoleMic" in HTML and "voiceConsoleInput" in HTML
    assert "composerForm" in HTML and "promptInput" in HTML

def test_workspace_and_immersive_theme_hooks_are_present():
    assert "workspace" in HTML.lower()
    assert "immersive" in HTML.lower()
    assert "localStorage" in HTML
    assert "theme" in APPROVED.lower() and "theme" in NATIVE.lower()

def test_orbital_navigation_and_panel_controls_remain_wired():
    for token in ("orbital-node", "is-selected", "orbit-origin-x", "orbit-origin-y"):
        assert token in HTML or token in APPROVED or token in NATIVE
    for token in ("panelMinimize", "panelClose", "orbitDragHandle"):
        assert token in HTML or token in APPROVED or token in NATIVE

def test_responsive_and_reduced_motion_guards_exist():
    for css in (APPROVED, NATIVE):
        assert "@media" in css
        assert "prefers-reduced-motion" in css
        assert "focus-visible" in css

def test_key_voice_and_theme_selectors_are_unique_in_static_markup():
    ids = re.findall(r'\bid="([^"]+)"', HTML)
    # Brain Center IDs are intentionally assigned to a dynamically rendered view;
    # activityEmpty is dynamically recreated after the initial placeholder is removed.
    ignored_dynamic = {"brainStatus", "brainDetails", "activityEmpty"}
    counts = {}
    for item in ids:
        if item not in ignored_dynamic:
            counts[item] = counts.get(item, 0) + 1
    assert all(count == 1 for count in counts.values())
