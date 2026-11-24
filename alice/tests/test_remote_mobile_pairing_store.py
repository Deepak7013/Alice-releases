import base64
import os

import pytest

from alice.remote.pairing_store import DPAPIPairingStore, DPAPIProtector


def _test_protect(data):
    return b"test-envelope:" + data


def _test_unprotect(data):
    if not data.startswith(b"test-envelope:"):
        raise ValueError("bad test envelope")
    return data[len(b"test-envelope:"):]


def test_pairing_store_persists_keys_only_inside_protected_blob_and_revoke(tmp_path):
    path = tmp_path / "clients.dpapi"
    store = DPAPIPairingStore(path, protect=_test_protect, unprotect=_test_unprotect)
    grant = store.pair("  Luca phone  ", {"chat", "status.read"})

    raw_file = path.read_bytes()
    decoded_secret = base64.urlsafe_b64decode(grant.secret_for_pairing + "=" * (-len(grant.secret_for_pairing) % 4))
    assert decoded_secret not in raw_file
    assert grant.secret_for_pairing not in repr(grant)

    credential = store.credential(grant.client_id)
    assert credential.client.label == "Luca phone"
    assert credential.client.scopes == frozenset({"chat", "status.read"})
    assert credential.secret == decoded_secret
    assert store.revoke(grant.client_id) is True
    assert store.revoke(grant.client_id) is False
    assert store.clients() == ()


def test_pairing_store_fails_closed_on_plaintext_or_unsupported_scope(tmp_path):
    path = tmp_path / "clients.dpapi"
    path.write_text('{"schema":1,"clients":[]}', encoding="utf-8")
    store = DPAPIPairingStore(path, protect=_test_protect, unprotect=_test_unprotect)
    with pytest.raises(ValueError, match="format"):
        store.clients()
    path.unlink()
    with pytest.raises(ValueError, match="unsupported"):
        store.pair("phone", {"shell.exec"})
    assert not path.exists()


def test_pairing_store_allows_only_one_active_client_in_this_build(tmp_path):
    store = DPAPIPairingStore(tmp_path / "clients.dpapi", protect=_test_protect, unprotect=_test_unprotect)
    store.pair("phone 1", {"chat"})
    with pytest.raises(ValueError, match="maximum paired-client count"):
        store.pair("phone 2", {"chat"})


def test_explicit_pairing_replacement_can_roll_back_protected_snapshot(tmp_path):
    store = DPAPIPairingStore(tmp_path / "clients.dpapi", protect=_test_protect, unprotect=_test_unprotect)
    original = store.pair("phone", {"chat", "status.read"})
    snapshot = store.snapshot()
    replacement = store.pair("phone", {"chat", "status.read", "email.read"}, replace_existing=True)
    assert replacement.client_id != original.client_id
    assert store.clients()[0].scopes == frozenset({"chat", "status.read", "email.read"})
    store.restore_snapshot(snapshot)
    assert store.clients()[0].client_id == original.client_id
    assert store.credential(original.client_id).secret


@pytest.mark.skipif(os.name != "nt", reason="Windows user-scope DPAPI is only available on Windows")
def test_windows_dpapi_round_trip_is_user_protected():
    clear = os.urandom(48)
    protected = DPAPIProtector.protect(clear)
    assert protected != clear
    assert DPAPIProtector.unprotect(protected) == clear


def test_default_path_uses_local_appdata(monkeypatch, tmp_path):
    from alice.remote.pairing_store import default_pairing_store_path

    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    assert default_pairing_store_path() == tmp_path / "ALICE" / "remote" / "paired_clients.dpapi"

