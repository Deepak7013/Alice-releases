import json
import importlib.util
from pathlib import Path
import sys

import pytest

from alice.deployment.updater import InPlaceUpdater, UpgradeError
from alice.capabilities.manager import CapabilityManager, STATUS_UNVERIFIED
from alice.agent.executor import Executor
from alice.execution.postconditions import PostconditionRegistry, PostconditionResult
from alice.gluttony.assimilation import AssimilationEngine
from alice.gluttony.evolver import DevourEngine, DevourError
from alice.gluttony.review import DevourReviewStore
from alice.maintenance.self_manager import SelfManager
from alice.security.ingest_guard import IngestGuard
from alice.tools.registry import ToolRegistry


class FakeRouter:
    def __init__(self, payloads):
        self.payloads = list(payloads)

    def ask(self, prompt, image_path=None):
        return self.payloads.pop(0)


def _report(root):
    acquired = root / "alice_workspace" / "gluttony" / "devour" / "job_test" / "source"
    acquired.mkdir(parents=True)
    (acquired / "candidate.py").write_text("def candidate():\n    return 1\n", encoding="utf-8")
    guard = IngestGuard()
    return {
        "status": "digested",
        "source": "https://github.com/example/project",
        "source_label": "example/project",
        "quarantine": str(acquired.parent),
        "acquired_source": str(acquired),
        "tree_sha256": guard.digest_tree(acquired),
        "acquisition": {"method": "archive"},
        "license": {"kind": "MIT", "files": ["LICENSE"]},
        "security": guard.scan_tree(acquired),
        "capability_candidates": [{"name": "terminal_agent"}],
        "policy": {
            "executed_external_code": False,
            "activated_external_code": False,
            "native_reimplementation_required": True,
        },
    }


def _approve_report(root,report,*capabilities):
    base=root/"alice_workspace"/"gluttony"/"devour"
    base.mkdir(parents=True,exist_ok=True)
    path=base/"DIGEST_test.json"
    path.write_text(json.dumps(report,indent=2,ensure_ascii=False)+"\n",encoding="utf-8")
    review=DevourReviewStore(root)
    for name in capabilities or ("terminal_agent",):
        review.approve_capability(path,name,confirmed=True)
    return path


def _setup(tmp_path, implementation):
    root = tmp_path / "alice_app"
    (root / "alice" / "tests").mkdir(parents=True)
    (root / "alice" / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "alice" / "tests" / "test_feature.py").write_text(
        "def test_terminal_behavior():\n    assert True\n", encoding="utf-8",
    )
    (root / "VERSION.txt").write_text("ALICE v4.104.0\n", encoding="utf-8")
    selection = json.dumps({
        "reason": "implement terminal behavior natively",
        "files": ["alice/feature.py", "alice/tests/test_feature.py"],
        "capabilities": ["terminal_agent"],
    })
    sm = SelfManager(root, router=FakeRouter([selection, implementation]))
    sm._stage_test_with_candidate_tests = lambda stage, candidate_tests=(): type("Result", (), {
        "returncode": 0, "stdout": "5 passed", "stderr": "",
        "candidate_test_paths": list(candidate_tests),
        "candidate_test_summary": "1 passed",
        "candidate_test_sandbox_evidence": None,
    })()
    return root, sm, _report(root)


def test_devour_upgrade_package_records_provenance_and_rollback_evidence(tmp_path):
    implementation = json.dumps({
        "reason": "native implementation",
        "runtime_entry_points": {"terminal_agent": "alice.feature:run_terminal_agent"},
        "changes": [
            {"path": "alice/feature.py", "content": "VALUE = 2\ndef run_terminal_agent():\n    return {'ok': True}\n"},
            {"path": "alice/tests/test_feature.py", "content": "def test_terminal_behavior():\n    assert True\n"},
        ],
    })
    root, sm, report = _setup(tmp_path, implementation)
    capabilities = CapabilityManager(root)
    sm.capability_manager = capabilities

    reviewed=_approve_report(root,report)
    result = sm.prepare_devour_upgrade("implement terminal behavior", reviewed, repair_attempts=0)

    assert result["ok"] is True
    assert result["status"] == "tested_candidate_pending_isolation"
    assert result["promotion_eligible"] is False
    assert (root / "alice" / "feature.py").read_text(encoding="utf-8") == "VALUE = 1\n"
    manifest = InPlaceUpdater(root).validate_package(result["package"]["package"])["manifest"]
    provenance = manifest["provenance"]
    assert provenance["devour"]["tree_sha256"] == report["tree_sha256"]
    assert provenance["devour"]["license"] == {
        "kind": "MIT", "files": ["LICENSE"], "review_required": False,
    }
    assert provenance["devour"]["security"]["review_required"] is False
    assert provenance["verification"]["test_suite"] == "passed"
    assert provenance["verification"]["candidate_tests"]["paths"] == ["alice/tests/test_feature.py"]
    assert provenance["verification"]["candidate_tests"]["summary"] == "1 passed"
    assert "sandbox evidence unavailable" in provenance["verification"]["execution_isolation"]
    assert provenance["promotion"]["promoted"] is False
    assert provenance["promotion"]["eligible"] is False
    assert provenance["promotion"]["blocked_until_os_sandbox"] is True
    assert provenance["rollback"]["required_before_activation"] is True
    assert provenance["user_approval"]["per_capability"] is True
    assert provenance["user_approval"]["approvals"][0]["capability"]=="terminal_agent"
    assert provenance["declared_entry_points"] == {"terminal_agent": "alice.feature:run_terminal_agent"}
    registry=capabilities.get("terminal_agent")
    assert registry["status"]==STATUS_UNVERIFIED and registry["verified"] is False
    assert registry["configured"] is False and capabilities.can_claim("terminal_agent") is False
    evidence=registry["acquisition_evidence"][0]
    assert evidence["status"]=="tested_candidate_pending_isolation"
    assert evidence["report_sha256"]==provenance["user_approval"]["report_sha256"]
    assert evidence["tree_sha256"]==report["tree_sha256"]
    assert evidence["candidate_sha256"]==result["package"]["sha256"]
    assert evidence["candidate_tests"]["paths"]==["alice/tests/test_feature.py"]
    assert evidence["sandbox"]["verified"] is False


def test_devour_upgrade_records_verified_container_isolation(tmp_path):
    implementation = json.dumps({
        "reason": "native implementation",
        "runtime_entry_points": {"terminal_agent": "alice.feature:run_terminal_agent"},
        "changes": [
            {"path": "alice/feature.py", "content": "VALUE = 2\ndef run_terminal_agent():\n    return {'ok': True}\n"},
            {"path": "alice/tests/test_feature.py", "content": "def test_terminal_behavior():\n    assert True\n"},
        ],
    })
    root, sm, report = _setup(tmp_path, implementation)
    capabilities = CapabilityManager(root)
    sm.capability_manager = capabilities
    sandbox = {
        "verified": True,
        "backend": "docker",
        "image": "alice-devour-candidate:py314",
        "image_id": "sha256:" + "a" * 64,
        "checks": {"network_disabled": True, "only_candidate_bind_mount": True},
    }

    class IsolatedPass:
        returncode = 0
        stdout = "8 passed"
        stderr = ""
        sandbox_evidence = sandbox
        candidate_test_paths = ["alice/tests/test_feature.py"]
        candidate_test_summary = "1 passed"
        candidate_test_sandbox_evidence = sandbox

    sm._stage_test_with_candidate_tests = lambda stage, candidate_tests=(): IsolatedPass()
    reviewed=_approve_report(root,report)
    result = sm.prepare_devour_upgrade("implement terminal behavior", reviewed, repair_attempts=0)

    assert result["status"] == "tested_candidate_isolated_pending_review"
    manifest = InPlaceUpdater(root).validate_package(result["package"]["package"])["manifest"]
    provenance = manifest["provenance"]
    assert provenance["verification"]["sandbox"]["verified"] is True
    assert provenance["verification"]["sandbox"]["image_id"] == sandbox["image_id"]
    assert provenance["verification"]["candidate_tests"]["sandbox"]["verified"] is True
    assert provenance["promotion"]["blocked_until_os_sandbox"] is False
    assert provenance["promotion"]["eligible"] is False
    receipt=result["capability_evidence"][0]
    assert receipt["recorded"] is True and receipt["active"] is False and receipt["verified"] is False
    assert CapabilityManager(root).get("terminal_agent")["acquisition_evidence"][0]["entry_point"] == "alice.feature:run_terminal_agent"
    registry=CapabilityManager(root).get("terminal_agent")
    assert registry["verified"] is False and registry["status"]==STATUS_UNVERIFIED
    assert registry["acquisition_evidence"][0]["status"]=="tested_candidate_isolated_pending_review"
    assert registry["acquisition_evidence"][0]["sandbox"]["image_id"]==sandbox["image_id"]


def test_devour_candidate_entrypoint_survives_build_install_and_runtime_verification(tmp_path):
    implementation = json.dumps({
        "reason": "bind the reviewed capability to an ALICE-owned runtime tool",
        "runtime_entry_points": {"terminal_agent": "alice.feature:run_terminal_agent"},
        "changes": [
            {"path": "alice/feature.py",
             "content": "VALUE = 2\ndef run_terminal_agent():\n    return {'ok': True}\n"},
            {"path": "alice/tests/test_feature.py",
             "content": "from alice.feature import run_terminal_agent\n\ndef test_terminal_agent_candidate():\n    assert run_terminal_agent()['ok'] is True\n"},
        ],
    })
    root, sm, report = _setup(tmp_path, implementation)
    python_stub = root / ".venv" / "Scripts" / "python.exe"
    python_stub.parent.mkdir(parents=True)
    python_stub.write_bytes(b"test-only updater install marker")
    manager = CapabilityManager(root)
    sm.capability_manager = manager
    sandbox = {
        "verified": True, "backend": "docker", "image": "alice-devour-candidate:py314",
        "image_id": "sha256:" + "f" * 64,
        "checks": {"network_disabled": True, "only_candidate_bind_mount": True},
    }

    class IsolatedPass:
        returncode = 0
        stdout = "2 passed"
        stderr = ""
        sandbox_evidence = sandbox
        candidate_test_paths = ["alice/tests/test_feature.py"]
        candidate_test_summary = "1 passed"
        candidate_test_sandbox_evidence = sandbox

    sm._stage_test_with_candidate_tests = lambda stage, candidate_tests=(): IsolatedPass()
    reviewed = _approve_report(root, report)
    candidate = sm.prepare_devour_upgrade(
        "implement terminal agent", reviewed, repair_attempts=0)
    assert candidate["status"] == "tested_candidate_isolated_pending_review"

    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: type("Result", (), {
        "returncode": 0, "stdout": "installed suite passed", "stderr": "",
    })()
    installed = updater.apply(candidate["package"]["package"])
    assert installed["ok"] is True
    receipt = CapabilityManager(root).get("terminal_agent")["acquisition_evidence"][0]
    assert receipt["entry_point"] == "alice.feature:run_terminal_agent"
    assert receipt["installation"]["status"] == "installed_pending_runtime_verification"

    spec = importlib.util.spec_from_file_location("alice.feature", root / "alice" / "feature.py")
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules["alice.feature"] = module
    spec.loader.exec_module(module)
    try:
        tools = ToolRegistry(capability_manager=CapabilityManager(root))
        tools.add("terminal_agent", "Run terminal agent", module.run_terminal_agent, "execute")
        tools.postconditions = PostconditionRegistry()
        tools.postconditions.register(
            "terminal_agent",
            lambda _args, _result: PostconditionResult(True, {"observed": True, "state_matches": True}),
        )
        executor = Executor(tools, capabilities=tools.capability_manager)
        executor.permissions.needs_confirmation = lambda _name, _args: False
        result = executor.run({"steps": [{"tool": "terminal_agent", "args": {}}]})[0]
        assert result["status"] == "verified"
        assert tools.capability_manager.can_claim("terminal_agent") is True
    finally:
        sys.modules.pop("alice.feature", None)


def test_devour_upgrade_rejects_changes_outside_selected_native_scope(tmp_path):
    implementation = json.dumps({
        "reason": "out of scope",
        "changes": [{"path": "alice/other.py", "content": "VALUE = 2\n"}],
    })
    root, sm, report = _setup(tmp_path, implementation)

    reviewed=_approve_report(root,report)
    with pytest.raises(RuntimeError, match="outside the selected native implementation scope"):
        sm.prepare_devour_upgrade("implement terminal behavior", reviewed, repair_attempts=0)

    assert not list((root / "alice_workspace" / "updates").glob("*.zip"))
    assert (root / "alice" / "feature.py").read_text(encoding="utf-8") == "VALUE = 1\n"


def test_devour_candidate_must_change_a_focused_test_for_its_capability(tmp_path):
    implementation = json.dumps({
        "reason": "no behavior test",
        "changes": [{"path": "alice/feature.py", "content": "VALUE = 2\n"}],
    })
    root, sm, report = _setup(tmp_path, implementation)

    reviewed=_approve_report(root,report)
    with pytest.raises(RuntimeError, match="must add or update a selected.*regression test"):
        sm.prepare_devour_upgrade("implement terminal behavior", reviewed, repair_attempts=0)

    assert not list((root / "alice_workspace" / "updates").glob("*.zip"))


def test_devour_candidate_requires_entry_point_in_changed_alice_source(tmp_path):
    implementation = json.dumps({
        "reason": "missing runtime binding",
        "changes": [
            {"path": "alice/feature.py", "content": "VALUE = 2\n"},
            {"path": "alice/tests/test_feature.py", "content": "def test_terminal_behavior():\n    assert True\n"},
        ],
    })
    root, sm, report = _setup(tmp_path, implementation)

    reviewed = _approve_report(root, report)
    with pytest.raises(RuntimeError, match="runtime_entry_points"):
        sm.prepare_devour_upgrade("implement terminal behavior", reviewed, repair_attempts=0)

    assert not list((root / "alice_workspace" / "updates").glob("*.zip"))
    assert (root / "alice" / "feature.py").read_text(encoding="utf-8") == "VALUE = 1\n"


@pytest.mark.parametrize(("entry", "source", "message"), [
    ("alice.other:run", "def run():\n    return True\n", "source must be included"),
    ("alice.feature:missing", "def run():\n    return True\n", "must name a changed synchronous"),
    ("alice.feature:run", "async def run():\n    return True\n", "must name a changed synchronous"),
])
def test_devour_entrypoint_must_be_a_changed_synchronous_module_function(entry, source, message):
    changes = [
        {"path": "alice/feature.py", "content": source},
        {"path": "alice/tests/test_feature.py", "content": "def test_feature():\n    assert True\n"},
    ]
    with pytest.raises(ValueError, match=message):
        SelfManager._validate_devour_entry_points({"terminal_agent": entry}, ["terminal_agent"], changes)


def test_devour_architect_must_select_a_focused_test(tmp_path):
    root, sm, report = _setup(tmp_path, "not used")
    sm.router.payloads[0] = json.dumps({
        "reason": "missing test selection",
        "files": ["alice/feature.py"],
        "capabilities": ["terminal_agent"],
    })

    reviewed=_approve_report(root,report)
    with pytest.raises(ValueError, match="must include a focused.*regression test"):
        sm.prepare_devour_upgrade("implement terminal behavior", reviewed)


@pytest.mark.parametrize("field,value", [
    ("tree_sha256", "not-a-digest"),
    ("policy", {"executed_external_code": True, "activated_external_code": False,
                 "native_reimplementation_required": True}),
])
def test_devour_upgrade_rejects_unverifiable_quarantine_provenance(tmp_path, field, value):
    root, sm, report = _setup(tmp_path, "not used")
    report[field] = value

    with pytest.raises(ValueError, match="DEVOUR"):
        reviewed=_approve_report(root,report)
        sm.prepare_devour_upgrade("implement terminal behavior", reviewed)


def test_devour_upgrade_rejects_quarantine_source_changed_after_analysis(tmp_path):
    root, sm, report = _setup(tmp_path, "not used")
    reviewed=_approve_report(root,report)
    (Path(report["acquired_source"]) / "candidate.py").write_text("changed = True\n", encoding="utf-8")

    with pytest.raises(ValueError, match="no longer matches"):
        sm.prepare_devour_upgrade("implement terminal behavior", reviewed)


def test_multi_source_approval_builds_native_candidate_with_composite_provenance(tmp_path):
    implementation = json.dumps({
        "reason": "native implementation from individually reviewed aggregate evidence",
        "changes": [
            {"path": "alice/feature.py", "content": "VALUE = 2\ndef run_candidate():\n    return {'ok': True}\n"},
            {"path": "alice/tests/test_feature.py",
             "content": "def test_terminal_behavior():\n    assert True\n"},
        ],
    })
    root, sm, _single_report = _setup(tmp_path, implementation)
    source_a=tmp_path/"review_source_a"; source_a.mkdir()
    source_b=tmp_path/"review_source_b"; source_b.mkdir()
    for source, body in ((source_a,"# planner agent tool orchestration\n"),
                         (source_b,"# planner agent stream orchestration\n")):
        (source/"LICENSE.txt").write_text("MIT License\n",encoding="utf-8")
        (source/"agent.py").write_text(body,encoding="utf-8")
    report=DevourEngine(root,self_manager=object()).devour_many([str(source_a),str(source_b)])["report"]
    review=DevourReviewStore(root)
    state=review.inspect(report)
    capability=state["capabilities"][0]["name"]
    selection=json.dumps({"reason":"native only","files":["alice/feature.py","alice/tests/test_feature.py"],
        "capabilities":[capability]})
    implementation_obj=json.loads(implementation)
    implementation_obj["runtime_entry_points"]={capability:"alice.feature:run_candidate"}
    implementation=json.dumps(implementation_obj)
    sm.router.payloads=[selection,implementation]
    manager=CapabilityManager(root); sm.capability_manager=manager
    review.approve_capability(report,capability,confirmed=True,decision="integrate_behind_alice_interface")

    result=sm.prepare_devour_upgrade("implement the selected capability",report,repair_attempts=0,
        approved_capabilities=[capability])

    assert result["ok"] is True
    manifest=InPlaceUpdater(root).validate_package(result["package"]["package"])["manifest"]
    provenance=manifest["provenance"]["devour"]
    assert len(provenance["source_tree_sha256s"])==2
    assert provenance["tree_sha256"]==state["tree_sha256"]
    assert provenance["external_code_executed"] is False
    assert manifest["provenance"]["user_approval"]["tree_sha256"]==state["tree_sha256"]
    assert manifest["provenance"]["user_approval"]["approvals"][0]["capability"]==capability
    assert manifest["provenance"]["user_approval"]["decisions"][capability]=="integrate_behind_alice_interface"
    assert manager.get(capability)["acquisition_evidence"][0]["tree_sha256"]==state["tree_sha256"]
    assert manager.get(capability)["acquisition_evidence"][0]["approval_decision"]=="integrate_behind_alice_interface"


def test_reuse_existing_component_decision_does_not_build_an_unneeded_candidate(tmp_path):
    root,sm,report=_setup(tmp_path,"not used")
    report["alice_capability_assessment"]={"capabilities":[{"name":"terminal_agent",
        "status":"partial","recommendation":"improve_native_capability"}]}
    reviewed=_approve_report(root,report)
    DevourReviewStore(root).approve_capability(reviewed,"terminal_agent",confirmed=True,
        decision="reuse_compatible_component")

    with pytest.raises(ValueError,match="does not require or permit a new candidate"):
        sm.prepare_devour_upgrade("reuse the existing ALICE component",reviewed,repair_attempts=0)

    assert not list((root/"alice_workspace"/"updates").glob("*.zip"))


def test_candidate_stage_omits_private_state_and_scrubs_test_environment(tmp_path, monkeypatch):
    root = tmp_path / "alice_app"
    (root / "alice" / "tests").mkdir(parents=True)
    (root / "alice" / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "alice" / "tests" / "test_feature.py").write_text(
        "def test_terminal_behavior():\n    assert True\n", encoding="utf-8",
    )
    (root / "alice_workspace" / "runtime").mkdir(parents=True)
    (root / "alice_workspace" / "runtime" / "memory.json").write_text("private state")
    (root / ".venv").mkdir()
    (root / ".venv" / "marker").write_text("local environment")
    (root / ".env").write_text("ALICE_API_KEY=private")
    (root / ".env.example").write_text("ALICE_API_KEY=replace-me")
    (root / "releases").mkdir()
    (root / "releases" / "old.zip").write_bytes(b"release")
    (root / "VERSION.txt").write_text("ALICE v4.104.0\n", encoding="utf-8")
    sm = SelfManager(root)
    stage = sm._copy_tree_for_stage()
    assert (stage / "alice" / "feature.py").is_file()
    assert not (stage / ".env").exists()
    assert (stage / ".env.example").is_file()
    assert not (stage / "alice_workspace").exists()
    assert not (stage / ".venv").exists()
    assert not (stage / "releases").exists()

    monkeypatch.setenv("ALICE_API_KEY", "must-not-reach-candidate-tests")
    monkeypatch.setenv("OPENAI_API_KEY", "must-not-reach-candidate-tests")
    observed = {}

    class FakeCandidateRunner:
        def run_tests(self, candidate, *, timeout, test_paths=None):
            observed.update(candidate=candidate, timeout=timeout, test_paths=test_paths)
            return type("Result", (), {"returncode": 0, "stdout": "ok", "stderr": ""})()

    sm.candidate_runner = FakeCandidateRunner()
    result = sm.run_tests(cwd=stage)

    assert result.returncode == 0
    assert observed["candidate"] == stage.resolve()
    assert observed["timeout"] == sm.TEST_TIMEOUT + 60


def test_devour_intake_to_verified_candidate_package_uses_live_quarantine_digest(tmp_path):
    root = tmp_path / "alice_app"
    (root / "alice").mkdir(parents=True)
    (root / "alice" / "feature.py").write_text("VALUE = 1\n", encoding="utf-8")
    (root / "VERSION.txt").write_text("ALICE v4.104.0\n", encoding="utf-8")
    candidate = tmp_path / "public-project"
    candidate.mkdir()
    (candidate / "agent.py").write_text(
        'def run():\n    return "terminal shell command"\n', encoding="utf-8",
    )
    engine = DevourEngine(root, AssimilationEngine(root))

    with pytest.raises(DevourError,match="approve capabilities individually"):
        engine.devour(str(candidate),goal="implement the discovered terminal behavior",
                      auto_upgrade=True,approval_token="USER_APPROVED_DEVOUR_UPGRADE")

    assert not list((root / "alice_workspace" / "updates").glob("*.zip"))

