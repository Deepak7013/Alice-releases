from pathlib import Path
from alice.artifacts.factory import ArtifactFactory
from alice.artifacts.reference_design import classify_slide, style_metadata
from alice.artifacts.visual_qa import VisualArtifactQA

def test_reference_layout_classification():
    assert classify_slide({"title":"Intro","body":"hello"},0,3)=="title"
    assert classify_slide({"title":"KPIs","body":"Revenue grew 20%"},1,3)=="metrics"
    assert classify_slide({"title":"Compare","left":"A","right":"B"},1,3)=="two_column"

def test_reference_metadata():
    m=style_metadata()
    assert m["reference"].startswith("Microsoft Office")
    assert m["proprietary_assets"] is False

def test_reference_powerpoint(tmp_path):
    f=ArtifactFactory(tmp_path)
    r=f.create_reference_powerpoint("Demo",[
        {"title":"Overview","body":"A clear opening"},
        {"title":"Metrics","metrics":[{"value":"42","label":"Users"},{"value":"18%","label":"Growth"}]},
        {"title":"Comparison","left":"Before","right":"After"},
        {"title":"Conclusion","body":"Next steps"},
    ])
    assert Path(r.path).exists()
    q=VisualArtifactQA().inspect(r.path,"powerpoint")
    assert q["ok"], q
