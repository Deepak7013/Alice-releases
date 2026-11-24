from pathlib import Path

import pytest

from alice.devices.discovery import DeviceCandidate
from alice.devices.selector import DeviceSelectionError, DeviceSelector
from alice.devices.registry import DeviceRegistry
from alice.security.device_authorization import AuthorizationError, DeviceAuthorizationManager
from alice.security.device_consent import DeviceConsent


def candidate(device_id, name, kind="android", online=True):
    return DeviceCandidate(device_id, name, kind, ("adb",), "adb", online)


def test_select_by_exact_id_without_authorizing():
    item = candidate("ABC123", "OnePlus 15R")
    selected = DeviceSelector.select([item], "ABC123")
    assert selected.id == "ABC123"


def test_select_exact_name_case_insensitive():
    item = candidate("ABC123", "OnePlus 15R")
    assert DeviceSelector.select([item], "oneplus 15r").id == "ABC123"


def test_partial_selection_requires_unique_match():
    items = [candidate("A1", "OnePlus 15R"), candidate("B2", "Samsung S26")]
    assert DeviceSelector.select(items, "Samsung").id == "B2"
    with pytest.raises(DeviceSelectionError):
        DeviceSelector.select(items, "Phone")


def test_selection_never_changes_authorization(tmp_path):
    registry = DeviceRegistry(tmp_path)
    d = registry.register("OnePlus 15R", "android", ["adb"])
    selected = DeviceSelector.select(
        [candidate(d["id"], d["name"])], "OnePlus 15R"
    )
    assert selected.id == d["id"]
    assert registry.get(d["id"])["paired"] is False
    assert DeviceConsent(tmp_path).allowed(d["id"], "adb") is False


def test_authorization_request_is_pending_and_scoped(tmp_path):
    registry = DeviceRegistry(tmp_path)
    d = registry.register("OnePlus 15R", "android", ["adb", "notifications"])
    manager = DeviceAuthorizationManager(tmp_path, registry=registry)
    request = manager.request(d["id"], ["notifications", "adb", "adb"])
    assert request["status"] == "pending"
    assert request["scopes"] == ["adb", "notifications"]
    assert registry.get(d["id"])["paired"] is False
    assert DeviceConsent(tmp_path).allowed(d["id"], "adb") is False


def test_approve_grants_only_requested_scopes_and_pairs(tmp_path):
    registry = DeviceRegistry(tmp_path)
    d = registry.register("Phone", "android", ["adb", "notifications", "messages"])
    consent = DeviceConsent(tmp_path)
    manager = DeviceAuthorizationManager(tmp_path, registry=registry, consent=consent)
    req = manager.request(d["id"], ["adb", "notifications"])
    result = manager.approve(req["id"])
    assert result["status"] == "approved"
    assert registry.get(d["id"])["paired"] is True
    assert consent.allowed(d["id"], "adb")
    assert consent.allowed(d["id"], "notifications")
    assert not consent.allowed(d["id"], "messages")


def test_deny_does_not_grant_or_pair(tmp_path):
    registry = DeviceRegistry(tmp_path)
    d = registry.register("Phone", "android", ["adb"])
    manager = DeviceAuthorizationManager(tmp_path, registry=registry)
    req = manager.request(d["id"], ["adb"])
    result = manager.deny(req["id"])
    assert result["status"] == "denied"
    assert registry.get(d["id"])["paired"] is False
    assert not DeviceConsent(tmp_path).allowed(d["id"], "adb")


def test_expired_request_cannot_be_approved(tmp_path):
    registry = DeviceRegistry(tmp_path)
    d = registry.register("Phone", "android", ["adb"])
    manager = DeviceAuthorizationManager(tmp_path, registry=registry, request_ttl_seconds=1)
    req = manager.request(d["id"], ["adb"])
    # Make expiry deterministic without sleeping.
    manager.data[req["id"]]["expires_at"] = "2000-01-01T00:00:00+00:00"
    manager._save()
    with pytest.raises(AuthorizationError):
        manager.approve(req["id"])
    assert manager.get(req["id"])["status"] == "expired"


def test_unknown_device_cannot_request_authorization(tmp_path):
    manager = DeviceAuthorizationManager(tmp_path)
    with pytest.raises(AuthorizationError):
        manager.request("missing", ["adb"])


def test_approval_is_persistent(tmp_path):
    registry = DeviceRegistry(tmp_path)
    d = registry.register("Phone", "android", ["adb"])
    manager = DeviceAuthorizationManager(tmp_path, registry=registry)
    req = manager.request(d["id"], ["adb"])
    manager.approve(req["id"])
    restored = DeviceAuthorizationManager(tmp_path)
    assert restored.get(req["id"])["status"] == "approved"
    assert restored.consent.allowed(d["id"], "adb")
    assert restored.registry.get(d["id"])["paired"] is True
