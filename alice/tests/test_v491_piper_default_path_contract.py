from pathlib import Path

def test_voice_manager_uses_runtime_piper_config_path():
    source = (Path(__file__).parents[1] / "voice" / "voice.py").read_text(encoding="utf-8")
    assert '"alice_workspace" / "runtime" / "piper_voice.json"' in source

def test_piper_diagnostic_is_explicitly_non_executing():
    source = (Path(__file__).parents[2] / "DIAGNOSE_PIPER_CONFIG.py").read_text(encoding="utf-8")
    assert "does not execute Piper" in source
    assert "subprocess" not in source
