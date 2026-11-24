from pathlib import Path


def _html():
    return (Path(__file__).resolve().parents[1] / "ui" / "assets" / "alice-premium-ui.html").read_text(encoding="utf-8")


def test_conversation_drawer_remembers_focus_origin_only_when_opening():
    html = _html()
    assert "let attachment=null,drawerReturnFocus=null" in html
    assert "if(!drawer.classList.contains('open'))" in html
    assert "drawerReturnFocus=active&&active!==document.body?active:null" in html


def test_conversation_drawer_restores_focus_to_connected_enabled_origin():
    html = _html()
    assert "const returnTarget=drawerReturnFocus;drawerReturnFocus=null" in html
    assert "returnTarget&&returnTarget.isConnected&&!returnTarget.disabled" in html
    assert "returnTarget.focus()" in html


def test_existing_drawer_accessibility_and_escape_close_are_preserved():
    html = _html()
    assert "drawer.setAttribute('aria-hidden','false')" in html
    assert "drawer.setAttribute('aria-hidden','true')" in html
    assert "e.key==='Escape'&&drawer.classList.contains('open')" in html
    assert "$('#closeDrawer').addEventListener('click',closeDrawer)" in html
