
from alice.artifacts.quality_memory import QualityMemory

def test_quality_memory_prefers_higher_quality(tmp_path):
    m=QualityMemory(tmp_path)
    m.record("college ppt","powerpoint","plain",.75,True)
    m.record("college ppt","powerpoint","alice_clean",1.0,True)
    assert m.best("college ppt","powerpoint")["recipe"]=="alice_clean"

def test_quality_memory_persists(tmp_path):
    m=QualityMemory(tmp_path); m.record("report","word","academic",.9,True)
    m2=QualityMemory(tmp_path)
    assert m2.best("report","word")["mean_score"]==.9
