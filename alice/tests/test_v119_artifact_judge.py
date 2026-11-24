from reportlab.pdfgen import canvas
from alice.artifacts.judge import ArtifactJudge

def make(path,text="Alice"):
    c=canvas.Canvas(str(path)); c.drawString(72,720,text); c.showPage(); c.save()

def test_fallback_judgment_is_explicit(tmp_path):
    p=tmp_path/"x.pdf"; make(p)
    j=ArtifactJudge().judge_pdf(p)
    assert j.source=="deterministic_visual_heuristics" and j.expert_score is None

def test_expert_judgment_is_combined(tmp_path):
    p=tmp_path/"x.pdf"; make(p)
    j=ArtifactJudge(lambda x: {"score":1.0,"confidence":.9,"reasons":["clear"]}).judge_pdf(p)
    assert j.source=="visual_plus_expert" and j.expert_score==1.0 and j.score>=j.visual_score

def test_failed_expert_falls_back(tmp_path):
    p=tmp_path/"x.pdf"; make(p)
    def bad(_): raise RuntimeError("boom")
    j=ArtifactJudge(bad).judge_pdf(p)
    assert j.source=="visual_fallback" and "expert_failed" in j.reasons
