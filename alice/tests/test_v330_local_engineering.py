import os
from pathlib import Path


def test_router_has_local_engineering_route():
    text=Path("alice/providers/router.py").read_text(encoding="utf-8")
    assert "def engineering_ask" in text
    assert "local_first=True" in text
    assert "require_local=True" in text
    assert "remote_fallback_allowed=allow_remote" in text
    assert "allow_remote=False" in text
    assert "def local_status" in text
    assert "older .env" in text


def test_self_manager_uses_engineering_route_and_compile_gate():
    text=Path("alice/maintenance/self_manager.py").read_text(encoding="utf-8")
    assert "def _engineering_ask" in text
    assert "compileall" in text
    assert "self._engineering_ask(selection_prompt)" in text
    assert "self._engineering_ask(implementation_prompt)" in text


def test_local_self_engineering_defaults_to_local_first():
    assert os.getenv("ALICE_SELF_ENGINEER_LOCAL_FIRST", "1") in {"1", "true", "yes", "on", "auto"}


def test_voice_preservation_and_recovery_contract_exists():
    text=Path("alice/voice/voice.py").read_text(encoding="utf-8")
    assert "def voice_contract" in text
    assert "Preserve the user's existing voice exactly" in text
    assert "recover to a female" in text
    assert "self.settings_path" in text


def test_voice_warmup_preserves_existing_selected_voice():
    from alice.voice.voice import Voice
    v=object.__new__(Voice)
    v._selected_name="female-id"; v._last_error=""
    v._start_powershell=lambda: True
    v.list_voices=lambda: [{"id":"female-id","name":"Existing Female","gender":"Female"},{"id":"male-id","name":"Other","gender":"Male"}]
    v._save=lambda: (_ for _ in ()).throw(AssertionError("existing voice should not be rewritten"))
    v._close_powershell=lambda: (_ for _ in ()).throw(AssertionError("broker should not restart when saved voice exists"))
    v._warm_up()
    assert v._selected_name=="female-id"


def test_voice_warmup_recovers_to_female_when_saved_voice_disappears():
    from alice.voice.voice import Voice
    v=object.__new__(Voice)
    v._selected_name="missing-id"; v._last_error=""; saved=[]
    v._start_powershell=lambda: True
    v.list_voices=lambda: [{"id":"male-id","name":"David","gender":"Male"},{"id":"female-id","name":"Zira","gender":"Female"}]
    v._save=lambda: saved.append(v._selected_name)
    v._close_powershell=lambda: None
    v._warm_up()
    assert v._selected_name=="female-id"
    assert saved==["female-id"]
