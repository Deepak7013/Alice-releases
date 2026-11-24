from alice.voice.cache_policy import speech_cache_key

class Engine:
    name = "local"

def test_cache_key_is_deterministic():
    assert speech_cache_key("Hello", engine=Engine()) == speech_cache_key("Hello", engine=Engine())

def test_cache_key_changes_for_engine_or_profile():
    class Other: name = "other"
    a = speech_cache_key("Hello", engine=Engine(), profile="natural")
    b = speech_cache_key("Hello", engine=Other(), profile="natural")
    c = speech_cache_key("Hello", engine=Engine(), profile="casual")
    assert a != b and a != c

def test_cache_key_none_for_missing_inputs():
    assert speech_cache_key("", engine=Engine()) is None
    assert speech_cache_key("Hello", engine=None) is None
