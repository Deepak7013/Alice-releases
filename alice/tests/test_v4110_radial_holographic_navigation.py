from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "alice/ui/assets/alice-premium-ui.html").read_text(encoding="utf-8")
CSS = (ROOT / "alice/ui/assets/alice-approved-ui.css").read_text(encoding="utf-8")

def test_existing_orbital_feature_catalog_is_preserved():
    assert "const orbitFeatures=[" in HTML
    assert "label:'Conversation'" in HTML
    assert "label:'Brain Center'" in HTML
    assert "label:'Notifications and activity'" in HTML
    assert "node.dataset.orbitView=feature.view" in HTML

def test_radial_navigation_keeps_accessible_labels_and_keyboard_focus():
    assert 'aria-label="Orbital feature navigation"' in HTML
    assert "node.setAttribute('aria-label',feature.label)" in HTML
    assert ".orbital-node:focus-visible,.orbit-nav-toggle:focus-visible" in CSS

def test_holographic_orbit_track_and_glass_nodes_are_styled():
    assert "PHASE 7 — radial feature navigation" in CSS
    assert ".orbital-nav.is-open:before" in CSS
    assert "backdrop-filter:blur(14px) saturate(130%)" in CSS
    assert ".orbital-nav.is-open .orbital-node.is-selected" in CSS

def test_nodes_have_hover_labels_responsive_and_reduced_motion_support():
    assert "content:attr(title)" in CSS
    assert "@media(max-width:760px)" in CSS
    assert "@media(prefers-reduced-motion:reduce)" in CSS
