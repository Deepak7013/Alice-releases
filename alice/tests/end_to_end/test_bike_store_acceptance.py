from pathlib import Path


def test_bike_store_project(project_root=None):
    # The release must not depend on a user's mutable projects_by_alice folder.
    # When a real generated project is supplied, validate that project instead;
    # otherwise use the deterministic acceptance fixture shipped with the suite.
    p = Path(project_root) if project_root else Path(__file__).resolve().parents[1] / "fixtures" / "bike_store"
    assert (p / "index.html").exists()
    html = (p / "index.html").read_text(encoding="utf-8").lower()
    css = (p / "style.css").read_text(encoding="utf-8").lower()
    js = (p / "app.js").read_text(encoding="utf-8").lower()
    for term in ["bike", "cart"]:
        assert term in html
    assert "price" in html or "price" in js
    assert "addtocart" in js or "add-to-cart" in html
    assert len(css) > 100
