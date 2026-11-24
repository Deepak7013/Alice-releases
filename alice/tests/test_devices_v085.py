from types import SimpleNamespace

import pytest

from alice.devices.discovery import (
    DeviceCandidate,
    DeviceDiscovery,
    DiscoveryError,
    parse_adb_devices,
)
from alice.devices.registry import DeviceRegistry


def test_parse_adb_devices():
    output = """List of devices attached
R58M123ABC    device product:foo model:OnePlus_15R device:foo transport_id:1
ABC999        unauthorized usb:1
OFF123        offline product:x model:Old_Phone
bad serial    device model:Nope
"""
    found = parse_adb_devices(output)
    assert [d.id for d in found] == ["R58M123ABC", "ABC999", "OFF123"]
    assert found[0].name == "OnePlus 15R"
    assert found[0].online is True
    assert found[1].online is False
    assert found[1].metadata["state"] == "unauthorized"


def test_discovery_does_not_pair_or_modify_registry(tmp_path):
    registry = DeviceRegistry(tmp_path)
    device = registry.register("My Phone", "android", ["adb"])
    before = registry.get(device["id"])

    discovery = DeviceDiscovery(registry=registry, runner=lambda *a, **k:
        SimpleNamespace(returncode=0, stdout="", stderr=""))
    found = discovery.discover(include_adb=True)

    assert found[0].id == device["id"]
    assert found[0].source == "registry"
    assert registry.get(device["id"]) == before
    assert registry.get(device["id"])["paired"] is False


def test_adb_discovery_works_with_injected_runner():
    def runner(args, **kwargs):
        assert args == ["adb", "devices", "-l"]
        assert kwargs["check"] is False
        return SimpleNamespace(
            returncode=0,
            stdout="List of devices attached\nSER123 device model:Test_Phone\n",
            stderr="",
        )

    found = DeviceDiscovery(runner=runner).discover(include_registry=False)
    assert len(found) == 1
    assert found[0].id == "SER123"
    assert found[0].name == "Test Phone"


def test_duplicate_prefers_live_adb():
    known = DeviceCandidate("SER123", "Old", "android", ("adb",), "registry", False)
    live = DeviceCandidate("SER123", "New", "android", ("adb",), "adb", True)
    merged = DeviceDiscovery.merge([known, live])
    assert len(merged) == 1
    assert merged[0].source == "adb"
    assert merged[0].online is True


def test_adb_failure_is_nonfatal_by_default_and_strict_when_requested():
    def runner(*args, **kwargs):
        raise FileNotFoundError("adb")

    discovery = DeviceDiscovery(runner=runner)
    assert discovery.discover(include_registry=False) == []
    with pytest.raises(DiscoveryError, match="ADB discovery unavailable"):
        discovery.discover(include_registry=False, strict=True)


def test_online_only_filters_unauthorized_and_offline(tmp_path):
    registry = DeviceRegistry(tmp_path)
    offline = registry.register("Offline", "android")
    online = registry.register("Online", "android")
    registry.set_online(online["id"], True)

    discovery = DeviceDiscovery(registry=registry, include_adb=False) if False else DeviceDiscovery(registry=registry)
    found = discovery.discover(include_adb=False, online_only=True)
    assert [d.id for d in found] == [online["id"]]
