from pathlib import Path


def app_text():
    return (Path(__file__).resolve().parents[1] / "ui" / "app.py").read_text(encoding="utf-8")


def test_compact_ui_uses_tools_menu_instead_of_button_row():
    text=app_text()
    assert 'text="Tools ▾"' in text
    assert 'label="Conversation History"' in text
    assert 'label="Voice & Microphone"' in text
    assert 'for label,cmd,w in (("Voice"' not in text


def test_history_is_exposed_as_a_direct_local_command():
    text=app_text()
    assert '"show conversation history"' in text
    assert 'self._queue_ui("history")' in text
    assert 'def show_history(self):' in text


def test_microphone_manager_is_wired_into_listen_path():
    text=app_text()
    assert 'from ..voice.input import MicrophoneManager' in text
    assert 'self.microphone=MicrophoneManager(self.root_path)' in text
    assert 'self.microphone.recognize_once(timeout=5,phrase_time_limit=12)' in text
    assert 'self.voice.listen_async(self._heard)' not in text


def test_version_and_voice_input_dependencies():
    root=Path(__file__).resolve().parents[2]
    assert (root/"VERSION.txt").read_text(encoding="utf-8").strip().startswith("ALICE v")
    req=(root/"requirements_audio.txt").read_text(encoding="utf-8")
    assert "SpeechRecognition>=3.14" in req
    assert "sounddevice>=0.5.2" in req
    assert "edge-tts>=7.2.0" in req
    core=(root/"requirements.txt").read_text(encoding="utf-8")
    assert "SpeechRecognition" not in core
    assert "sounddevice" not in core


def test_microphone_selection_prefers_saved_then_headset_then_default():
    from alice.voice.input import MicrophoneManager
    m=MicrophoneManager(root=Path(__file__).resolve().parents[2])
    devices=[
        {"index":0,"name":"Microphone Array","default":True,"max_input_channels":2},
        {"index":1,"name":"Noise Buds VS102 NEO Headset","default":False,"max_input_channels":1},
    ]
    assert m.choose_best(devices)["index"]==1
    m.settings["device_name"]="Microphone Array"
    assert m.choose_best(devices)["index"]==0


def test_installer_migrates_v331_and_still_uses_staged_target():
    root=Path(__file__).resolve().parents[2]
    ps=(root/"INSTALL_ALICE.ps1").read_text(encoding="utf-8")
    assert "C:\\Alice_v3.31.0" in ps
    assert "ALICE_STAGE_" in ps
    assert "Move-Item $Stage $Root" in ps
    assert "optional audio input + female neural voice stack" in ps
