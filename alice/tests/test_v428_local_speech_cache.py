import pytest
from alice.voice.cache_store import LocalSpeechCache

def key(ch): return ch * 64

def test_cache_stores_immutable_bytes_and_reads_them():
    c=LocalSpeechCache(max_entries=2,max_bytes=10)
    assert c.put(key("a"), bytearray(b"abc"))
    assert c.get(key("a")) == b"abc"
    assert c.stats().bytes_used == 3

def test_cache_evicts_least_recently_used_entry():
    c=LocalSpeechCache(max_entries=2,max_bytes=20)
    c.put(key("a"),b"a"); c.put(key("b"),b"b")
    assert c.get(key("a")) == b"a"
    c.put(key("c"),b"c")
    assert c.get(key("a")) == b"a" and c.get(key("b")) is None and c.get(key("c")) == b"c"

def test_cache_obeys_byte_bound_and_rejects_oversized_payload():
    c=LocalSpeechCache(max_entries=5,max_bytes=4)
    assert not c.put(key("a"),b"12345")
    c.put(key("a"),b"12"); c.put(key("b"),b"34")
    c.put(key("c"),b"56")
    assert c.stats().bytes_used <= 4 and c.stats().entries == 2
    assert c.get(key("a")) is None

def test_cache_rejects_invalid_keys_and_payload_types():
    c=LocalSpeechCache()
    assert not c.put("not-a-hash",b"x")
    assert not c.put(key("a"),"not bytes")
    assert c.get("not-a-hash") is None

def test_cache_clear_and_invalid_limits():
    c=LocalSpeechCache(); c.put(key("a"),b"x"); c.clear()
    assert c.stats().entries == 0 and c.stats().bytes_used == 0
    with pytest.raises(ValueError): LocalSpeechCache(max_entries=0)
    with pytest.raises(ValueError): LocalSpeechCache(max_bytes=0)
