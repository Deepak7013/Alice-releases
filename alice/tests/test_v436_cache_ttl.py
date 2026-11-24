import pytest
from alice.voice.cache_store import LocalSpeechCache

class Clock:
    def __init__(self): self.now=10.0
    def __call__(self): return self.now

def test_ttl_expiration_removes_payload_and_bytes():
    clock=Clock(); c=LocalSpeechCache(ttl_seconds=5,clock=clock)
    assert c.put("a"*64,b"audio") and c.get("a"*64)==b"audio"
    clock.now=15.0
    assert c.get("a"*64) is None
    assert c.stats().entries==0 and c.stats().bytes_used==0

def test_purge_expired_returns_count_and_keeps_live_entries():
    clock=Clock(); c=LocalSpeechCache(ttl_seconds=5,clock=clock)
    c.put("a"*64,b"a"); clock.now=12; c.put("b"*64,b"b")
    clock.now=15
    assert c.purge_expired()==1
    assert c.get("b"*64)==b"b"

def test_ttl_must_be_positive_and_non_boolean():
    with pytest.raises(ValueError): LocalSpeechCache(ttl_seconds=0)
    with pytest.raises(ValueError): LocalSpeechCache(ttl_seconds=True)

def test_non_ttl_cache_retains_existing_behavior():
    c=LocalSpeechCache(); c.put("a"*64,b"a")
    assert c.get("a"*64)==b"a" and c.audit().consistent
