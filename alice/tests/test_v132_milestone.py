import json
from pathlib import Path
from alice.intelligence.visual_expert import MultimodalArtifactExpert
from alice.artifacts.judge import ArtifactJudge
class FakeRouter:
    def ask(self,prompt,image_path=None,allow_fallback=True):
        assert image_path and Path(image_path).exists()
        return json.dumps({"score":.9,"confidence":.95,"reasons":["strong hierarchy","balanced spacing"]})

def test_multimodal_expert_parses_provider(tmp_path):
    import fitz
    pdf=tmp_path/"x.pdf"; d=fitz.open(); d.new_page().insert_text((50,50),"Alice report"); d.save(pdf); d.close()
    r=MultimodalArtifactExpert(FakeRouter()).judge_pdf(pdf,{"kind":"report"})
    assert r["source"]=="multimodal_provider" and r["score"]==.9

def test_artifact_judge_uses_provider_expert(tmp_path):
    import fitz
    pdf=tmp_path/"x.pdf"; d=fitz.open(); d.new_page().insert_text((50,50),"Alice report"); d.save(pdf); d.close()
    r=ArtifactJudge(provider_expert=MultimodalArtifactExpert(FakeRouter())).judge_pdf(pdf)
    assert r.source=="visual_plus_multimodal_provider" and r.expert_score==.9
