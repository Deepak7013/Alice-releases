from pathlib import Path


def test_neural_speech_path_records_timing_without_text_payload():
    source = Path('alice/voice/voice.py').read_text(encoding='utf-8')
    assert 'trace.mark("neural_synthesis_started")' in source
    assert 'trace.mark("neural_provider_call_finished")' in source
    assert 'self._last_speech_latency_report = trace.report()' in source
    assert 'def speech_latency_report(self):' in source
    # We deliberately do not claim a first-audio timestamp until the provider exposes one.
    assert 'mislabeling it as time-to-first-audio' in source


def test_latency_report_accessor_returns_a_defensive_copy():
    from alice.voice.voice import Voice
    voice = Voice.__new__(Voice)
    voice._last_speech_latency_report = {'schema': 1, 'total_ms': 12.5, 'stages': [{'stage': 'finished', 'elapsed_ms': 12.5, 'since_previous_ms': 12.5}]}
    result = voice.speech_latency_report()
    result['stages'][0]['stage'] = 'changed'
    assert voice._last_speech_latency_report['stages'][0]['stage'] == 'finished'
