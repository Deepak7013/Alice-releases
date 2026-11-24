from alice.voice.cache_policy import speech_cache_key
class Engine:
    name="local"; voice="Alice"; version="1"
def test_cache_key_stays_deterministic_for_same_context():
    a=speech_cache_key("Hello",engine=Engine(),pronunciation={"GPU":"G P U"})
    b=speech_cache_key("Hello",engine=Engine(),pronunciation={"GPU":"G P U"})
    assert a==b and len(a)==64
def test_voice_version_locale_and_pronunciation_invalidate_key():
    base=speech_cache_key("Hello",engine=Engine())
    assert base!=speech_cache_key("Hello",engine=Engine(),voice="Other")
    assert base!=speech_cache_key("Hello",engine=Engine(),engine_version="2")
    assert base!=speech_cache_key("Hello",engine=Engine(),locale="hi-IN")
    assert base!=speech_cache_key("Hello",engine=Engine(),pronunciation={"Hello":"hullo"})
def test_rate_emotion_and_profile_invalidate_key():
    base=speech_cache_key("Hello",engine=Engine())
    assert base!=speech_cache_key("Hello",engine=Engine(),rate=1.1)
    assert base!=speech_cache_key("Hello",engine=Engine(),emotion="warm")
    assert base!=speech_cache_key("Hello",engine=Engine(),profile="casual")
def test_missing_text_or_engine_returns_none():
    assert speech_cache_key("",engine=Engine()) is None
    assert speech_cache_key("Hello",engine=None) is None
