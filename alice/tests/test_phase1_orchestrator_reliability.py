import json
import subprocess
import sys
import time
from pathlib import Path

import pytest

from alice.agents.orchestrator import MultiAgentOrchestrator
from alice.agents.worker import WorkerResult, WorkerSpec


class Router:
    def __init__(self, response='{"summary":"merged"}'):
        self.response = response

    def ask(self, _prompt):
        return self.response


class Tools:
    tools = {}


def spec(name):
    return WorkerSpec(name=name, role="researcher", objective=f"task for {name}")



def test_orchestrator_rejects_invalid_worker_limits_and_duplicate_names(tmp_path):
    with pytest.raises(ValueError, match="max_workers"):
        MultiAgentOrchestrator(Router(), Tools(), tmp_path, max_workers=0)
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)
    with pytest.raises(ValueError, match="unique"):
        orchestrator.run("objective", [spec("same"), spec("same")])


def test_worker_exception_is_recorded_and_checkpoint_is_still_written(tmp_path, monkeypatch):
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)

    class BrokenWorker:
        def __init__(self, *_args):
            pass

        def run(self, _context):
            raise RuntimeError("worker crashed")

    monkeypatch.setattr("alice.agents.orchestrator.SpecialistWorker", BrokenWorker)
    result = orchestrator.run("objective", [spec("broken")])

    assert result["ok"] is False
    assert result["workers"][0]["status"] == "failed"
    assert "RuntimeError" in result["workers"][0]["error"]
    checkpoint = json.loads((tmp_path / "alice_workspace/workers/last_orchestration.json").read_text())
    assert checkpoint["workers"][0]["status"] == "failed"


def test_checkpoint_is_atomic_json_and_cleanup_preserves_checkpoint(tmp_path):
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)
    worker_dir = orchestrator.worker_root / "worker-a"
    worker_dir.mkdir()
    (worker_dir / "artifact.txt").write_text("temporary")
    checkpoint = orchestrator.worker_root / "last_orchestration.json"
    orchestrator._write_checkpoint({"ok": True, "summary": "durable"})

    assert json.loads(checkpoint.read_text())["summary"] == "durable"
    assert orchestrator.dispose([WorkerResult("id", "worker-a", "researcher", "completed", "x")]) == []
    assert not worker_dir.exists()
    assert checkpoint.exists()


def test_invalid_merge_response_is_explicitly_marked():
    orchestrator = MultiAgentOrchestrator(Router("not json"), Tools())
    merged = orchestrator.merge("objective", [])
    assert merged["summary"] == "Worker reports collected without model merge."
    assert merged["merge_error"] == "InvalidMergeResponse"


def test_verification_disabled_cannot_report_success(tmp_path, monkeypatch):
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)

    class GoodWorker:
        def __init__(self, _router, _tools, worker_spec):
            self.spec = worker_spec

        def run(self, _context):
            return WorkerResult("id", self.spec.name, self.spec.role, "completed", self.spec.objective, summary="done")

    monkeypatch.setattr("alice.agents.orchestrator.SpecialistWorker", GoodWorker)
    result = orchestrator.run("objective", [spec("worker")], verify=False)
    assert result["ok"] is False
    assert result["verification"]["reason"] == "verification disabled"

@pytest.mark.parametrize("unsafe_name", ["../escape", "nested/worker", "last_orchestration.json", "", "bad name", "a" * 65])
def test_orchestrator_rejects_unsafe_worker_names_before_creating_directories(tmp_path, unsafe_name):
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)
    with pytest.raises(ValueError, match="Worker name"):
        orchestrator.run("objective", [spec(unsafe_name)])
    assert {item.name for item in orchestrator.worker_root.iterdir()} <= {".orchestrator.lock"}


def test_orchestrator_rejects_unhashable_worker_name_as_validation_error(tmp_path):
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)
    malformed = spec("safe")
    malformed.name = ["not", "a", "name"]
    with pytest.raises(ValueError, match="Worker name"):
        orchestrator.run("objective", [malformed])


def test_orchestrator_rejects_symlinked_worker_directory(tmp_path):
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)
    outside = tmp_path / "outside"
    outside.mkdir()
    link = orchestrator.worker_root / "worker-link"
    try:
        link.symlink_to(outside, target_is_directory=True)
    except (OSError, NotImplementedError):
        pytest.skip("directory symlinks are unavailable on this platform")
    with pytest.raises(ValueError, match="symbolic link"):
        orchestrator.run("objective", [spec("worker-link")])
    assert outside.exists()


@pytest.mark.parametrize("field,value", [
    ("max_steps", True), ("max_steps", 101),
    ("timeout_seconds", True), ("timeout_seconds", float("nan")),
    ("timeout_seconds", 86401), ("risk", "root"),
])
def test_orchestrator_validates_worker_execution_bounds(tmp_path, field, value):
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)
    worker_spec = spec("bounded")
    setattr(worker_spec, field, value)
    with pytest.raises((ValueError, TypeError)):
        orchestrator.run("objective", [worker_spec])
    assert {item.name for item in orchestrator.worker_root.iterdir()} <= {".orchestrator.lock"}


def test_workspace_lock_serializes_orchestrators_sharing_worker_root(tmp_path):
    import threading
    import time

    first = MultiAgentOrchestrator(Router(), Tools(), tmp_path)
    second = MultiAgentOrchestrator(Router(), Tools(), tmp_path)
    first_inside = threading.Event()
    release_first = threading.Event()
    second_inside = threading.Event()

    def hold_first():
        with first._workspace_lock():
            first_inside.set()
            assert release_first.wait(2)

    def enter_second():
        with second._workspace_lock():
            second_inside.set()

    t1 = threading.Thread(target=hold_first)
    t2 = threading.Thread(target=enter_second)
    t1.start()
    assert first_inside.wait(1)
    t2.start()
    try:
        time.sleep(0.1)
        assert not second_inside.is_set()
    finally:
        release_first.set()
        t1.join(2)
        t2.join(2)
    assert not t1.is_alive()
    assert not t2.is_alive()
    assert second_inside.is_set()
    assert (first.worker_root / ".orchestrator.lock").is_file()


def test_workspace_lock_serializes_independent_processes_and_recovers_after_termination(tmp_path):
    # Independent Python processes exercise kernel-level locks, not just threads.
    root = str(Path(__file__).resolve().parents[2])
    acquired_first = tmp_path / "first.acquired"
    acquired_second = tmp_path / "second.acquired"
    script = (
        "import pathlib, sys, time\n"
        "from alice.agents.orchestrator import MultiAgentOrchestrator\n"
        "class R: pass\n"
        "class T: tools = {}\n"
        "o = MultiAgentOrchestrator(R(), T(), sys.argv[1])\n"
        "with o._workspace_lock():\n"
        " pathlib.Path(sys.argv[2]).write_text('locked')\n"
        " time.sleep(float(sys.argv[3]))\n"
    )
    env = dict(__import__("os").environ)
    env["PYTHONPATH"] = root + __import__("os").pathsep + env.get("PYTHONPATH", "")
    first = subprocess.Popen([sys.executable, "-c", script, str(tmp_path), str(acquired_first), "60"], cwd=root, env=env)
    second = None
    try:
        deadline = time.monotonic() + 8
        while not acquired_first.exists() and time.monotonic() < deadline and first.poll() is None:
            time.sleep(0.02)
        assert acquired_first.exists(), "first process did not acquire workspace lock"
        second = subprocess.Popen([sys.executable, "-c", script, str(tmp_path), str(acquired_second), "0"], cwd=root, env=env)
        time.sleep(0.35)
        assert not acquired_second.exists(), "second process entered while first held workspace lock"

        # Kernel-managed advisory locks are released when the owner is killed.
        first.terminate()
        first.wait(timeout=5)
        deadline = time.monotonic() + 8
        while not acquired_second.exists() and time.monotonic() < deadline and second.poll() is None:
            time.sleep(0.02)
        assert acquired_second.exists(), "second process did not acquire lock after owner termination"
        assert second.wait(timeout=5) == 0
    finally:
        if first.poll() is None:
            first.kill()
            first.wait(timeout=5)
        if second is not None and second.poll() is None:
            second.kill()
            second.wait(timeout=5)


def test_workspace_lock_has_a_bounded_wait(tmp_path):
    import threading
    import time

    holder = MultiAgentOrchestrator(Router(), Tools(), tmp_path)
    waiter = MultiAgentOrchestrator(Router(), Tools(), tmp_path, workspace_lock_timeout=0.12)
    entered = threading.Event()
    release = threading.Event()

    def hold():
        with holder._workspace_lock():
            entered.set()
            release.wait(2)

    thread = threading.Thread(target=hold)
    thread.start()
    assert entered.wait(1)
    started = time.monotonic()
    try:
        with pytest.raises(TimeoutError, match="workspace lock"):
            with waiter._workspace_lock():
                pytest.fail("lock unexpectedly acquired")
        assert time.monotonic() - started < 1.0
    finally:
        release.set()
        thread.join(2)
    assert not thread.is_alive()


@pytest.mark.parametrize("timeout", [True, 0, -1, float("inf"), float("nan"), 86401, "1"])
def test_workspace_lock_timeout_configuration_is_validated(tmp_path, timeout):
    with pytest.raises(ValueError, match="workspace_lock_timeout"):
        MultiAgentOrchestrator(Router(), Tools(), tmp_path, workspace_lock_timeout=timeout)

@pytest.mark.parametrize("response,expected", [
    ('[]', "JSON object"),
    ('{"summary": 7, "steps": []}', "summary"),
    ('{"summary": "x", "steps": [], "artifacts": [7]}', "artifacts"),
    ('{"summary": "x", "steps": [], "artifacts": ["a"]}', None),
])
def test_specialist_worker_validates_model_plan_shape(response, expected):
    from alice.agents.worker import SpecialistWorker

    class PlanningRouter:
        def ask(self, _prompt):
            return response

    worker = SpecialistWorker(PlanningRouter(), Tools(), spec("plan-check"))
    result = worker.run("small context")
    if expected is None:
        assert result.status == "completed"
        assert result.artifacts == ["a"]
    else:
        assert result.status == "failed"
        assert expected in result.error


def test_specialist_worker_rejects_oversized_context_before_model_call():
    from alice.agents.worker import SpecialistWorker

    class NeverCalledRouter:
        def ask(self, _prompt):
            raise AssertionError("model must not be called for oversized context")

    worker = SpecialistWorker(NeverCalledRouter(), Tools(), spec("context-check"))
    result = worker.run("x" * (worker.MAX_CONTEXT_CHARS + 1))
    assert result.status == "failed"
    assert "context exceeds" in result.error


def test_specialist_worker_rejects_oversized_model_response():
    from alice.agents.worker import SpecialistWorker

    class LargeRouter:
        def ask(self, _prompt):
            return "x" * (SpecialistWorker.MAX_MODEL_RESPONSE_CHARS + 1)

    result = SpecialistWorker(LargeRouter(), Tools(), spec("response-check")).run()
    assert result.status == "failed"
    assert "1 MB safety limit" in result.error


def test_specialist_worker_rejects_non_object_tool_arguments_before_executor():
    from alice.agents.worker import SpecialistWorker

    class PlanningRouter:
        def ask(self, _prompt):
            return '{"summary":"x","steps":[{"tool":"read","args":[]}]}'

    worker_spec = WorkerSpec("args-check", "researcher", "task", allowed_tools=["read"])
    worker = SpecialistWorker(PlanningRouter(), Tools(), worker_spec)
    result = worker.run()
    assert result.status == "failed"
    assert "args must be a JSON object" in result.error


def test_orchestrator_rejects_worker_result_identity_spoofing(tmp_path, monkeypatch):
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)

    class SpoofedWorker:
        def __init__(self, *_args):
            pass

        def run(self, _context):
            return WorkerResult("id", "different-worker", "researcher", "completed", "task", summary="spoof")

    monkeypatch.setattr("alice.agents.orchestrator.SpecialistWorker", SpoofedWorker)
    result = orchestrator.run("objective", [spec("assigned-worker")])
    assert result["ok"] is False
    assert result["workers"][0]["name"] == "assigned-worker"
    assert result["workers"][0]["status"] == "failed"
    assert "identity does not match" in result["workers"][0]["error"]


def test_orchestrator_rejects_oversized_worker_result_contract(tmp_path, monkeypatch):
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)

    class OversizedWorker:
        def __init__(self, *_args):
            pass

        def run(self, _context):
            assigned = spec("oversized")
            return WorkerResult("id", assigned.name, assigned.role, "completed", assigned.objective, artifacts=["x" * 1025])

    monkeypatch.setattr("alice.agents.orchestrator.SpecialistWorker", OversizedWorker)
    result = orchestrator.run("objective", [spec("oversized")])
    assert result["ok"] is False
    assert result["workers"][0]["status"] == "failed"
    assert "result contract" in result["workers"][0]["error"]


@pytest.mark.parametrize("response,expected", [
    ('{"summary":"x","steps":[7]}', "step must be an object"),
    ('{"summary":"x","steps":[],"artifacts":[" "]}', "artifacts"),
    ('{"summary":"x","steps":[],"artifacts":["x" * 1025]}', "artifacts"),
    ('{"summary":"x" * 4001,"steps":[]}', "summary"),
])
def test_specialist_worker_rejects_invalid_plan_fields(response, expected):
    from alice.agents.worker import SpecialistWorker

    class PlanningRouter:
        def ask(self, _prompt):
            # Evaluate simple test expressions without relying on Python repr parsing.
            if '"x" * 1025' in response:
                return '{"summary":"x","steps":[],"artifacts":["' + ('x' * 1025) + '"]}'
            if '"x" * 4001' in response:
                return '{"summary":"' + ('x' * 4001) + '","steps":[]}'
            return response

    result = SpecialistWorker(PlanningRouter(), Tools(), spec("invalid-fields")).run()
    assert result.status == "failed"
    assert expected in result.error


def test_specialist_worker_rejects_oversized_tool_arguments():
    from alice.agents.worker import SpecialistWorker

    class PlanningRouter:
        def ask(self, _prompt):
            payload = "x" * 66000
            return json.dumps({"summary": "x", "steps": [{"tool": "read", "args": {"value": payload}}]})

    worker_spec = WorkerSpec("large-args", "researcher", "task", allowed_tools=["read"])
    result = SpecialistWorker(PlanningRouter(), Tools(), worker_spec).run()
    assert result.status == "failed"
    assert "64 KB safety limit" in result.error


def test_specialist_worker_rejects_non_text_model_response():
    from alice.agents.worker import SpecialistWorker

    class NonTextRouter:
        def ask(self, _prompt):
            return {"summary": "not serialized"}

    result = SpecialistWorker(NonTextRouter(), Tools(), spec("non-text")).run()
    assert result.status == "failed"
    assert "must return text" in result.error


def test_windows_workspace_lock_branch_acquires_and_releases_with_msvcrt(tmp_path, monkeypatch):
    import sys
    import types
    import alice.agents.orchestrator as orchestrator_module

    calls = []
    fake_msvcrt = types.SimpleNamespace(LK_NBLCK=1, LK_UNLCK=2)

    def fake_locking(_fd, mode, count):
        calls.append((mode, count))

    fake_msvcrt.locking = fake_locking
    monkeypatch.setitem(sys.modules, "msvcrt", fake_msvcrt)
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)
    # Exercise the Windows-specific branch under Linux without claiming native
    # Windows behavior; the real msvcrt implementation still needs Windows CI.
    monkeypatch.setattr(orchestrator_module.os, "name", "nt")
    with orchestrator._workspace_lock():
        assert calls == [(fake_msvcrt.LK_NBLCK, 1)]
    assert calls == [(fake_msvcrt.LK_NBLCK, 1), (fake_msvcrt.LK_UNLCK, 1)]

@pytest.mark.parametrize("objective,context,match", [
    ("x" * 12001, "", "objective exceeds"),
    ("objective", "x" * 50001, "context exceeds"),
])
def test_orchestrator_bounds_top_level_objective_and_context(tmp_path, objective, context, match):
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)
    with pytest.raises(ValueError, match=match):
        orchestrator.run(objective, [spec("bounded-input")], context=context)
    assert not (orchestrator.worker_root / "bounded-input").exists()


def test_orchestrator_rejects_more_than_32_workers_before_directory_creation(tmp_path):
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)
    specs = [spec(f"worker-{index}") for index in range(33)]
    with pytest.raises(ValueError, match="At most 32 workers"):
        orchestrator.run("objective", specs)
    assert not any(path.is_dir() for path in orchestrator.worker_root.iterdir())


@pytest.mark.parametrize("response,error", [
    ("not json", "ValueError"),
    ('{"summary":7}', "ValueError"),
    ('{"summary":"ok","agreements":[7]}', "ValueError"),
    (json.dumps({"summary": "ok", "conflicts": ["y" * 1001]}), "ValueError"),
    ("x" * (MultiAgentOrchestrator.MAX_MERGE_RESPONSE_CHARS + 1), "ValueError"),
])
def test_merge_rejects_invalid_or_oversized_model_responses(response, error):
    orchestrator = MultiAgentOrchestrator(Router(response), Tools())
    merged = orchestrator.merge("objective", [])
    assert merged["summary"] == "Worker reports collected without model merge."
    assert merged["merge_error"] == ("InvalidMergeResponse" if response == "not json" else error)


def test_merge_discards_unrecognized_model_fields():
    orchestrator = MultiAgentOrchestrator(
        Router('{"summary":"ok","agreements":["a"],"surprise":"must not persist"}'), Tools()
    )
    merged = orchestrator.merge("objective", [])
    assert merged == {"summary": "ok", "agreements": ["a"], "conflicts": [], "next_actions": []}


def test_orchestrator_rejects_non_finite_worker_tool_evidence(tmp_path, monkeypatch):
    orchestrator = MultiAgentOrchestrator(Router(), Tools(), tmp_path)

    class NonFiniteWorker:
        def __init__(self, *_args):
            pass

        def run(self, _context):
            assigned = spec("non-finite")
            return WorkerResult("id", assigned.name, assigned.role, "completed", assigned.objective,
                                summary="done", tool_results=[{"tool": "x", "result": float("nan")}])

    monkeypatch.setattr("alice.agents.orchestrator.SpecialistWorker", NonFiniteWorker)
    result = orchestrator.run("objective", [spec("non-finite")])
    assert result["ok"] is False
    assert result["workers"][0]["status"] == "failed"
    assert "finite JSON" in result["workers"][0]["error"]
