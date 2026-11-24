from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = (ROOT / "alice/ui/assets/alice-premium-ui.html").read_text(encoding="utf-8")

def test_initial_workspace_navigation_exposes_current_page():
    assert 'data-view="Overview" aria-current="page"' in HTML

def test_view_switch_updates_accessible_current_page_state():
    token = "$$('.nav-btn').forEach(b=>{const selected=b===btn;"
    assert token in HTML
    assert "if(selected)b.setAttribute('aria-current','page')" in HTML
    assert "else b.removeAttribute('aria-current')" in HTML

def test_existing_active_visual_state_is_preserved():
    assert "b.classList.toggle('active',selected)" in HTML
    assert "$$('.nav-btn').forEach" in HTML
