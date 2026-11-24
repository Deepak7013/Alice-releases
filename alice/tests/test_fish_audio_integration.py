import base64
import os
from pathlib import Path
from types import SimpleNamespace

import pytest

from alice.voice.fish_audio import FishAudioProvider
from alice.voice.secret_store import FishAudioSecretStore


def _protected_store(tmp_path):
    # Deterministic reversible test wrapper; not used by application code.
    return FishAudioSecretStore(
        tmp_path / "fish.key.dpapi",
        protect=lambda value: base64.b64encode(b"test-wrapper:" + value),
        unprotect=lambda value: base64.b64decode(value).removeprefix(b"test-wrapper:"),
    )


def test_fish_audio_secret_store_never_writes_plaintext_and_round_trips(tmp_path):
    store = _protected_store(tmp_path)
    store.set("fish-test-key-do-not-leak")
    assert store.has()
    assert store.get() == "fish-test-key-do-not-leak"
    assert b"fish-test-key-do-not-leak" not in (tmp_path / "fish.key.dpapi").read_bytes()
    store.delete()
    assert not store.has()
    assert store.get() == ""


@pytest.mark.skipif(os.name != "nt", reason="Windows DPAPI is platform-specific")
def test_fish_audio_real_windows_dpapi_round_trip_and_ciphertext(tmp_path):
    store = FishAudioSecretStore(tmp_path / "actual.dpapi")
    store.set("non-production-dpapi-test-token")
    assert store.get() == "non-production-dpapi-test-token"
    assert b"non-production-dpapi-test-token" not in (tmp_path / "actual.dpapi").read_bytes()


def test_fish_audio_tts_uses_saved_voice_id_and_returns_only_playback_status(tmp_path):
    calls = {}

    class TTS:
        def convert(self, **kwargs):
            calls["request"] = kwargs
            return b"fake-mp3-data"

    played = []
    # The factory records the key only in this test process and returns a fake client.
    provider = FishAudioProvider(
        _protected_store(tmp_path), tmp_path / "cache",
        client_factory=lambda key: (calls.update(key_seen_by_client=key) or SimpleNamespace(tts=TTS())),
        playback=lambda path, cancel_event=None: played.append(Path(path).read_bytes()) or True,
    )
    provider.secrets.set("fish-test-key-do-not-leak")
    assert provider.speak("test phrase", "saved-voice-model-id")
    assert calls["request"]["text"] == "test phrase"
    assert calls["request"]["reference_id"] == "saved-voice-model-id"
    assert played == [b"fake-mp3-data"]
    assert list((tmp_path / "cache").glob("*.mp3")) == []


def test_fish_audio_provider_reports_missing_setup_without_network(tmp_path):
    provider = FishAudioProvider(_protected_store(tmp_path), tmp_path / "cache", client_factory=lambda key: pytest.fail("unexpected request"))
    status = provider.status("")
    assert status == {
        "provider": "fish_audio", "key_configured": False, "voice_id_configured": False,
        "sdk_available": provider.sdk_available(), "ready": False, "reason": "api_key_missing",
    }
    with pytest.raises(RuntimeError, match="fish_audio_configuration_missing"):
        provider.speak("test", "")


def test_fish_audio_errors_are_sanitized_and_temp_audio_is_removed(tmp_path):
    class TTS:
        def convert(self, **kwargs):
            raise RuntimeError("Authorization: Bearer fish-test-key-do-not-leak")

    provider = FishAudioProvider(
        _protected_store(tmp_path), tmp_path / "cache",
        client_factory=lambda key: SimpleNamespace(tts=TTS()), playback=lambda *args, **kwargs: True,
    )
    provider.secrets.set("fish-test-key-do-not-leak")
    with pytest.raises(RuntimeError) as error:
        provider.speak("test", "saved-voice-model-id")
    assert "fish-test-key-do-not-leak" not in str(error.value)
    assert not list((tmp_path / "cache").glob("*.mp3"))


def test_selected_fish_voice_never_falls_back_to_another_provider():
    from alice.voice.voice import Voice

    class BrokenFish:
        def speak(self, *args, **kwargs):
            raise RuntimeError("fish_audio_http_402")

    voice = Voice.__new__(Voice)
    voice._voice_mode = "fish_audio"
    voice._fish_audio_voice_id = "saved-voice-model-id"
    voice.fish_audio = BrokenFish()
    voice._failure_count = 0
    voice._spoken_count = 0
    voice._last_error = ""
    voice._last_provider = ""
    voice._speak_neural = lambda *_: pytest.fail("Fish Audio failure must not fall back to neural")
    voice._speak_sapi = lambda *_: pytest.fail("Fish Audio failure must not fall back to SAPI")
    assert voice._speak_with_recovery("bounded test") is False
    assert voice._last_error == "fish_audio_http_402"
    assert voice._last_provider == "fish_audio"
    assert voice._failure_count == 1


def test_fish_audio_voice_selection_persists_explicit_provider_choice():
    from alice.voice.voice import Voice

    voice = Voice.__new__(Voice)
    voice._voice_mode = "neural"
    voice._fish_audio_voice_id = "saved-voice-model-id"
    voice._selected_name = ""
    voice._neural_voice = "en-US-AriaNeural"
    voice._last_error = "old failure"
    voice._last_provider = "microsoft_edge_neural"
    voice._backend_kind = ""
    voice._backend_ready = False
    saved = []
    voice.fish_audio_status = lambda: {"ready": True, "reason": "ready"}
    voice.stop = lambda: None
    voice._save = lambda: saved.append((voice._voice_mode, voice._fish_audio_voice_id))
    selected = voice.select_fish_audio_voice()
    assert selected["id"] == "saved-voice-model-id"
    assert voice._voice_mode == "fish_audio"
    assert voice._neural_voice == ""
    assert saved == [("fish_audio", "saved-voice-model-id")]


def test_voice_settings_dialog_exposes_masked_fish_key_and_voice_id_controls():
    from pathlib import Path

    source = Path(__file__).parents[1].joinpath("ui", "app.py").read_text(encoding="utf-8")
    assert 'nb.add(fish_tab,text="Fish Audio")' in source
    assert 'show="*"' in source
    assert "Fish Audio voice ID" in source
    assert "save_fish_audio_settings" in source
    assert "test_fish_audio_voice" in source
    assert 'elif kind == "fish_audio_test"' in source
    assert "sends one fixed sample sentence to Fish Audio" in source
