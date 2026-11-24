from alice.voice.cache_store import LocalSpeechCache
from alice.voice.synthesis_cache import LocalSynthesisCacheGateway

class Engine:
    name="local-neural"; version="1"; voice="Aria"; local_owned=True; remote_dependency=False; offline=True
    def __init__(self): self.calls=0
    def can_generate(self,text): return bool(text)
    def synthesize(self,text): self.calls+=1; return ("AUDIO:"+text).encode()

def test_local_synthesis_is_cached_and_reused():
    e=Engine(); g=LocalSynthesisCacheGateway(LocalSpeechCache())
    a=g.synthesize(e,"Hello world."); b=g.synthesize(e,"Hello world.")
    assert a.ok and not a.cache_hit and a.payload==b"AUDIO:Hello world."
    assert b.ok and b.cache_hit and b.payload==a.payload and e.calls==1

def test_speech_affecting_context_change_causes_cache_miss():
    e=Engine(); g=LocalSynthesisCacheGateway()
    a=g.synthesize(e,"Hello",rate=1.0); b=g.synthesize(e,"Hello",rate=1.1)
    assert a.ok and b.ok and not b.cache_hit and e.calls==2

def test_remote_or_unowned_engine_is_rejected_before_synthesis():
    class Remote(Engine): local_owned=False; remote_dependency=True; offline=False
    e=Remote(); r=LocalSynthesisCacheGateway().synthesize(e,"Hello")
    assert not r.ok and r.reason=="local_engine_required" and e.calls==0

def test_missing_synthesis_contract_is_rejected():
    class Incomplete: name="local"; local_owned=True; remote_dependency=False; offline=True
    r=LocalSynthesisCacheGateway().synthesize(Incomplete(),"Hello")
    assert not r.ok and r.reason=="synthesis_contract_missing"

def test_empty_or_nonbytes_audio_is_not_cached():
    class Bad(Engine):
        def synthesize(self,text): self.calls+=1; return "not audio bytes"
    e=Bad();g=LocalSynthesisCacheGateway();r=g.synthesize(e,"Hello")
    assert not r.ok and r.reason=="invalid_audio_payload" and g.cache.stats().entries==0

def test_synthesis_exception_returns_explicit_failure():
    class Broken(Engine):
        def synthesize(self,text): raise RuntimeError("device details")
    r=LocalSynthesisCacheGateway().synthesize(Broken(),"Hello")
    assert not r.ok and r.reason=="synthesis_failed"

def test_payload_over_cache_capacity_can_be_returned_but_not_cached():
    e=Engine();g=LocalSynthesisCacheGateway(LocalSpeechCache(max_bytes=2), max_payload_bytes=64)
    r=g.synthesize(e,"Hello")
    assert r.ok and not r.cache_hit and r.payload==b"AUDIO:Hello" and g.cache.stats().entries==0

def test_audio_payload_over_admission_limit_is_rejected():
    class Large(Engine):
        def synthesize(self,text): self.calls+=1; return b"x"*65
    e=Large();g=LocalSynthesisCacheGateway(max_payload_bytes=64)
    r=g.synthesize(e,"Hello")
    assert not r.ok and r.payload is None and r.reason=="audio_payload_too_large"
    assert g.cache.stats().entries==0

def test_invalid_payload_limit_is_rejected():
    import pytest
    for value in (0,-1,True,1.5,"12"):
        with pytest.raises(ValueError, match="max_payload_bytes_must_be_positive_integer"):
            LocalSynthesisCacheGateway(max_payload_bytes=value)


def test_oversized_text_is_rejected_before_engine_readiness_or_synthesis():
    class Counting(Engine):
        def __init__(self): super().__init__(); self.readiness_calls=0
        def can_generate(self,text): self.readiness_calls+=1; return True
    e=Counting(); g=LocalSynthesisCacheGateway(max_text_chars=4)
    r=g.synthesize(e,"hello")
    assert not r.ok and r.reason=="text_too_large" and e.calls==0 and e.readiness_calls==0

def test_invalid_text_limit_is_rejected():
    import pytest
    for value in (0,-1,True,1.5,"4"):
        with pytest.raises(ValueError, match="max_text_chars_must_be_positive_integer"):
            LocalSynthesisCacheGateway(max_text_chars=value)


def test_oversized_memoryview_is_rejected_before_bytes_copy():
    class LargeView(Engine):
        def synthesize(self,text): self.calls+=1; return memoryview(b"x"*65)
    e=LargeView(); g=LocalSynthesisCacheGateway(max_payload_bytes=64)
    r=g.synthesize(e,"Hello")
    assert not r.ok and r.payload is None and r.reason=="audio_payload_too_large"
    assert g.cache.stats().entries==0

def test_bytes_like_payload_at_limit_is_admitted():
    class Exact(Engine):
        def synthesize(self,text): self.calls+=1; return bytearray(b"x"*64)
    e=Exact(); g=LocalSynthesisCacheGateway(max_payload_bytes=64)
    r=g.synthesize(e,"Hello")
    assert r.ok and r.payload==b"x"*64
