from concurrent.futures import ThreadPoolExecutor
from alice.voice.cache_store import LocalSpeechCache
def test_concurrent_cache_access_preserves_bounds_and_consistency():
    cache=LocalSpeechCache(max_entries=16,max_bytes=128)
    def worker(i):
        key=f"{i:064x}"; cache.put(key,bytes([i%255+1])*8); return cache.get(key)
    with ThreadPoolExecutor(max_workers=8) as pool: list(pool.map(worker,range(200)))
    stats=cache.stats()
    assert 0<=stats.entries<=16 and 0<=stats.bytes_used<=128
    assert stats.bytes_used==sum(len(v) for v in cache._items.values())
def test_clear_is_safe_and_stats_are_consistent():
    cache=LocalSpeechCache();cache.put("a"*64,b"audio");cache.clear()
    assert cache.stats().entries==0 and cache.stats().bytes_used==0
