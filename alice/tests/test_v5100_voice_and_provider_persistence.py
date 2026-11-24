import json
from pathlib import Path

import pytest


def test_voice_settings_recover_from_verified_continuity_when_primary_is_corrupt(tmp_path):
    from alice.voice.continuity import VoiceContinuityGuard
    from alice.voice.voice import Voice

    runtime = tmp_path / "alice_workspace" / "runtime"
    runtime.mkdir(parents=True)
    settings = runtime / "voice.json"
    settings.write_text("{broken", encoding="utf-8")
    guard = VoiceContinuityGuard(runtime / "voice_continuity.json")
    guard.remember(voice_id="saved-voice-id", name="Alice saved voice", mode="sapi", neural_voice="")

    voice = Voice.__new__(Voice)
    voice.root = tmp_path
    voice.settings_path = settings
    voice.continuity = guard
    saved = voice._load_with_recovery()

    assert saved["voice_name"] == "saved-voice-id"
    assert saved["mode"] == "sapi"
    assert json.loads(settings.read_text(encoding="utf-8")) == saved


def test_voice_recovery_rejects_tampered_continuity(tmp_path):
    from alice.voice.continuity import VoiceContinuityGuard

    guard = VoiceContinuityGuard(tmp_path / "voice_continuity.json")
    guard.remember(voice_id="voice-a", name="Alice", mode="sapi")
    payload = json.loads(guard.path.read_text(encoding="utf-8"))
    payload["voice_id"] = "voice-b"
    guard.path.write_text(json.dumps(payload), encoding="utf-8")
    assert guard.recover_settings() is None


def test_hosted_key_save_preserves_other_env_values(tmp_path, monkeypatch):
    from alice.providers.configuration import save_openrouter_config
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "ALICE_PRIMARY_PROVIDER", "ALICE_RUNTIME_MODE"):
        monkeypatch.setenv(name, "")

    env = tmp_path / ".env"
    env.write_text("OTHER_SETTING=keep\nOPENROUTER_API_KEY=old\nOPENROUTER_MODEL=old-model\n", encoding="utf-8")
    save_openrouter_config(env, "new-key", "openrouter/auto")
    saved = env.read_text(encoding="utf-8")
    assert "OTHER_SETTING=keep" in saved
    assert "OPENROUTER_API_KEY=new-key" in saved
    assert "OPENROUTER_MODEL=openrouter/auto" in saved
    assert not list(tmp_path.glob(".env*.tmp"))


def test_hosted_key_save_normalizes_legacy_export_format(tmp_path, monkeypatch):
    from alice.providers.configuration import save_openrouter_config
    for name in ("OPENROUTER_API_KEY", "OPENROUTER_MODEL", "ALICE_PRIMARY_PROVIDER", "ALICE_RUNTIME_MODE"):
        monkeypatch.setenv(name, "")

    env = tmp_path / ".env"
    env.write_text("export OPENROUTER_API_KEY = old\n OPENROUTER_MODEL = old\n", encoding="utf-8")
    save_openrouter_config(env, "new-key", "new-model")
    saved = env.read_text(encoding="utf-8")
    assert "OPENROUTER_API_KEY=new-key" in saved
    assert "OPENROUTER_MODEL=new-model" in saved
    assert not saved.lstrip().startswith("export ")
