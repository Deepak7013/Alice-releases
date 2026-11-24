from alice.voice.cache_store import LocalSpeechCache
def test_cache_audit_reports_healthy_state():
    c=LocalSpeechCache(max_entries=2,max_bytes=8);c.put("a"*64,b"123");c.put("b"*64,b"45")
    report=c.audit()
    assert report.consistent and report.reason=="cache_integrity_ok"
    assert report.entries==2 and report.bytes_used==5 and report.bounds_ok and report.keys_valid and report.payloads_valid
def test_cache_audit_detects_counter_drift_without_mutating_cache():
    c=LocalSpeechCache();c.put("a"*64,b"audio");c._bytes=1
    report=c.audit()
    assert not report.consistent and report.reason=="cache_integrity_failed"
    assert report.bytes_used==5 and c._bytes==1
def test_cache_audit_detects_bound_or_key_corruption():
    c=LocalSpeechCache(max_entries=1,max_bytes=8);c._items["bad-key"]=b"x";c._bytes=1
    report=c.audit()
    assert not report.consistent and not report.keys_valid
