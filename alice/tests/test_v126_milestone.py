from alice.experience.global_store import GlobalExperienceStore
from alice.intelligence.brain import IntelligenceBrain
from alice.intelligence.efficiency import EfficiencyPolicy

def test_brain_prefers_direct_experience(tmp_path):
    s=GlobalExperienceStore(tmp_path); s.record("create college powerpoint presentation","use academic slides",True,evidence={"verified":True,"quality":.9})
    x=IntelligenceBrain(s,"tfidf").solve_strategy("make a university presentation")
    assert x["strategy"]=="reuse_direct_experience" and x["efficiency"]=="reuse_cached_experience"

def test_brain_falls_back_to_algorithm_choice(tmp_path):
    s=GlobalExperienceStore(tmp_path); x=IntelligenceBrain(s,"tfidf").solve_strategy("detect anomalies in numeric data",objective="anomaly detection",data={"outliers":True})
    assert x["strategy"]=="select_algorithm" and x["algorithms"]

def test_high_confidence_reuse_is_fastest():
    d=EfficiencyPolicy().choose(direct_confidence=.9,deterministic_available=True)
    assert d.path=="reuse_cached_experience" and d.estimated_cost=="low"

def test_visual_provider_escalation_only_when_needed():
    d=EfficiencyPolicy().choose(deterministic_available=True,visual_required=True,provider_available=True,complexity="high")
    assert d.path=="use_multimodal_review"

def test_optimism_never_claims_success_when_blocked():
    assert EfficiencyPolicy.optimistic_status(False,blocked_reason="missing tool")=="blocked_with_next_step"

def test_visual_render_result_survives_temp_cleanup(tmp_path):
    from alice.artifacts.factory import ArtifactFactory
    from alice.artifacts.visual_pipeline import VisualArtifactPipeline
    from pathlib import Path
    p=ArtifactFactory(tmp_path).create_pdf("durable",[{"heading":"Visible","body":"Content"}]).path
    r=VisualArtifactPipeline(output_root=tmp_path/"renders").inspect(p,"pdf")
    assert r["ok"] and r["quality_score"]>0 and Path(r["rendered"]["rendered_pdf"]).exists()
