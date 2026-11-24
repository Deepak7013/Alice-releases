from alice.voice.pipeline import LocalSpeechPipelinePlanner, STAGES


class LocalEngine:
    name = "alice_local_neural"
    local_owned = True
    remote_dependency = False
    offline = True


class RemoteEngine:
    name = "remote_tts"
    local_owned = False
    remote_dependency = True
    offline = False


def test_local_pipeline_has_required_order():
    r = LocalSpeechPipelinePlanner().plan("Hello world.", engine=LocalEngine())
    assert r.valid
    assert r.stages == STAGES
    assert r.stages[:2] == ("normalize", "pronunciation")
    assert r.stages[-2:] == ("synthesize", "playback")


def test_remote_engine_cannot_satisfy_local_pipeline():
    r = LocalSpeechPipelinePlanner().plan("hello", engine=RemoteEngine())
    assert not r.valid and r.reason == "local_pipeline_required"


def test_empty_text_is_blocked():
    r = LocalSpeechPipelinePlanner().plan("  ", engine=LocalEngine())
    assert not r.valid and r.reason == "text_missing"


def test_missing_engine_is_blocked():
    r = LocalSpeechPipelinePlanner().plan("hello", engine=None)
    assert not r.valid and r.reason == "engine_missing"


def test_planner_has_no_side_effects():
    r = LocalSpeechPipelinePlanner().plan("hello", engine=LocalEngine())
    assert r.valid
    assert not hasattr(r, "audio")
