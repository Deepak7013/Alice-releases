from pathlib import Path
import pytest
from alice.creation.service import CreationService
from alice.creation.models import CreationRequest, ArtifactKind


class FakeImageProvider:
    def generate(self, prompt, output_path, size='1024x1024'):
        path = Path(output_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b'fake-png-payload')
        return str(path)


def test_creation_service_generates_verifiable_image_artifact(tmp_path):
    service = CreationService(image_provider=FakeImageProvider(), root=tmp_path)
    artifact = service.create(CreationRequest(
        prompt='A small green robot on a desk', kind=ArtifactKind.IMAGE,
        filename='test image.png', context={'size': '1024x1024'}))
    assert artifact.exists
    assert Path(artifact.path).read_bytes() == b'fake-png-payload'
    assert Path(artifact.path).parent == (tmp_path / 'alice_workspace' / 'artifacts').resolve()


def test_image_creation_fails_clearly_without_provider(tmp_path):
    service = CreationService(root=tmp_path)
    with pytest.raises(RuntimeError, match='No image generation provider configured'):
        service.create(CreationRequest(prompt='robot', kind=ArtifactKind.IMAGE))


def test_image_provider_uses_supported_configurable_default_model(monkeypatch):
    monkeypatch.delenv('OPENAI_IMAGE_MODEL', raising=False)
    from alice.creation.image import OpenAIImageProvider
    assert OpenAIImageProvider().model == 'gpt-image-1'


def test_ui_registers_image_generation_as_external_action():
    from pathlib import Path
    source = (Path(__file__).resolve().parents[1] / 'ui' / 'app.py').read_text(encoding='utf-8')
    assert 't.add("generate_image"' in source
    assert 'generate_image,"external"' in source


def test_openai_image_provider_refuses_cloud_generation_in_local_only_mode(tmp_path, monkeypatch):
    from types import SimpleNamespace
    from alice.creation.image import OpenAIImageProvider
    monkeypatch.setenv("ALICE_RUNTIME_MODE", "local_required")
    calls = []
    client = SimpleNamespace(images=SimpleNamespace(generate=lambda **kwargs: calls.append(kwargs)))
    target = tmp_path / 'image.png'
    with pytest.raises(RuntimeError, match="local-only brain mode"):
        OpenAIImageProvider(client=client).generate('test image', target)
    assert calls == []
    assert not target.exists()


def test_openai_image_provider_rejects_unsupported_size_before_api_call():
    from types import SimpleNamespace
    from alice.creation.image import OpenAIImageProvider
    client = SimpleNamespace(images=SimpleNamespace(generate=lambda **kwargs: pytest.fail('API must not be called')))
    with pytest.raises(ValueError, match='Unsupported image size'):
        OpenAIImageProvider(client=client).generate('test image', 'unused.png', '999x999')
