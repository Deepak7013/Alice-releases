from alice.learning.provenance import LearningProvenance

def test_provenance_is_recorded_and_deduplicable(tmp_path):
    p=LearningProvenance(tmp_path); r=p.record('ALICE learns locally','instruction')
    assert r.fingerprint and p.seen(r.fingerprint)

def test_provenance_keeps_source_and_confidence(tmp_path):
    r=LearningProvenance(tmp_path).record('use local memory','instruction',confidence=.88)
    assert r.source=='user_chat' and r.confidence==.88
