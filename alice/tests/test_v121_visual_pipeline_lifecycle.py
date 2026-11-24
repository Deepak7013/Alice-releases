from alice.artifacts.factory import ArtifactFactory
from alice.artifacts.visual_pipeline import VisualArtifactPipeline

def test_pipeline_analyzes_before_render_tempdir_disappears(tmp_path):
    f=ArtifactFactory(tmp_path)
    p=f.create_pdf("pipeline test",[{"heading":"Test","body":"Visible content"}])
    r=VisualArtifactPipeline().inspect(p.path,"pdf")
    assert r["ok"] and r["quality_score"]>0
