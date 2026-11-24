from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HTML = ROOT / "alice" / "ui" / "assets" / "alice-premium-ui.html"


def test_canvas_stops_scheduling_frames_when_reduced_motion_is_enabled():
    text = HTML.read_text(encoding="utf-8")
    assert "function draw(now){if(reducedMotion||document.hidden)return;frame++;" in text
    assert "if(!reducedMotion){requestAnimationFrame(draw);" in text


def test_canvas_pauses_in_background_and_resumes_on_visibility():
    text = HTML.read_text(encoding="utf-8")
    assert "document.addEventListener('visibilitychange'" in text
    assert "if(!document.hidden)requestAnimationFrame(draw)" in text
    assert "setTimeout(()=>requestAnimationFrame(draw),500)" not in text


def test_canvas_uses_a_lower_pixel_ratio_budget():
    text = HTML.read_text(encoding="utf-8")
    assert "window.matchMedia('(max-width: 720px)').matches?1.35:1.75" in text
    assert "devicePixelRatio||1" in text


def test_existing_canvas_and_interaction_are_preserved():
    text = HTML.read_text(encoding="utf-8")
    assert 'id="coreCanvas"' in text
    assert "canvas.addEventListener('pointermove'" in text
    assert "const count=210" in text
    assert "for(const [i,j] of edges)" in text
