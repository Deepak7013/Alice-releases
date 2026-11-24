from alice.voice import VoiceSession, CallableSTT, CallableTTS

def test_voice_session_turn_and_tts():
    spoken=[]
    s=VoiceSession(CallableSTT(lambda a:"open calculator"), CallableTTS(spoken.append), lambda x:"Received: "+x)
    s.start(); t=s.handle_audio(b"audio")
    assert t.status=="completed" and t.transcript=="open calculator"
    assert spoken==["Received: open calculator"]

def test_voice_session_requires_start():
    s=VoiceSession(CallableSTT(lambda a:"hello"))
    try: s.handle_audio(b"x"); assert False
    except RuntimeError: pass
