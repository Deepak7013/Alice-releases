from alice.agent.agent import AliceAgent
from alice.ui.app import AliceUI


def test_normal_text_request_does_not_need_tools():
    assert AliceUI._needs_tools("What is 25 x 25?") is False
    assert AliceUI._needs_tools("Explain what recursion means") is False


def test_desktop_request_needs_tools():
    assert AliceUI._needs_tools("open calculator") is True
    assert AliceUI._needs_tools("click the Start button") is True


def test_text_and_concise_defaults_are_enabled():
    # UI state defaults are part of the public interaction contract.
    assert "Text: ON" in open("alice/ui/app.py", encoding="utf-8").read()
    assert "Concise: ON" in open("alice/ui/app.py", encoding="utf-8").read()


def test_agent_has_direct_brain_response_path():
    assert callable(AliceAgent.respond_text)


def test_startup_installer_exists():
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    text=(root/"INSTALL_ALICE_STARTUP.bat").read_text(encoding="utf-8")
    assert "schtasks /Create" in text
    assert "ONLOGON" in text
    assert "pythonw.exe" in text
