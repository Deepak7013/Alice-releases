import json
import pytest
from alice.execution.receipt_journal import ReceiptJournal, ReceiptJournalError


def receipt(action_id="a1", **extra):
    return {"action_id": action_id, "tool": "desktop.click", "admitted": True,
            "execution_ok": True, "verified": False, "outcome": "attempted", **extra}


def test_append_and_reload_hash_chained_receipts(tmp_path):
    path = tmp_path / "receipts.jsonl"
    journal = ReceiptJournal(path)
    journal.append(receipt())
    journal.append(receipt("a2", outcome="verified", verified=True))
    assert [row["action_id"] for row in ReceiptJournal(path).list()] == ["a1", "a2"]


def test_duplicate_action_id_is_rejected_without_appending(tmp_path):
    journal = ReceiptJournal(tmp_path / "receipts.jsonl")
    journal.append(receipt())
    with pytest.raises(ValueError, match="duplicate action_id"):
        journal.append(receipt())
    assert len(journal.list()) == 1


def test_torn_final_record_is_ignored_and_next_append_repairs_tail(tmp_path):
    path = tmp_path / "receipts.jsonl"
    journal = ReceiptJournal(path)
    journal.append(receipt())
    with path.open("ab") as stream:
        stream.write(b'{"receipt":')
    assert [row["action_id"] for row in journal.list()] == ["a1"]
    # A subsequent append must not leave the torn bytes embedded in a record.
    journal.append(receipt("a2"))
    assert [row["action_id"] for row in journal.list()] == ["a1", "a2"]


def test_interior_tampering_is_reported(tmp_path):
    path = tmp_path / "receipts.jsonl"
    journal = ReceiptJournal(path)
    journal.append(receipt())
    journal.append(receipt("a2"))
    lines = path.read_text().splitlines()
    first = json.loads(lines[0]); first["receipt"]["outcome"] = "forged"
    lines[0] = json.dumps(first)
    path.write_text("\n".join(lines) + "\n")
    with pytest.raises(ReceiptJournalError, match="corruption"):
        journal.list()


def test_non_json_receipt_is_rejected_before_write(tmp_path):
    path = tmp_path / "receipts.jsonl"
    journal = ReceiptJournal(path)
    with pytest.raises((TypeError, ValueError)):
        journal.append(receipt(metadata=object()))
    assert not path.exists()


def test_executor_persists_receipt_for_executed_tool(tmp_path):
    from alice.agent.executor import Executor
    from alice.tools.registry import ToolRegistry

    calls = []
    tools = ToolRegistry()
    tools.add("read_value", "Read a value", lambda: calls.append("read") or {"value": 7}, "read")
    journal = ReceiptJournal(tmp_path / "executor.jsonl")
    executor = Executor(tools, receipt_journal=journal)
    executor.permissions.needs_confirmation = lambda *_: False

    result = executor.run({"steps": [{"tool": "read_value", "args": {}}]})

    assert result[0]["status"] == "observed"
    assert calls == ["read"]
    persisted = journal.list()
    assert len(persisted) == 1
    assert persisted[0]["tool"] == "read_value"
    assert persisted[0]["admitted"] is True
    assert persisted[0]["execution_ok"] is True


def test_executor_reports_journal_failure_without_hiding_tool_outcome():
    from alice.agent.executor import Executor
    from alice.tools.registry import ToolRegistry

    class BrokenJournal:
        def append(self, _receipt):
            raise OSError("disk unavailable")

    tools = ToolRegistry()
    tools.add("read_value", "Read a value", lambda: {"value": 7}, "read")
    executor = Executor(tools, receipt_journal=BrokenJournal())
    executor.permissions.needs_confirmation = lambda *_: False
    result = executor.run({"steps": [{"tool": "read_value", "args": {}}]})
    assert result[0]["status"] == "observed"
    assert "disk unavailable" in result[0]["receipt_persistence_error"]


def test_executor_prevents_replay_of_action_id_before_tool_side_effect(tmp_path):
    from alice.agent.executor import Executor
    from alice.tools.registry import ToolRegistry

    calls = []
    tools = ToolRegistry()
    tools.add("write_value", "Write a value", lambda: calls.append("write") or {"ok": True}, "write")
    journal = ReceiptJournal(tmp_path / "executor.jsonl")
    executor = Executor(tools, receipt_journal=journal)
    executor.permissions.needs_confirmation = lambda *_: False

    plan = {"steps": [{"tool": "write_value", "args": {}, "action_id": "stable-action-42"}]}
    first = executor.run(plan)
    second = executor.run(plan)

    assert first[0]["status"] == "attempted"
    assert second[0]["status"] == "duplicate_prevented"
    assert calls == ["write"]
    assert len(journal.list()) == 1


def test_executor_fails_closed_if_action_history_cannot_be_read():
    from alice.agent.executor import Executor
    from alice.tools.registry import ToolRegistry

    class UnreadableJournal:
        def list(self):
            raise OSError("journal unavailable")
        def append(self, _receipt):
            raise AssertionError("must not attempt append")

    calls = []
    tools = ToolRegistry()
    tools.add("write_value", "Write a value", lambda: calls.append("write"), "write")
    executor = Executor(tools, receipt_journal=UnreadableJournal())
    executor.permissions.needs_confirmation = lambda *_: False
    result = executor.run({"steps": [{"tool": "write_value", "args": {}, "action_id": "action-x"}]})
    assert result[0]["error_class"] == "ReceiptJournalUnavailable"
    assert calls == []



def test_complete_malformed_final_line_is_corruption_not_torn_tail(tmp_path):
    path = tmp_path / "receipts.jsonl"
    journal = ReceiptJournal(path)
    journal.append(receipt())
    with path.open("ab") as stream:
        stream.write(b'{"broken": true}\n')
    with pytest.raises(ReceiptJournalError, match="corruption"):
        journal.list()


def test_unterminated_malformed_final_line_remains_recoverable(tmp_path):
    path = tmp_path / "receipts.jsonl"
    journal = ReceiptJournal(path)
    journal.append(receipt())
    with path.open("ab") as stream:
        stream.write(b'{"broken":')
    assert [row["action_id"] for row in journal.list()] == ["a1"]


def test_record_size_limit_rejects_oversized_payload_before_write(tmp_path):
    path = tmp_path / "receipts.jsonl"
    journal = ReceiptJournal(path, max_record_bytes=256)
    with pytest.raises(ValueError, match="size limit"):
        journal.append(receipt(metadata="x" * 400))
    assert not path.exists()


def test_record_size_limit_is_validated_at_construction(tmp_path):
    with pytest.raises(ValueError, match="max_record_bytes"):
        ReceiptJournal(tmp_path / "receipts.jsonl", max_record_bytes=True)
    with pytest.raises(ValueError, match="max_record_bytes"):
        ReceiptJournal(tmp_path / "receipts.jsonl", max_record_bytes=0)


def test_journal_rejects_unexpected_envelope_fields(tmp_path):
    path = tmp_path / "receipts.jsonl"
    journal = ReceiptJournal(path)
    journal.append(receipt())
    envelope = json.loads(path.read_text().splitlines()[0])
    envelope["untrusted_extra"] = "ignored?"
    path.write_text(json.dumps(envelope) + "\n")
    with pytest.raises(ReceiptJournalError, match="corruption"):
        journal.list()


def test_durable_action_claim_is_exclusive_across_journal_instances(tmp_path):
    path = tmp_path / "claims.jsonl"
    first = ReceiptJournal(path)
    second = ReceiptJournal(path)
    assert first.claim_action("stable-1", "desktop.click") is True
    assert second.claim_action("stable-1", "desktop.click") is False
    assert second.get_action_claim("stable-1")["tool"] == "desktop.click"


def test_action_claim_survives_journal_reconstruction(tmp_path):
    path = tmp_path / "claims.jsonl"
    assert ReceiptJournal(path).claim_action("stable-2", "file.write") is True
    reopened = ReceiptJournal(path)
    assert reopened.get_action_claim("stable-2")["action_id"] == "stable-2"
    assert reopened.claim_action("stable-2", "file.write") is False


def test_concurrent_executor_calls_cannot_both_start_same_action(tmp_path):
    import threading
    import time
    from alice.agent.executor import Executor
    from alice.tools.registry import ToolRegistry

    calls = []
    calls_lock = threading.Lock()
    tools = ToolRegistry()
    def write_once():
        time.sleep(0.05)
        with calls_lock:
            calls.append("called")
        return {"ok": True}
    tools.add("write_value", "Write a value", write_once, "write")
    journal = ReceiptJournal(tmp_path / "concurrent.jsonl")
    executors = [Executor(tools, receipt_journal=ReceiptJournal(journal.path)) for _ in range(2)]
    for executor in executors:
        executor.permissions.needs_confirmation = lambda *_: False
    barrier = threading.Barrier(2)
    results = [None, None]
    def run(index):
        barrier.wait()
        results[index] = executors[index].run({"steps": [{"tool": "write_value", "args": {}, "action_id": "same-action"}]})
    threads = [threading.Thread(target=run, args=(i,)) for i in range(2)]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=3)
    assert all(not thread.is_alive() for thread in threads)
    assert len(calls) == 1
    statuses = sorted(result[0]["status"] for result in results)
    assert statuses == ["attempted", "duplicate_prevented"]


def test_denied_action_does_not_create_durable_claim(tmp_path):
    from alice.agent.executor import Executor
    from alice.tools.registry import ToolRegistry

    tools = ToolRegistry()
    tools.add("write_value", "Write a value", lambda: {"ok": True}, "write")
    journal = ReceiptJournal(tmp_path / "denied.jsonl")
    executor = Executor(tools, receipt_journal=journal)
    executor.permissions.needs_confirmation = lambda *_: True
    executor.permissions.request = lambda *_: False
    result = executor.run({"steps": [{"tool": "write_value", "args": {}, "action_id": "denied-action"}]})
    assert result[0]["status"] == "denied"
    assert journal.get_action_claim("denied-action") is None


def test_concurrent_distinct_appends_from_journal_instances_are_not_lost(tmp_path):
    import threading
    path = tmp_path / "parallel-appends.jsonl"
    journals = [ReceiptJournal(path) for _ in range(8)]
    barrier = threading.Barrier(len(journals))
    errors = []
    def append(index):
        try:
            barrier.wait()
            journals[index].append(receipt(f"parallel-{index}"))
        except Exception as exc:
            errors.append(exc)
    threads = [threading.Thread(target=append, args=(i,)) for i in range(len(journals))]
    for thread in threads: thread.start()
    for thread in threads: thread.join(timeout=5)
    assert all(not thread.is_alive() for thread in threads)
    assert errors == []
    assert {row["action_id"] for row in ReceiptJournal(path).list()} == {f"parallel-{i}" for i in range(8)}


def test_corrupt_action_claim_fails_closed(tmp_path):
    path = tmp_path / "claims.jsonl"
    journal = ReceiptJournal(path)
    token = __import__("hashlib").sha256(b"broken-claim").hexdigest()
    (journal.claims_path / f"{token}.json").write_text("{broken", encoding="utf-8")
    with pytest.raises(ReceiptJournalError, match="claim is corrupt"):
        journal.get_action_claim("broken-claim")



def test_action_claim_rejects_unexpected_fields(tmp_path):
    import hashlib
    path = tmp_path / "claims.jsonl"
    journal = ReceiptJournal(path)
    journal.claim_action("strict-claim", "desktop.click")
    token = hashlib.sha256(b"strict-claim").hexdigest()
    claim_path = journal.claims_path / f"{token}.json"
    payload = json.loads(claim_path.read_text(encoding="utf-8"))
    payload["unexpected"] = True
    claim_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReceiptJournalError, match="claim is corrupt"):
        journal.get_action_claim("strict-claim")


@pytest.mark.parametrize("claimed_at", [True, float("nan"), float("inf"), 0, -1, "now"])
def test_action_claim_rejects_invalid_timestamps(tmp_path, claimed_at):
    import hashlib
    path = tmp_path / "claims.jsonl"
    journal = ReceiptJournal(path)
    journal.claim_action("timestamp-claim", "desktop.click")
    token = hashlib.sha256(b"timestamp-claim").hexdigest()
    claim_path = journal.claims_path / f"{token}.json"
    payload = json.loads(claim_path.read_text(encoding="utf-8"))
    payload["claimed_at"] = claimed_at
    claim_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReceiptJournalError, match="claim is corrupt"):
        journal.get_action_claim("timestamp-claim")


def test_action_claim_rejects_blank_tool_name_on_read(tmp_path):
    import hashlib
    path = tmp_path / "claims.jsonl"
    journal = ReceiptJournal(path)
    journal.claim_action("blank-tool", "desktop.click")
    token = hashlib.sha256(b"blank-tool").hexdigest()
    claim_path = journal.claims_path / f"{token}.json"
    payload = json.loads(claim_path.read_text(encoding="utf-8"))
    payload["tool"] = " "
    claim_path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(ReceiptJournalError, match="claim is corrupt"):
        journal.get_action_claim("blank-tool")


@pytest.mark.parametrize("mutation", [
    {"admitted": "false"},
    {"execution_ok": 1},
    {"verified": None},
    {"action_id": 123},
    {"unexpected": "field"},
    {"evidence": "x" * 4097},
])
def test_journal_rejects_malformed_receipt_before_touching_disk(tmp_path, mutation):
    journal = ReceiptJournal(tmp_path / "strict.jsonl")
    payload = receipt()
    payload.update(mutation)
    with pytest.raises(ValueError):
        journal.append(payload)
    assert not journal.path.exists()


def test_journal_rejects_semantically_invalid_hashed_receipt_on_read(tmp_path):
    import hashlib
    path = tmp_path / "forged.jsonl"
    payload = receipt()
    payload["verified"] = True
    payload["execution_ok"] = False
    canonical = ReceiptJournal._canonical(payload)
    digest = hashlib.sha256(("0" * 64).encode("ascii") + canonical).hexdigest()
    envelope = {"previous_hash": "0" * 64, "receipt": payload, "record_hash": digest}
    path.write_bytes(ReceiptJournal._canonical(envelope) + b"\n")
    with pytest.raises(ReceiptJournalError, match="corruption"):
        ReceiptJournal(path).list()


def test_executor_receipt_records_postcondition_digest_without_raw_evidence(tmp_path):
    import hashlib
    from alice.agent.executor import Executor
    from alice.tools.registry import ToolRegistry

    class Check:
        ok = True
        reason = "target state observed"
        evidence = {"path": "C:/Users/example/private.txt", "exists": True}

    class Postconditions:
        def has(self, _name):
            return True
        def verify(self, _name, _args, _out):
            return Check()

    tools = ToolRegistry()
    tools.add("write_value", "Write a value", lambda: {"ok": True}, "write")
    journal = ReceiptJournal(tmp_path / "evidence.jsonl")
    executor = Executor(tools, postconditions=Postconditions(), receipt_journal=journal)
    executor.permissions.needs_confirmation = lambda *_: False

    result = executor.run({"steps": [{"tool": "write_value", "args": {}, "action_id": "evidence-action"}]})
    persisted = journal.list()[0]
    expected = hashlib.sha256(
        b'{"exists":true,"path":"C:/Users/example/private.txt"}'
    ).hexdigest()

    assert result[0]["status"] == "verified"
    assert "target state observed" in persisted["evidence"]
    assert expected in persisted["evidence"]
    assert "private.txt" not in persisted["evidence"]


def test_executor_receipt_keeps_failure_class_and_error_summary(tmp_path):
    from alice.agent.executor import Executor
    from alice.tools.registry import ToolRegistry

    tools = ToolRegistry()
    def fail():
        raise RuntimeError("controlled failure")
    tools.add("write_value", "Write a value", fail, "write")
    journal = ReceiptJournal(tmp_path / "failure.jsonl")
    executor = Executor(tools, receipt_journal=journal)
    executor.permissions.needs_confirmation = lambda *_: False

    result = executor.run({"steps": [{"tool": "write_value", "args": {}, "action_id": "failed-action"}]})
    persisted = journal.list()[0]
    assert result[0]["status"] == "error"
    assert "controlled failure" in persisted["evidence"]
    assert "error_class=RuntimeError" in persisted["evidence"]
