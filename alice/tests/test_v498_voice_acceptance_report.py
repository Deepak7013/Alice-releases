from ALICE_VOICE_ACCEPTANCE_CHECK import summarize_voice_diagnostics


def test_report_does_not_claim_audible_success_from_software_return_value():
    report = summarize_voice_diagnostics(
        platform_name='Windows', voices=[{'name': 'Microsoft Zira Desktop', 'id': 'zira', 'gender': ''}],
        selected_mode='sapi', piper_status={'ready': False}, neural_status={'ok': False},
        playback_attempted=True, playback_returned=True, playback_error='',
    )
    assert report['female_sapi_candidate_count'] == 1
    assert report['playback_test']['call_returned_true'] is True
    assert report['playback_test']['human_audible_confirmation_required'] is True
    assert report['overall'] == 'diagnostics_collected_user_confirmation_required'
    assert report['speech_text_recorded'] is False
    assert report['secrets_recorded'] is False


def test_diagnostics_only_never_claims_playback_was_tested():
    report = summarize_voice_diagnostics(
        platform_name='Linux', voices=[], selected_mode='neural', piper_status={}, neural_status={},
        playback_attempted=False, playback_returned=False, playback_error='',
    )
    assert report['playback_test']['call_returned_true'] is None
    assert report['overall'] == 'diagnostics_only_no_audio_claim'
