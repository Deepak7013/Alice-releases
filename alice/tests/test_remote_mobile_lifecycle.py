import json
from types import SimpleNamespace

import pytest

from alice.remote.lifecycle import CONFIG_RELATIVE_PATH, RemoteMobileServiceController, read_config, start_configured_service, write_config
from alice.remote.pairing_store import DPAPIPairingStore


def protect(data):
    return b"test:" + data


def unprotect(data):
    assert data.startswith(b"test:")
    return data[5:]


class FakeService:
    def __init__(self, dispatcher, *, host, port):
        self.dispatcher = dispatcher
        self.host = host
        self.port = port
        self.started = False
        self.stopped = False

    @property
    def address(self):
        return (self.host, self.port)

    def start(self):
        self.started = True
        return self.address

    def shutdown(self):
        self.stopped = True


def make_store(tmp_path):
    return DPAPIPairingStore(tmp_path / "paired.dpapi", protect=protect, unprotect=unprotect)


def test_missing_or_disabled_config_starts_no_service(tmp_path):
    store = make_store(tmp_path)
    agent = SimpleNamespace(respond_text=lambda *_a, **_k: "ok")
    assert start_configured_service(agent, tmp_path, store=store, service_factory=FakeService) is None
    config_path = tmp_path / CONFIG_RELATIVE_PATH
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"enabled": False}), encoding="utf-8")
    assert start_configured_service(agent, tmp_path, store=store, service_factory=FakeService) is None


def test_opt_in_config_starts_only_loopback_with_paired_chat_scope(tmp_path):
    store = make_store(tmp_path)
    grant = store.pair("phone", {"chat", "status.read"})
    config_path = tmp_path / CONFIG_RELATIVE_PATH
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"enabled": True, "client_id": grant.client_id, "port": 17840}), encoding="utf-8")
    agent = SimpleNamespace(respond_text=lambda message, **_kw: f"Alice: {message}")
    captured = []

    def factory(dispatcher, **kwargs):
        service = FakeService(dispatcher, **kwargs)
        captured.append(service)
        return service

    controller = start_configured_service(agent, tmp_path, store=store, service_factory=factory, version="5.0-dev")
    assert controller is not None
    assert captured[0].host == "127.0.0.1"
    assert captured[0].started is True
    assert captured[0].dispatcher._handlers["alice.chat"]({"message": "hello"}) == {"text": "Alice: hello"}
    status = captured[0].dispatcher._handlers["alice.status.read"]({})
    assert status == {"version": "5.0-dev", "state": "ready"}
    controller.shutdown()
    controller.shutdown()
    assert captured[0].stopped is True


def test_enabled_config_without_existing_pair_fails_closed(tmp_path):
    store = make_store(tmp_path)
    config_path = tmp_path / CONFIG_RELATIVE_PATH
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"enabled": True, "client_id": "missing", "port": 17840}), encoding="utf-8")
    with pytest.raises(KeyError):
        start_configured_service(SimpleNamespace(respond_text=lambda *_a, **_k: "ok"), tmp_path,
                                 store=store, service_factory=FakeService)


def test_enabled_config_without_client_starts_health_only_listener(tmp_path):
    config_path = write_config(tmp_path, enabled=True, port=17840)
    assert json.loads(config_path.read_text(encoding="utf-8")) == {"enabled": True, "port": 17840}
    assert read_config(tmp_path) == {"enabled": True, "client_id": None, "port": 17840}
    captured = []

    def factory(dispatcher, **kwargs):
        service = FakeService(dispatcher, **kwargs)
        captured.append(service)
        return service

    controller = start_configured_service(SimpleNamespace(), tmp_path, service_factory=factory)
    assert controller is not None
    assert controller.client_id is None
    assert captured[0].dispatcher is None
    assert captured[0].host == "127.0.0.1"
    assert captured[0].started is True
    controller.shutdown()


def test_config_rejects_non_loopback_or_invalid_port_controls(tmp_path):
    config_path = tmp_path / CONFIG_RELATIVE_PATH
    config_path.parent.mkdir(parents=True)
    config_path.write_text(json.dumps({"enabled": True, "client_id": "phone", "host": "0.0.0.0", "port": 80}), encoding="utf-8")
    with pytest.raises(ValueError, match="port"):
        read_config(tmp_path)


def test_config_write_is_opt_in_and_contains_no_pairing_secret(tmp_path):
    path = write_config(tmp_path, enabled=True, client_id="client-123", port=17840)
    assert read_config(tmp_path) == {"enabled": True, "client_id": "client-123", "port": 17840}
    assert "secret" not in path.read_text(encoding="utf-8").lower()
    write_config(tmp_path, enabled=False)
    assert read_config(tmp_path) == {"enabled": False}
