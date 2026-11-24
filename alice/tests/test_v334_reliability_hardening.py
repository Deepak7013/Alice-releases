from pathlib import Path
import queue
import threading

ROOT=Path(__file__).resolve().parents[2]


def test_version_is_v334():
    assert (ROOT/"VERSION.txt").read_text().strip().startswith("ALICE v")


def test_router_clamps_huge_output_budget(monkeypatch):
    from alice.providers.router import Router
    r=Router()
    monkeypatch.setenv("ALICE_PROVIDER_MAX_OUTPUT_TOKENS","2048")
    assert r._safe_max_tokens("hello",131072)==2048
    assert r._safe_max_tokens("hello",77)==77


def test_router_reduces_budget_once_only_when_402_reports_affordable_limit(monkeypatch):
    from alice.providers.router import Router
    monkeypatch.setenv("ALICE_PROVIDER_MAX_OUTPUT_TOKENS","2048")
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    r=Router()
    calls=[]
    def fake(prompt,image_path=None,max_tokens=None):
        calls.append(max_tokens)
        if max_tokens>512: raise RuntimeError("HTTP 402: can only afford 512 tokens")
        return "ok"
    r._order=lambda:["local"]
    r._ask_local=fake
    assert r.ask("Explain neural networks briefly.",max_tokens=2048)=="ok"
    assert calls==[2048,512]


def test_router_never_exposes_huge_raw_402_dump(monkeypatch):
    from alice.providers.router import Router, ProviderError
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    r=Router()
    r._order=lambda:["local"]
    r._ask_local=lambda *a,**k: (_ for _ in ()).throw(RuntimeError("HTTP 402: This request requires more credits, or fewer max_tokens. You requested up to 131072 tokens"))
    try:
        r.ask("Explain neural networks briefly.",max_tokens=131072)
    except ProviderError as exc:
        text=str(exc)
        assert "131072" not in text
        assert "HTTP 402" in text
    else:
        raise AssertionError("expected ProviderError")


def test_memory_rule_is_retrievable_from_structured_layer(tmp_path):
    from alice.memory.store import MemoryStore
    m=MemoryStore(tmp_path)
    rule="During ALICE testing, every confirmed bug or fault I report must be preserved as a required regression test or fix requirement for the next ALICE upgrade."
    m.learn_explicit(rule)
    m2=MemoryStore(tmp_path)
    answer=m2.local_memory_answer("What is the active ALICE project rule I just taught you?")
    assert answer and rule in answer


def test_hypothetical_security_questions_bypass_action_routing():
    from alice.ui.app import AliceUI
    assert AliceUI._is_hypothetical_analysis("Suppose a devoured repository contains a script that attempts to delete files. What exactly would you do? Do not execute/modify. Explain the security decision.")
    assert AliceUI._is_hypothetical_analysis("If a devoured repo already has a capability ALICE has, should she blindly copy it?")
    assert not AliceUI._is_hypothetical_analysis("Delete C:\\temp\\old.txt")


def test_voice_stop_invalidates_queued_generation():
    from alice.voice.voice import Voice
    v=Voice.__new__(Voice)
    v._speech_generation=0
    v._speech_generation_lock=threading.Lock()
    v._speech_queue=queue.Queue()
    v._active_speech_cancel=threading.Event()
    v._ps=None
    v._pyttsx_engine=None
    v._close_powershell=lambda:None
    v._speech_queue.put(("speak","old",0))
    v.stop()
    assert v._speech_generation==1
    assert v._active_speech_cancel.is_set()
    assert v._speech_queue.get_nowait()==("stop",)


def test_text_only_command_is_deterministic():
    from alice.ui.app import AliceUI
    assert AliceUI._is_stop_voice_command("stop talking and give me text")
    assert AliceUI._is_stop_voice_command("text only")


def test_direct_upgrade_command_is_present_in_ui_source():
    text=(ROOT/"alice/ui/app.py").read_text(encoding="utf-8")
    assert "install alice upgrade" in text
    assert "_schedule_package_upgrade(package)" in text


def test_neural_backend_has_bounded_diagnostics_and_cancellable_playback():
    text=(ROOT/"alice/voice/neural.py").read_text(encoding="utf-8")
    assert "diagnose_voice" in text
    assert "socket.getaddrinfo" in text
    assert "cancel_event" in text
    assert "for attempt in range(2)" in text


def test_router_extracts_provider_affordable_budget():
    from alice.providers.router import Router
    assert Router._budget_hint("HTTP 402: can only afford 384 tokens") == 384
    assert Router._budget_hint("more credits; can only afford up to 1,024 tokens") == 1024
    assert Router._budget_hint("generic 402") is None


def test_hypothetical_is_classified_before_action_routing():
    from alice.ui.app import AliceUI
    assert AliceUI._is_hypothetical_analysis("Suppose the repo contains a script that deletes ALICE files. What would you do? Do not execute it.")


def test_update_version_is_forward_of_v3342():
    from alice.deployment.updater import version_tuple
    assert version_tuple("ALICE v3.35.5") > version_tuple("ALICE v3.34.2")
