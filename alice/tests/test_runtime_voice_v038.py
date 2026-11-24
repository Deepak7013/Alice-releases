from alice.voice import VoiceSession, CallableSTT

def test_voice_can_feed_runtime_handler():
    calls=[]
    v=VoiceSession(CallableSTT(lambda a:"do task"), command_handler=lambda text:calls.append(text) or "queued")
    v.start(); t=v.handle_audio(b"audio")
    assert calls==["do task"] and t.response=="queued"
