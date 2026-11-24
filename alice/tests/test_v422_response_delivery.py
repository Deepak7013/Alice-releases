from alice.ui.response_delivery import canonicalize_response


def test_completed_response_is_shared_by_ui_and_voice():
    result = canonicalize_response({"status": "completed", "result": "  Hello ALICE.  "})
    assert result.valid is True
    assert result.text == "Hello ALICE."
    assert result.voice_text == result.text


def test_failed_provider_response_never_becomes_blank():
    result = canonicalize_response({"status": "failed", "error": "provider returned empty response"})
    assert result.valid is True
    assert result.text.startswith("Error: provider returned empty response")
    assert result.voice_text == result.text


def test_empty_completed_response_is_replaced_explicitly():
    result = canonicalize_response({"status": "completed", "result": ""})
    assert result.valid is False
    assert result.reason == "empty_response_replaced"
    assert result.text
    assert result.voice_text == ""


def test_approval_response_is_canonical():
    result = canonicalize_response({"status": "awaiting_approval", "approval": {"reason": "Write access required."}})
    assert result.text == "I need your approval before doing this.\nReason: Write access required."
    assert result.voice_text == result.text
