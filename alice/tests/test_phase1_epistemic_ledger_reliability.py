import json
import math
from concurrent.futures import ThreadPoolExecutor

import pytest

from alice.memory_context.epistemic import EpistemicLedger, EpistemicStatus


def test_corrupt_ledger_fails_closed_without_overwriting_original(tmp_path):
    path = tmp_path / "alice_workspace" / "epistemic_ledger.json"
    path.parent.mkdir(parents=True)
    original = '{"broken": {"status": "made-up"}}'
    path.write_text(original, encoding="utf-8")

    with pytest.raises(ValueError, match="Cannot safely load epistemic ledger"):
        EpistemicLedger(tmp_path)

    assert path.read_text(encoding="utf-8") == original


@pytest.mark.parametrize("confidence", [True, float("nan"), float("inf"), -0.1, 1.1, "0.5"])
def test_add_rejects_invalid_confidence(tmp_path, confidence):
    ledger = EpistemicLedger(tmp_path)
    with pytest.raises(ValueError):
        ledger.add("a claim", confidence=confidence)


def test_add_requires_superseded_record_to_exist(tmp_path):
    ledger = EpistemicLedger(tmp_path)
    with pytest.raises(KeyError):
        ledger.add("new claim", supersedes="missing")
    assert ledger.current() == []


def test_failed_save_does_not_mutate_in_memory_state(tmp_path, monkeypatch):
    ledger = EpistemicLedger(tmp_path)
    original_save = ledger._save

    def fail(*args, **kwargs):
        raise OSError("disk full")

    monkeypatch.setattr(ledger, "_save", fail)
    with pytest.raises(OSError, match="disk full"):
        ledger.add("claim")
    assert ledger.current() == []
    monkeypatch.setattr(ledger, "_save", original_save)
    assert ledger.add("claim")["status"] == EpistemicStatus.ASSERTED.value


def test_concurrent_adds_on_one_ledger_preserve_every_record(tmp_path):
    ledger = EpistemicLedger(tmp_path)
    with ThreadPoolExecutor(max_workers=12) as pool:
        rows = list(pool.map(lambda i: ledger.add(f"claim {i}", source="parallel-test"), range(80)))
    assert len({row["record_id"] for row in rows}) == 80
    reopened = EpistemicLedger(tmp_path)
    assert len(reopened.current()) == 80


def test_ledger_rejects_non_string_claim_and_evidence(tmp_path):
    ledger = EpistemicLedger(tmp_path)
    with pytest.raises(ValueError):
        ledger.add(42)
    with pytest.raises(ValueError):
        ledger.add("claim", evidence=["ok", 3])
