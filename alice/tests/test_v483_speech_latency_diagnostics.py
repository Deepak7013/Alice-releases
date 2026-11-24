from alice.voice.latency_diagnostics import SpeechLatencyTrace
import pytest

def test_latency_trace_reports_stage_and_deltas_without_payload():
    trace = SpeechLatencyTrace(_started=10.0)
    trace.mark("response_ready", at=10.1)
    trace.mark("first_audio", at=10.35)
    report = trace.report()
    assert report["schema"] == 1
    assert report["total_ms"] == 350.0
    assert report["stages"] == [
        {"stage": "response_ready", "elapsed_ms": 100.0, "since_previous_ms": 100.0},
        {"stage": "first_audio", "elapsed_ms": 350.0, "since_previous_ms": 250.0},
    ]
    assert "text" not in report and "api_key" not in report

def test_latency_trace_rejects_blank_stage():
    trace = SpeechLatencyTrace(_started=1.0)
    with pytest.raises(ValueError): trace.mark(" ", at=1.1)

def test_latency_trace_rejects_timestamp_before_start():
    trace = SpeechLatencyTrace(_started=1.0)
    with pytest.raises(ValueError): trace.mark("bad", at=0.9)
