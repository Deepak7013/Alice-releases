
from pathlib import Path
from alice.artifacts.quality import ArtifactQualityScorer

def test_quality_score_for_existing_file(tmp_path):
    p=tmp_path/"x.txt"; p.write_text("hello")
    q=ArtifactQualityScorer().score(p,"text")
    assert q["score"]==1.0 and q["human_aesthetic_review"] is False

def test_missing_file_fails(tmp_path):
    q=ArtifactQualityScorer().score(Path(tmp_path)/"nope","text")
    assert q["score"]<.75
