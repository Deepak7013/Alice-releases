from pathlib import Path
import json

def test_gluttony_engine_is_quarantine_only():
    text=Path("alice/gluttony/assimilation.py").read_text(encoding="utf-8")
    assert "quarantine" in text
    assert "executed_external_code" in text
    assert "/zipball" in text
    assert "LocalInputAdapter" in text
    assert "subprocess.run" not in text
    assert "activate" not in text.lower() or "activation" in text.lower()

def test_ingest_guard_exists():
    text=Path("alice/security/ingest_guard.py").read_text(encoding="utf-8")
    assert "destructive_command" in text
    assert "persistence" in text
    assert "obfuscation" in text

def test_voice_sapi_uses_voice_name():
    text=Path("alice/voice/voice.py").read_text(encoding="utf-8")
    assert 'env["ALICE_SAPI_VOICE"]=selected_name or self._selected_name or ""' in text
    assert "SelectVoice($env:ALICE_SAPI_VOICE)" in text

def test_local_ai_auto_detection_and_self_tools():
    router=Path("alice/providers/router.py").read_text(encoding="utf-8")
    app=Path("alice/ui/app.py").read_text(encoding="utf-8")
    assert "_local_service_detected" in router
    assert 'local_ai_status' in app
    assert 'assimilate_repository' in app
    assert 'alice_read_source' in app
    assert 'alice_workspace_status' in app

def test_self_inspection_methods():
    text=Path("alice/maintenance/self_manager.py").read_text(encoding="utf-8")
    assert "def read_source" in text
    assert "def source_inventory" in text
    assert "def workspace_status" in text
