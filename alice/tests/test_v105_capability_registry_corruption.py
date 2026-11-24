import json
import pytest

from alice.capabilities.manager import CapabilityGap, CapabilityManager


@pytest.mark.parametrize("payload", [
    b'{"terminal_agent": ',
    b'[]',
    b'{"terminal_agent": null}',
])
def test_corrupt_capability_registry_is_preserved_and_fails_closed(tmp_path, payload):
    registry_path = tmp_path / "alice_workspace" / "capabilities.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_bytes(payload)

    with pytest.raises(CapabilityGap, match="preserved"):
        CapabilityManager(tmp_path)

    assert registry_path.read_bytes() == payload


def test_oversized_capability_registry_is_preserved_and_fails_closed(tmp_path):
    registry_path = tmp_path / "alice_workspace" / "capabilities.json"
    registry_path.parent.mkdir(parents=True)
    payload = b" " * (8 * 1024 * 1024 + 1)
    registry_path.write_bytes(payload)

    with pytest.raises(CapabilityGap, match="8 MiB"):
        CapabilityManager(tmp_path)

    assert registry_path.stat().st_size == len(payload)


def test_valid_capability_registry_still_loads(tmp_path):
    registry_path = tmp_path / "alice_workspace" / "capabilities.json"
    registry_path.parent.mkdir(parents=True)
    registry_path.write_text(json.dumps({"terminal_agent": {
        "name": "terminal_agent", "description": "candidate", "acquisition_evidence": []
    }}), encoding="utf-8")

    manager = CapabilityManager(tmp_path, initialize=False)
    assert manager.get("terminal_agent")["name"] == "terminal_agent"
