from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
CSS = (ROOT / "alice/ui/assets/alice-approved-ui.css").read_text(encoding="utf-8")
HTML = (ROOT / "alice/ui/assets/alice-premium-ui.html").read_text(encoding="utf-8")

def test_phase5_chamber_composition_has_depth_layers():
    assert "PHASE 5 — main orbital chamber composition" in CSS
    assert "repeating-linear-gradient(0deg" in CSS
    assert "radial-gradient(ellipse at 51% 42%" in CSS
    assert "var(--alice-chamber-edge)" in CSS

def test_phase5_keeps_workspace_and_immersive_layout_distinct():
    assert 'body[data-theme="immersive"] .core-card:before' in CSS
    assert 'body[data-theme="immersive"] .rail{display:none}' in CSS
    assert 'body[data-theme="immersive"] .sidebar,body[data-theme="immersive"] .rail{display:none}' in HTML or 'data-theme="immersive"' in HTML

def test_phase5_glass_panels_use_teal_palette():
    assert "rgba(8,27,27,.82)" in CSS
    assert "rgba(88,226,188,.2)" in CSS
    assert ".panel,.crystal-panel" in CSS

def test_phase5_responsive_and_reduced_motion_rules_exist():
    assert "@media (max-width:1100px)" in CSS
    assert "@media (max-width:760px)" in CSS
    assert "@media (prefers-reduced-motion:reduce)" in CSS
