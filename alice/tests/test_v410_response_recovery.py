from alice.ui.response_transaction import ResponseTransaction

def test_transaction_preserves_partial_text_on_failure():
    tx=ResponseTransaction(); tx.append("First part. "); tx.append("Second part.")
    state=tx.fail()
    assert state.text == "First part. Second part."
    assert state.recoverable is True
    assert state.completed is False

def test_transaction_empty_failure_is_not_recoverable():
    tx=ResponseTransaction(); state=tx.fail()
    assert state.text == ""
    assert state.recoverable is False

def test_completed_transaction_is_canonical():
    tx=ResponseTransaction(); tx.append("Complete answer."); state=tx.complete()
    assert state.completed is True
    assert state.text == "Complete answer."

def test_agent_has_bounded_recovery_method():
    from pathlib import Path
    text=(Path(__file__).resolve().parents[1]/"agent"/"agent.py").read_text(encoding="utf-8")
    assert "def respond_text_recovery" in text
    assert "Do not repeat any text already delivered" in text

def test_ui_uses_response_transaction():
    from pathlib import Path
    text=(Path(__file__).resolve().parents[1]/"ui"/"app.py").read_text(encoding="utf-8")
    assert "ResponseTransaction" in text
    assert "respond_text_recovery" in text

def test_generation_four_is_elysium():
    from pathlib import Path
    root=Path(__file__).resolve().parents[2]
    assert (root/"VERSION.txt").read_text(encoding="utf-8").strip().startswith("ALICE v4.")

def test_attestation_accepts_v4():
    from pathlib import Path
    import json
    from alice.deployment.upgrade_attestation import attest
    import tempfile
    with tempfile.TemporaryDirectory() as td:
        r=Path(td); (r/"VERSION.txt").write_text("ALICE v4.3.0",encoding="utf-8")
        (r/"full_install_manifest.json").write_text(json.dumps({"version":"ALICE v4.3.0","files":[]}),encoding="utf-8")
        assert attest(r,"ALICE v3.100.0").ok
