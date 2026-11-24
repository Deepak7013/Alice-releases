from alice.ui.response_stream import ResponseStreamAssembler
from alice.ui.stream_delivery import ResponseStreamDeliveryGate

def test_completed_stream_uses_one_canonical_ui_and_voice_text():
    s=ResponseStreamAssembler(); s.add("Hello "); s.add("from ALICE.")
    r=ResponseStreamDeliveryGate().deliver(s)
    assert r.complete and r.delivery.text=="Hello from ALICE."
    assert r.sync.display_text==r.sync.voice_text==r.delivery.text and r.sync.speak

def test_incomplete_stream_never_enters_voice_path():
    s=ResponseStreamAssembler(); s.add("partial"); s.abort("provider_timeout")
    r=ResponseStreamDeliveryGate().deliver(s)
    assert not r.complete and not r.sync.speak and not r.sync.voice_text
    assert r.delivery.text and r.sync.display_text==r.delivery.text

def test_voice_disabled_keeps_complete_text_only():
    s=ResponseStreamAssembler(); s.add("Visible answer.")
    r=ResponseStreamDeliveryGate().deliver(s,voice_enabled=False)
    assert r.complete and not r.sync.speak and not r.sync.voice_text
    assert r.sync.display_text=="Visible answer."

def test_empty_stream_is_explicit_and_not_spoken():
    r=ResponseStreamDeliveryGate().deliver(ResponseStreamAssembler())
    assert not r.complete and r.delivery.text and not r.sync.speak
