"""External, Windows-safe updater finalizer for ALICE.

The helper survives the GUI process, applies the verified package, repairs
launchers, starts the upgraded process, and verifies a startup handshake.
It records diagnostics instead of silently failing so a broken relaunch is
never mistaken for a successful upgrade.
"""
from __future__ import annotations
import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

try:
    from .upgrade_audit import UpgradeAudit
except ImportError:
    from upgrade_audit import UpgradeAudit


def _wait_for_pid_exit(pid: int) -> bool:
    if not pid:
        return True
    try:
        import psutil
    except Exception:
        psutil = None
    if psutil is not None:
        for _ in range(160):
            if not psutil.pid_exists(pid):
                return True
            time.sleep(0.25)
        return False
    for _ in range(160):
        try:
            r = subprocess.run(["tasklist", "/FI", f"PID eq {pid}"], capture_output=True, text=True, timeout=2)
            if not re.search(rf"\b{pid}\b", r.stdout):
                return True
        except Exception:
            return False
        time.sleep(0.25)
    return False


def _launch_gui(root: Path, log_path: Path):
    """Start ALICE with python.exe, not pythonw.exe, while hiding the console.

    python.exe is deliberately used for the post-upgrade handshake because it
    gives us reliable stdout/stderr diagnostics if module startup fails. The
    Windows CREATE_NO_WINDOW flag keeps that diagnostic process from creating
    a visible console window.
    """
    scripts = root / ".venv" / "Scripts"
    candidates = [scripts / "python.exe", scripts / "pythonw.exe"]
    launcher = next((p for p in candidates if p.exists()), None)
    if launcher is None:
        raise RuntimeError(f"No ALICE Python launcher found under {scripts}")
    log_path.parent.mkdir(parents=True, exist_ok=True)
    log = log_path.open("ab")
    flags = (
        getattr(subprocess, "DETACHED_PROCESS", 0)
        | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        | getattr(subprocess, "CREATE_NO_WINDOW", 0)
    )
    try:
        child = subprocess.Popen(
            [str(launcher), "-m", "alice", "--show"],
            cwd=str(root),
            stdin=subprocess.DEVNULL,
            stdout=log,
            stderr=subprocess.STDOUT,
            creationflags=flags,
            close_fds=True,
        )
    finally:
        log.close()
    return child, launcher


def _read_health(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--root", required=True)
    ap.add_argument("--package", required=True)
    ap.add_argument("--pid", type=int, default=0)
    ap.add_argument("--restart", action="store_true")
    ap.add_argument("--health-timeout", type=int, default=60)
    args = ap.parse_args()

    root_requested = Path(args.root).expanduser().absolute()
    package = Path(args.package).expanduser().absolute()
    sys.path.insert(0, str(root_requested))
    from alice.deployment.updater import InPlaceUpdater, read_version, _assert_no_reparse_path
    from alice.deployment.launcher_repair import repair_windows_launchers
    from alice.deployment.signed_updates import UpdateJournal, verify_signed_package, record_signed_update_success
    from alice.deployment.update_service import UpdateService
    _assert_no_reparse_path(root_requested)
    _assert_no_reparse_path(package)
    root = root_requested.resolve()
    runtime = root / "alice_workspace" / "runtime"
    audit = UpgradeAudit(root)
    audit.record("begin", version=str(root / "VERSION.txt"))
    runtime.mkdir(parents=True, exist_ok=True)
    diagnostics = runtime / "upgrade_relaunch_diagnostics.json"
    health = runtime / "health.json"

    service = UpdateService(root)
    recovered = service.recover_interrupted()
    if recovered.get("helper_active"):
        audit.record("another_update_helper_active", ok=False)
        raise SystemExit(4)
    journal = UpdateJournal(root)
    # Claim the transaction before waiting so another ALICE process cannot
    # start and race the file swap while the original UI shuts down.
    journal.transition("CHECKING", helper_pid=os.getpid())
    old_health = _read_health(health) or {}
    try:
        health.unlink(missing_ok=True)
    except Exception:
        pass

    audit.record("wait_for_old_process", detail=f"pid={args.pid}")
    if not _wait_for_pid_exit(args.pid):
        journal.transition("FAILED", helper_pid=os.getpid(), error="old_process_exit_timeout")
        diagnostics.write_text(json.dumps({"stage": "wait_for_old_process", "ok": False, "error": "process_exit_timeout"}, indent=2), encoding="utf-8")
        raise SystemExit(5)

    backup_ref = None
    try:
        # Reauthenticate only after the GUI has exited. A package or sidecar
        # replaced while this helper waited is rejected before any mutation.
        verified = verify_signed_package(root, package)
        package = Path(verified["package"])
        signed_manifest = verified["manifest"]
        sequence = signed_manifest["sequence"]
        target_version = signed_manifest["version"]
        package_digest = signed_manifest["package"]["sha256"]
        journal.transition("VERIFIED", version=target_version, sequence=sequence, package_sha256=package_digest, helper_pid=os.getpid())
        audit.record("signature_verified", ok=True, version=target_version, detail=signed_manifest["key_id"])

        def record_apply_state(state, backup):
            nonlocal backup_ref
            backup_ref = str(backup)
            journal.transition(state, version=target_version, sequence=sequence,
                               package_sha256=package_digest, backup=backup_ref, helper_pid=os.getpid())

        result = InPlaceUpdater(root).apply(package, expected_sha256=package_digest, state_callback=record_apply_state)
    except Exception as exc:
        audit.record("verification_failed", ok=False, detail=type(exc).__name__)
        if backup_ref:
            try:
                journal.transition("ROLLING_BACK", backup=backup_ref, helper_pid=os.getpid(), error=type(exc).__name__)
                InPlaceUpdater(root).rollback(backup_ref)
                journal.transition("ROLLED_BACK", backup=backup_ref, helper_pid=os.getpid(), error=type(exc).__name__)
            except Exception:
                journal.transition("FAILED", backup=backup_ref, helper_pid=os.getpid(), error="rollback_failed")
        else:
            journal.transition("FAILED", helper_pid=os.getpid(), error=type(exc).__name__)
        diagnostics.write_text(json.dumps({"stage": "verification", "ok": False, "error": str(exc)}, indent=2), encoding="utf-8")
        raise SystemExit(2)
    audit.record("install", ok=bool(result.get("ok")), version=result.get("version", ""), detail=result.get("error", result.get("reason", "")))
    (runtime / "last_update.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    if not result.get("ok"):
        if result.get("rolled_back"):
            journal.transition("ROLLING_BACK", version=result.get("target"), sequence=sequence,
                               package_sha256=package_digest, backup=result.get("backup"), helper_pid=os.getpid())
            journal.transition("ROLLED_BACK", version=result.get("version"), sequence=sequence,
                               package_sha256=package_digest, backup=result.get("backup"), helper_pid=os.getpid())
        else:
            journal.transition("FAILED", version=result.get("target"), sequence=sequence,
                               package_sha256=package_digest, backup=result.get("backup"), helper_pid=os.getpid(), error="apply_failed")
        diagnostics.write_text(json.dumps({"stage": "install", "result": result}, indent=2), encoding="utf-8")
        raise SystemExit(2)

    journal.transition("HEALTH_CHECK", version=target_version, sequence=sequence,
                       package_sha256=package_digest, backup=result.get("backup"), helper_pid=os.getpid())
    if not args.restart:
        journal.transition("ROLLING_BACK", version=target_version, sequence=sequence,
                           package_sha256=package_digest, backup=result.get("backup"), helper_pid=os.getpid(),
                           error="restart_health_check_required")
        InPlaceUpdater(root).rollback(result["backup"])
        journal.transition("ROLLED_BACK", version=read_version(root), sequence=sequence,
                           package_sha256=package_digest, backup=result.get("backup"), helper_pid=os.getpid())
        raise SystemExit(4)

    child = None
    try:
        repair = repair_windows_launchers(root, start_visible=False)
        audit.record("launcher_repair", ok=bool(repair.get("ok")), version=result.get("version", ""))
        child, launcher = _launch_gui(root, runtime / "upgrade_relaunch.log")
        audit.record("relaunch_started", version=result.get("version", ""), detail=f"pid={child.pid}")
        deadline = time.time() + max(10, args.health_timeout)
        healthy = False
        health_data = None
        while time.time() < deadline:
            health_data = _read_health(health)
            if (
                isinstance(health_data, dict)
                and health_data.get("ok") is True
                and health_data.get("started_at")
                and health_data.get("version") == result.get("version")
                and health_data.get("started_at") != old_health.get("started_at")
            ):
                healthy = True
                audit.record("health_verified", version=result.get("version", ""))
                break
            if child.poll() is not None:
                break
            time.sleep(0.5)

        if not healthy:
            exit_code = child.poll() if child is not None else None
            log_text = ""
            log_path = runtime / "upgrade_relaunch.log"
            try:
                log_text = log_path.read_text(encoding="utf-8", errors="replace")[-12000:]
            except Exception:
                pass
            payload = {
                "stage": "relaunch",
                "ok": False,
                "reason": "post_restart_health_timeout",
                "exit_code": exit_code,
                "launcher": str(launcher),
                "root": str(root),
                "health": health_data,
                "repair": repair,
                "diagnostic_log": str(log_path),
                "stdout_stderr_tail": log_text,
            }
            audit.record("health_failed", ok=False, version=result.get("version", ""), detail="post_restart_health_timeout")
            diagnostics.write_text(json.dumps(payload, indent=2), encoding="utf-8")
            if child is not None and child.poll() is None:
                try:
                    child.terminate()
                    child.wait(timeout=5)
                except Exception:
                    try: child.kill()
                    except Exception: pass
            backup = result.get("backup")
            if backup:
                journal.transition("ROLLING_BACK", version=target_version, sequence=sequence,
                                   package_sha256=package_digest, backup=backup, helper_pid=os.getpid(), error="health_check_failed")
                rollback = InPlaceUpdater(root).rollback(backup)
                audit.record("rollback", ok=bool(rollback), version=result.get("version", ""))
                journal.transition("ROLLED_BACK", version=rollback.get("version", ""), sequence=sequence,
                                   package_sha256=package_digest, backup=backup, helper_pid=os.getpid())
                diagnostics.write_text(json.dumps({**payload, "rolled_back": True, "rollback": rollback}, indent=2), encoding="utf-8")
            else:
                journal.transition("FAILED", version=target_version, sequence=sequence,
                                   package_sha256=package_digest, helper_pid=os.getpid(), error="health_check_failed_no_backup")
            raise SystemExit(3)

        record_signed_update_success(root, signed_manifest)
        journal.transition("ACCEPTED", version=target_version, sequence=sequence,
                           package_sha256=package_digest, backup=result.get("backup"), helper_pid=os.getpid())
        audit.record("complete", version=result.get("version", ""))
        diagnostics.write_text(json.dumps({
            "stage": "relaunch", "ok": True, "version": result.get("version"),
            "launcher": str(launcher), "root": str(root), "pid": child.pid,
            "health": health_data, "repair": repair,
        }, indent=2), encoding="utf-8")
        raise SystemExit(0)
    except SystemExit:
        raise
    except Exception as exc:
        diagnostics.write_text(json.dumps({"stage":"relaunch", "ok":False, "error":repr(exc)}, indent=2), encoding="utf-8")
        backup = result.get("backup")
        if backup:
            try:
                journal.transition("ROLLING_BACK", version=target_version, sequence=sequence,
                                   package_sha256=package_digest, backup=backup, helper_pid=os.getpid(), error=type(exc).__name__)
                InPlaceUpdater(root).rollback(backup)
                journal.transition("ROLLED_BACK", version=read_version(root), sequence=sequence,
                                   package_sha256=package_digest, backup=backup, helper_pid=os.getpid())
            except Exception:
                journal.transition("FAILED", backup=backup, helper_pid=os.getpid(), error="rollback_failed")
        raise SystemExit(3)


if __name__ == "__main__":
    main()
