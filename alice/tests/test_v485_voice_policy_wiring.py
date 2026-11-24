from pathlib import Path
import ast


def test_voice_startup_imports_and_applies_default_policy_after_load():
    source = Path('alice/voice/voice.py').read_text(encoding='utf-8')
    tree = ast.parse(source)
    imports_policy = any(
        isinstance(node, ast.ImportFrom)
        and node.module == 'default_voice_policy'
        and any(alias.name == 'apply_default_voice' for alias in node.names)
        for node in ast.walk(tree)
    )
    assert imports_policy
    assert 'settings = self._load()' in source
    assert 'settings = apply_default_voice(raw_settings)' in source
    assert 'if settings != raw_settings:' in source


def test_voice_startup_does_not_overwrite_nonempty_saved_voice():
    from alice.voice.default_voice_policy import apply_default_voice
    saved = {'voice_name': 'Alice UK – Sonia', 'neural_voice': 'en-GB-SoniaNeural', 'mode': 'neural', 'enabled': True}
    assert apply_default_voice(saved) == saved
