from ALICE_VOICE_ACCEPTANCE_CHECK import assess_selected_mode


def test_neural_assessment_does_not_claim_audio_was_heard():
    result = assess_selected_mode(selected_mode="neural", voices=[], piper_status={}, neural_status={"ok": True})
    assert result["status"] == "ready_signal_present"
    assert result["audible_playback_proven"] is False


def test_piper_not_ready_exposes_reason():
    result = assess_selected_mode(selected_mode="piper", voices=[], piper_status={"ready": False, "reason": "model_missing"}, neural_status={})
    assert result["status"] == "not_ready"
    assert result["reason"] == "model_missing"
    assert result["audible_playback_proven"] is False


def test_sapi_only_reports_candidate_visibility():
    result = assess_selected_mode(selected_mode="sapi", voices=[{"name": "Microsoft Zira Desktop", "id": "zira"}], piper_status={}, neural_status={})
    assert result["status"] == "female_candidate_visible"
    assert result["reason"] == "candidate_visibility_only_not_selected_voice_proof"
    assert result["audible_playback_proven"] is False


def test_unknown_mode_is_not_marked_ready():
    result = assess_selected_mode(selected_mode="mystery", voices=[], piper_status={}, neural_status={})
    assert result["status"] == "unknown_mode"
    assert result["audible_playback_proven"] is False
