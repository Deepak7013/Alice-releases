import hashlib
import importlib.util
import json
import sys
import zipfile
from pathlib import Path
from types import SimpleNamespace

from alice.agent.executor import Executor
from alice.capabilities.manager import CapabilityManager, STATUS_UNVERIFIED
from alice.deployment.updater import InPlaceUpdater, build_manifest
from alice.execution.postconditions import PostconditionRegistry, PostconditionResult
from alice.tools.registry import ToolRegistry


_ENTRY_POINT = "alice.adapters.terminal_agent:run_terminal_agent"


def _installed_adapter(root, name="run_terminal_agent"):
    path = Path(root) / "alice" / "adapters" / "terminal_agent.py"
    module_name = "alice.adapters.terminal_agent"
    spec = importlib.util.spec_from_file_location(module_name, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return getattr(module, name)


def _candidate_package(tmp_path, *, record_receipt=True, manifest_entry_point=_ENTRY_POINT,
                       receipt_entry_point=_ENTRY_POINT):
    root = tmp_path / "install"
    (root / "alice" / "tests").mkdir(parents=True)
    (root / "alice" / "adapters").mkdir(parents=True)
    (root / ".venv" / "Scripts").mkdir(parents=True)
    (root / "VERSION.txt").write_text("ALICE v4.105.0\n", encoding="utf-8")
    (root / "alice" / "feature.py").write_text("VALUE = 'old'\n", encoding="utf-8")
    (root / "alice" / "adapters" / "terminal_agent.py").write_text(
        "def run_terminal_agent():\n    return {'ok': True, 'adapter': 'old'}\n"
        "\ndef run_other_terminal_agent():\n    return {'ok': True, 'adapter': 'other'}\n",
        encoding="utf-8",
    )
    (root / ".venv" / "Scripts" / "python.exe").write_text("test placeholder", encoding="utf-8")

    payload = tmp_path / "payload"
    (payload / "alice" / "tests").mkdir(parents=True)
    (payload / "alice" / "adapters").mkdir(parents=True)
    (payload / "VERSION.txt").write_text("ALICE v4.106.0\n", encoding="utf-8")
    (payload / "alice" / "feature.py").write_text("VALUE = 'candidate'\n", encoding="utf-8")
    (payload / "alice" / "adapters" / "terminal_agent.py").write_text(
        "def run_terminal_agent():\n    return {'ok': True, 'adapter': 'approved'}\n"
        "\ndef run_other_terminal_agent():\n    return {'ok': True, 'adapter': 'other'}\n",
        encoding="utf-8",
    )
    (payload / "alice" / "tests" / "test_terminal_agent.py").write_text(
        "def test_terminal_agent_candidate():\n    assert True\n", encoding="utf-8",
    )
    manifest = build_manifest(payload, "ALICE v4.106.0", "ALICE v4.105.0")
    manifest["minimum_version"] = "ALICE v4.105.0"
    manifest["self_generated"] = True
    manifest["provenance"] = {
        "kind": "devour_native_reimplementation",
        "selected_capabilities": ["terminal_agent"],
        "user_approval": {
            "per_capability": True,
            "report_sha256": "b" * 64,
            "tree_sha256": "c" * 64,
            "approvals": [{"capability": "terminal_agent", "candidate_sha256": "d" * 64}],
        },
        "verification": {"sandbox": {"verified": True}},
        "promotion": {"eligible": False, "blocked_until_os_sandbox": False},
        "trusted_adapter_entrypoints": {"terminal_agent": _ENTRY_POINT},
        "declared_entry_points": {"terminal_agent": manifest_entry_point},
    }
    (payload / "upgrade_manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
    package = tmp_path / "candidate.zip"
    with zipfile.ZipFile(package, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(payload.rglob("*")):
            if path.is_file():
                archive.write(path, path.relative_to(payload).as_posix())
    package_sha = hashlib.sha256(package.read_bytes()).hexdigest()

    registry = CapabilityManager(root)
    if record_receipt:
        registry.record_devour_candidate(
            "terminal_agent", candidate_version="ALICE v4.106.0",
            candidate_sha256=package_sha, report_sha256="b" * 64,
            tree_sha256="c" * 64, capability_candidate_sha256="d" * 64,
            candidate_status="tested_candidate_isolated_pending_review",
            test_paths=["alice/tests/test_terminal_agent.py"], test_summary="1 passed",
            sandbox={"verified": True, "backend": "docker", "image_id": "sha256:" + "e" * 64},
            approval_method="explicit_per_capability_ui_confirmation",
            entry_point=receipt_entry_point,
        )
    return root, package, package_sha, registry


def test_devour_install_records_pending_state_then_runtime_postcondition_verifies(tmp_path):
    root, package, package_sha, registry = _candidate_package(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock full suite passed", stderr="")

    installed = updater.apply(package)

    assert installed["ok"] is True and installed["rolled_back"] is False
    assert installed["candidate_lifecycle"] == [{
        "name": "terminal_agent", "recorded": True, "active": False,
        "verified": False, "status": "installed_pending_runtime_verification",
        "candidate_sha256": package_sha,
    }]
    registry = CapabilityManager(root)
    pending = registry.get("terminal_agent")
    assert pending["status"] == STATUS_UNVERIFIED
    assert pending["configured"] is False and pending["verified"] is False
    assert pending["acquisition_evidence"][0]["installation"]["status"] == "installed_pending_runtime_verification"
    assert registry.can_claim("terminal_agent") is False

    # Simulate the installed app's next launch and one independently observed action.
    registry = CapabilityManager(root)
    tools = ToolRegistry(capability_manager=registry)
    tools.add("terminal_agent", "Run a terminal task", _installed_adapter(root), "write")
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register(
        "terminal_agent",
        lambda _args, _result: PostconditionResult(True, {"observed": True, "state_matches": True}),
    )
    executor = Executor(tools, capabilities=registry)
    executor.permissions.needs_confirmation = lambda _name, _args: False
    result = executor.run({"steps": [{"tool": "terminal_agent", "args": {}}]})[0]

    assert result["status"] == "verified"
    assert registry.can_claim("terminal_agent") is True
    runtime = registry.get("terminal_agent")["acquisition_evidence"][0]["installation"]
    assert runtime["status"] == "runtime_verified"
    assert runtime["runtime_verification"]["status"] == "independently_verified"
    assert len(runtime["runtime_verification"]["postcondition_evidence_sha256"]) == 64
    assert runtime["runtime_verification"]["callable_provenance"]["source_path"] == "alice/adapters/terminal_agent.py"
    assert runtime["runtime_verification"]["callable_provenance"]["module"] == "alice.adapters.terminal_agent"
    assert "alice.feature" not in sys.modules


def test_devour_install_requires_matching_current_isolated_registry_receipt(tmp_path):
    root, package, _package_sha, _registry = _candidate_package(tmp_path, record_receipt=False)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock pass", stderr="")

    try:
        updater.apply(package)
    except Exception as exc:
        assert "isolated candidate receipt" in str(exc)
    else:
        raise AssertionError("DEVOUR package must be blocked without its current capability receipt")

    assert (root / "VERSION.txt").read_text(encoding="utf-8").strip() == "ALICE v4.105.0"
    assert not list((root / ".alice_backups").glob("inplace_*"))


def test_devour_install_rejects_package_entrypoint_mismatch_before_backup_or_mutation(tmp_path):
    root, package, _package_sha, _registry = _candidate_package(
        tmp_path, manifest_entry_point="alice.adapters.terminal_agent:run_other_terminal_agent")
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock pass", stderr="")

    try:
        updater.apply(package)
    except Exception as exc:
        assert "entry point" in str(exc).lower()
    else:
        raise AssertionError("Package and isolated registry entry points must match before install")

    assert (root / "VERSION.txt").read_text(encoding="utf-8").strip() == "ALICE v4.105.0"
    assert not list((root / ".alice_backups").glob("inplace_*"))


def test_failed_candidate_package_suite_rolls_back_without_install_receipt(tmp_path):
    root, package, _package_sha, _registry = _candidate_package(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=1, stdout="1 failed", stderr="candidate suite failed")

    result = updater.apply(package)

    assert result["ok"] is False and result["rolled_back"] is True
    assert (root / "VERSION.txt").read_text(encoding="utf-8").strip() == "ALICE v4.105.0"
    stored = CapabilityManager(root).get("terminal_agent")
    assert stored["status"] == STATUS_UNVERIFIED and stored["verified"] is False
    assert "installation" not in stored["acquisition_evidence"][0]


def test_devour_candidate_cannot_be_promoted_by_same_named_tool_before_installation(tmp_path):
    root, _package, _package_sha, registry = _candidate_package(tmp_path)
    registry.record_success(
        "terminal_agent", note="generic runtime tool observed",
        evidence_sha256="a" * 64, observer="terminal_agent",
    )
    stored = CapabilityManager(root).get("terminal_agent")
    assert stored["status"] == STATUS_UNVERIFIED
    assert stored["verified"] is False
    assert stored["configured"] is False
    assert "no matching installed DEVOUR candidate" in stored["verification_note"]


def test_devour_candidate_runtime_verification_requires_exact_installed_version(tmp_path):
    root, package, _package_sha, registry = _candidate_package(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock full suite passed", stderr="")
    installed = updater.apply(package)
    assert installed["ok"] is True

    # Simulate the runtime version changing back or pointing at a different install.
    (root / "VERSION.txt").write_text("ALICE v4.105.0\n", encoding="utf-8")
    registry = CapabilityManager(root)
    registry.record_success(
        "terminal_agent", note="wrong install runtime observed",
        evidence_sha256="b" * 64, observer="terminal_agent",
    )
    stored = registry.get("terminal_agent")
    assert stored["status"] == STATUS_UNVERIFIED
    assert stored["verified"] is False
    installation = stored["acquisition_evidence"][0]["installation"]
    assert installation["status"] == "installed_pending_runtime_verification"
    assert "runtime_verification" not in installation


def test_devour_candidate_runtime_verification_requires_matching_capability_observer(tmp_path):
    root, package, _package_sha, registry = _candidate_package(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock full suite passed", stderr="")
    assert updater.apply(package)["ok"] is True
    registry = CapabilityManager(root)
    registry.record_success(
        "terminal_agent", note="different observer observed success",
        evidence_sha256="c" * 64, observer="other_tool",
    )
    stored = registry.get("terminal_agent")
    assert stored["status"] == STATUS_UNVERIFIED
    assert stored["verified"] is False
    assert stored["acquisition_evidence"][0]["installation"]["status"] == "installed_pending_runtime_verification"


def test_devour_candidate_runtime_verification_rejects_modified_installed_artifact(tmp_path):
    root, package, _package_sha, registry = _candidate_package(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock full suite passed", stderr="")
    assert updater.apply(package)["ok"] is True

    # Version.txt and the capability name alone are insufficient: an installed
    # file from the candidate must still match the install-time manifest digest.
    feature = root / "alice" / "feature.py"
    feature.write_text("VALUE = 'modified after installation'\n", encoding="utf-8")
    registry = CapabilityManager(root)
    registry.record_success(
        "terminal_agent", note="tool returned success",
        evidence_sha256="f" * 64, observer="terminal_agent",
    )
    stored = registry.get("terminal_agent")
    assert stored["status"] == STATUS_UNVERIFIED
    assert stored["verified"] is False
    assert stored["configured"] is False
    installation = stored["acquisition_evidence"][0]["installation"]
    assert installation["status"] == "installed_pending_runtime_verification"
    assert "runtime_verification" not in installation


def test_devour_candidate_runtime_verification_rejects_missing_installed_artifact_after_restart(tmp_path):
    root, package, _package_sha, _registry = _candidate_package(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock full suite passed", stderr="")
    assert updater.apply(package)["ok"] is True

    # Reconstructing the manager models a process restart; deleting an expected
    # candidate artifact must not be mistaken for a successful runtime install.
    (root / "alice" / "feature.py").unlink()
    registry = CapabilityManager(root)
    registry.record_success(
        "terminal_agent", note="success after restart with missing artifact",
        evidence_sha256="1" * 64, observer="terminal_agent",
    )
    stored = registry.get("terminal_agent")
    assert stored["status"] == STATUS_UNVERIFIED
    assert stored["verified"] is False and stored["configured"] is False
    installation = stored["acquisition_evidence"][0]["installation"]
    assert installation["status"] == "installed_pending_runtime_verification"
    assert "runtime_verification" not in installation


def test_devour_candidate_runtime_verification_rejects_artifact_symlink_escape(tmp_path):
    root, package, _package_sha, _registry = _candidate_package(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock full suite passed", stderr="")
    assert updater.apply(package)["ok"] is True

    outside = tmp_path / "outside.py"
    outside.write_text("VALUE = 'candidate'\n", encoding="utf-8")
    feature = root / "alice" / "feature.py"
    feature.unlink()
    try:
        feature.symlink_to(outside)
    except (OSError, NotImplementedError):
        # Symlinks can be unavailable in restricted Windows environments; this
        # fixture runs on platforms where the operation is supported.
        return

    registry = CapabilityManager(root)
    registry.record_success(
        "terminal_agent", note="success through outside symlink",
        evidence_sha256="2" * 64, observer="terminal_agent",
    )
    stored = registry.get("terminal_agent")
    assert stored["status"] == STATUS_UNVERIFIED
    assert stored["verified"] is False and stored["configured"] is False
    assert "runtime_verification" not in stored["acquisition_evidence"][0]["installation"]


def test_promoted_devour_capability_is_disabled_when_artifact_changes_before_next_claim(tmp_path):
    root, package, _package_sha, registry = _candidate_package(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock full suite passed", stderr="")
    assert updater.apply(package)["ok"] is True

    registry = CapabilityManager(root)
    tools = ToolRegistry(capability_manager=registry)
    tools.add("terminal_agent", "Run a terminal task", _installed_adapter(root), "write")
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register(
        "terminal_agent",
        lambda _args, _result: PostconditionResult(True, {"observed": True, "state_matches": True}),
    )
    executor = Executor(tools, capabilities=registry)
    executor.permissions.needs_confirmation = lambda _name, _args: False
    assert executor.run({"steps": [{"tool": "terminal_agent", "args": {}}]})[0]["status"] == "verified"
    assert registry.can_claim("terminal_agent") is True

    # A successful prior verification must not grant indefinite trust if a
    # candidate file is changed later, before the next capability claim.
    (root / "alice" / "feature.py").write_text("VALUE = 'tampered later'\n", encoding="utf-8")
    assert registry.can_claim("terminal_agent") is False
    assert registry.has("terminal_agent") is False
    stored = registry.get("terminal_agent")
    assert stored["status"] == STATUS_UNVERIFIED
    assert stored["verified"] is False and stored["configured"] is False
    assert "no longer matches" in stored["verification_note"]


def test_promoted_devour_capability_is_disabled_when_persisted_install_receipt_is_tampered(tmp_path):
    root, package, _package_sha, _registry = _candidate_package(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock full suite passed", stderr="")
    assert updater.apply(package)["ok"] is True

    registry = CapabilityManager(root)
    tools = ToolRegistry(capability_manager=registry)
    tools.add("terminal_agent", "Run a terminal task", _installed_adapter(root), "write")
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register(
        "terminal_agent",
        lambda _args, _result: PostconditionResult(True, {"observed": True, "state_matches": True}),
    )
    executor = Executor(tools, capabilities=registry)
    executor.permissions.needs_confirmation = lambda _name, _args: False
    assert executor.run({"steps": [{"tool": "terminal_agent", "args": {}}]})[0]["status"] == "verified"
    assert registry.can_claim("terminal_agent") is True

    # A restart followed by receipt-state tampering must not preserve trust.
    import json
    path = root / "alice_workspace" / "capabilities.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    receipt = stored["terminal_agent"]["acquisition_evidence"][0]["installation"]
    receipt["status"] = "installed_pending_runtime_verification"
    path.write_text(json.dumps(stored), encoding="utf-8")

    restarted = CapabilityManager(root)
    assert restarted.can_claim("terminal_agent") is False
    after = restarted.get("terminal_agent")
    assert after["status"] == STATUS_UNVERIFIED
    assert after["verified"] is False and after["configured"] is False
    assert "no longer matches" in after["verification_note"]


def _run_verified_terminal_agent(root, registry, function):
    tools = ToolRegistry(capability_manager=registry)
    tools.add("terminal_agent", "Run a terminal task", function, "write")
    tools.postconditions = PostconditionRegistry()
    tools.postconditions.register(
        "terminal_agent",
        lambda _args, _result: PostconditionResult(True, {"observed": True, "state_matches": True}),
    )
    executor = Executor(tools, capabilities=registry)
    executor.permissions.needs_confirmation = lambda _name, _args: False
    result = executor.run({"steps": [{"tool": "terminal_agent", "args": {}}]})[0]
    return tools, result


def test_devour_promotion_requires_declared_entrypoint_and_installed_registered_callable(tmp_path):
    root, package, _package_sha, _registry = _candidate_package(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock suite passed", stderr="")
    assert updater.apply(package)["ok"] is True

    registry = CapabilityManager(root)
    tools, result = _run_verified_terminal_agent(root, registry, _installed_adapter(root))

    assert result["status"] == "verified"
    assert tools.get("terminal_agent").fn.__module__ == "alice.adapters.terminal_agent"
    assert registry.can_claim("terminal_agent") is True
    provenance = registry.get("terminal_agent")["acquisition_evidence"][0]["installation"]
    provenance = provenance["runtime_verification"]["callable_provenance"]
    assert provenance["qualname"] == "run_terminal_agent"
    assert provenance["source_path"] == "alice/adapters/terminal_agent.py"
    assert len(provenance["source_sha256"]) == 64
    assert len(provenance["code_sha256"]) == 64
    assert "alice.feature" not in sys.modules


def test_devour_promotion_rejects_callable_outside_installed_alice_source(tmp_path):
    root, package, _package_sha, _registry = _candidate_package(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock suite passed", stderr="")
    assert updater.apply(package)["ok"] is True

    registry = CapabilityManager(root)
    _tools, result = _run_verified_terminal_agent(root, registry, lambda: {"ok": True})

    assert result["status"] == "verified"
    assert registry.can_claim("terminal_agent") is False
    assert "not the exact live ALICE tool" in registry.get("terminal_agent")["verification_note"]


def test_devour_claim_is_revoked_when_registered_callable_changes(tmp_path):
    root, package, _package_sha, _registry = _candidate_package(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock suite passed", stderr="")
    assert updater.apply(package)["ok"] is True

    registry = CapabilityManager(root)
    tools, result = _run_verified_terminal_agent(root, registry, _installed_adapter(root))
    assert result["status"] == "verified" and registry.can_claim("terminal_agent") is True

    tools.add("terminal_agent", "Run a terminal task", _installed_adapter(root, "run_other_terminal_agent"), "write")

    assert registry.can_claim("terminal_agent") is False
    stored = registry.get("terminal_agent")
    assert stored["status"] == STATUS_UNVERIFIED
    assert stored["verified"] is False and stored["configured"] is False


def test_devour_claim_rechecks_persisted_callable_provenance_after_restart(tmp_path):
    root, package, _package_sha, _registry = _candidate_package(tmp_path)
    updater = InPlaceUpdater(root)
    updater._run_tests = lambda: SimpleNamespace(returncode=0, stdout="mock suite passed", stderr="")
    assert updater.apply(package)["ok"] is True

    registry = CapabilityManager(root)
    _tools, result = _run_verified_terminal_agent(root, registry, _installed_adapter(root))
    assert result["status"] == "verified" and registry.can_claim("terminal_agent") is True

    path = root / "alice_workspace" / "capabilities.json"
    stored = json.loads(path.read_text(encoding="utf-8"))
    installation = stored["terminal_agent"]["acquisition_evidence"][0]["installation"]
    installation["runtime_verification"]["callable_provenance"]["code_sha256"] = "0" * 64
    path.write_text(json.dumps(stored), encoding="utf-8")

    restarted = CapabilityManager(root)
    _run_verified_terminal_agent(root, restarted, _installed_adapter(root))
    assert restarted.can_claim("terminal_agent") is False
    after = restarted.get("terminal_agent")
    assert after["status"] == STATUS_UNVERIFIED
    assert after["verified"] is False and after["configured"] is False
