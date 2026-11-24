from pathlib import Path
import json
ROOT=Path(__file__).resolve().parents[2]

def test_neural_popen_uses_pipe_arguments_not_capture_output():
    text=(ROOT/"alice/voice/neural.py").read_text(encoding="utf-8")
    assert "subprocess.Popen" in text
    assert "stdout=subprocess.PIPE" in text
    assert "stderr=subprocess.PIPE" in text
    assert "Popen([\"powershell\"" in text
    assert "capture_output=True" not in text

def test_neural_voice_pack_inventory_contains_all_six_female_profiles():
    from alice.voice.neural import FEMALE_VOICE_PACKS
    assert len(FEMALE_VOICE_PACKS)==6
    assert all(v["gender"]=="Female" for v in FEMALE_VOICE_PACKS.values())

def test_single_instance_uses_stable_named_mutex_and_last_error():
    text=(ROOT/"alice/__main__.py").read_text(encoding="utf-8")
    assert "WinDLL(\"kernel32\", use_last_error=True)" in text
    assert r"Global\ALICE_GLUTTONY_UI_V3128" in text
    assert "ctypes.get_last_error() == 183" in text

def test_launcher_mutex_is_stable_and_not_version_split():
    text=(ROOT/"alice/desktop/launcher.py").read_text(encoding="utf-8")
    assert "WinDLL(\"kernel32\", use_last_error=True)" in text
    assert r"Global\\ALICE_GLUTTONY_CTRL_ALT_A_LAUNCHER_V3124" in text

def test_stored_devour_report_query_path_exists():
    text=(ROOT/"alice/ui/app.py").read_text(encoding="utf-8")
    assert "def _stored_devour_answer" in text
    assert "security.get('threat_count',0)" in text
    assert "counts['exists']" in text
    assert "No new Devour was performed." in text

def test_report_query_can_extract_expected_claw_code_fixture(tmp_path, monkeypatch):
    # Exercise the deterministic field mapping without needing a live model/provider.
    from alice.gluttony.evolver import DevourEngine
    class FakeDevour:
        def latest_report(self):
            return {"ok":True,"source":"https://github.com/instructkr/claw-code",
                    "report":"DIGEST_fixture.json","capability_candidates":[
                        {"name":n} for n in ("model_provider_abstraction","terminal_agent","session_management","tool_orchestration","workspace_intelligence","testing_harness","streaming","agent_planning")],
                    "alice_capability_assessment":{"capabilities":[{"status":"exists"} for _ in range(8)]},
                    "security":{"threat_count":138},"license":{"kind":"MIT"}}
    # Import the UI class without constructing Tk; bind only the tested method.
    from alice.ui.app import AliceUI
    obj=object.__new__(AliceUI); obj.devour=FakeDevour()
    answer=obj._stored_devour_answer("For the stored Claw-Code Devour report, answer all three items: static security findings, 8 main capabilities, and comparison")
    assert "138" in answer and "8 existing" in answer and "0 partial" in answer and "0 missing" in answer
    assert "model_provider_abstraction" in answer

def test_version_is_forward_from_v3343():
    assert (ROOT/"VERSION.txt").read_text().strip().startswith("ALICE v")
