from alice.voice.cache_store import LocalSpeechCache

def test_cache_metrics_count_hits_misses_and_evictions():
    c=LocalSpeechCache(max_entries=1,max_bytes=10)
    assert c.get("a"*64) is None
    assert c.put("a"*64,b"a")
    assert c.get("a"*64)==b"a"
    assert c.put("b"*64,b"b")
    s=c.stats()
    assert (s.hits,s.misses,s.evictions)==(1,1,1)
    assert s.entries==1 and s.bytes_used==1

def test_replacing_same_key_is_not_an_eviction():
    c=LocalSpeechCache(); c.put("a"*64,b"a"); c.put("a"*64,b"bb")
    s=c.stats()
    assert s.evictions==0 and s.bytes_used==2

def test_clear_preserves_lifetime_metrics():
    c=LocalSpeechCache(); c.get("a"*64); c.clear()
    assert c.stats().misses==1 and c.stats().entries==0
