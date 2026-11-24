"""Multi-agent orchestration: bounded workers, collaboration, merge and verification."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict
from pathlib import Path
import json
import math
import os
import re
import shutil
import tempfile
import time
from contextlib import contextmanager

from .worker import WorkerSpec, WorkerResult, SpecialistWorker


class MultiAgentOrchestrator:
    MAX_OBJECTIVE_CHARS = 12000
    MAX_CONTEXT_CHARS = 50000
    MAX_WORKERS = 32
    MAX_WORKER_EVIDENCE_BYTES = 256 * 1024
    MAX_MERGE_RESPONSE_CHARS = 64 * 1024
    MAX_MERGE_LIST_ITEMS = 32
    MAX_MERGE_ITEM_CHARS = 1000
    MAX_MERGE_SUMMARY_CHARS = 8000

    ROLES = {
        "researcher": "Find and synthesize trustworthy information. Prefer read-only tools.",
        "coder": "Design or implement bounded software changes. Never modify Alice core directly.",
        "tester": "Inspect and test a bounded artifact; report failures and reproducible evidence.",
        "browser_operator": "Research or operate a browser task within the assigned site/tool scope.",
        "ui_analyst": "Inspect UI/screen state and recommend concrete interaction steps.",
        "documenter": "Turn supplied evidence into concise documentation or instructions.",
        "debugger": "Diagnose a bounded failure and propose or apply a safe fix in the assigned workspace.",
    }

    def __init__(self, router, tools, workspace=None, max_workers=4, workspace_lock_timeout=300.0):
        if isinstance(max_workers, bool) or not isinstance(max_workers, int) or max_workers < 1:
            raise ValueError("max_workers must be a positive integer")
        if (isinstance(workspace_lock_timeout, bool)
                or not isinstance(workspace_lock_timeout, (int, float))
                or not math.isfinite(workspace_lock_timeout)
                or not 0 < workspace_lock_timeout <= 86400):
            raise ValueError("workspace_lock_timeout must be finite and between 0 and 86400 seconds")
        self.workspace_lock_timeout = float(workspace_lock_timeout)
        self.router = router
        self.tools = tools
        self.root = Path(workspace or Path(__file__).resolve().parents[2]).resolve()
        self.worker_root = (self.root / "alice_workspace" / "workers").resolve()
        if self.worker_root == self.root or self.root not in self.worker_root.parents:
            raise ValueError("Worker workspace must be a child of the ALICE workspace")
        self.worker_root.mkdir(parents=True, exist_ok=True)
        self.max_workers = max_workers

    def _default_specs(self, objective):
        research = [n for n in ("fetch_webpage", "browser_page_text", "browser_snapshot", "list_files", "read_file", "capability_inventory") if n in self.tools.tools]
        analysis = [n for n in ("take_screenshot", "ground_screen", "screen_state", "running_apps", "browser_snapshot") if n in self.tools.tools]
        return [
            WorkerSpec("researcher-1", "researcher", objective, research, read_scope=["workspace", "web"], risk="read"),
            WorkerSpec("analyst-1", "ui_analyst", objective, analysis, risk="read"),
        ]

    @staticmethod
    def _failed_result(spec, exc):
        return WorkerResult(
            worker_id="orchestrator-error",
            name=spec.name,
            role=spec.role,
            status="failed",
            objective=spec.objective,
            error=f"Worker orchestration failed: {type(exc).__name__}: {str(exc)[:500]}",
        )

    @contextmanager
    def _workspace_lock(self):
        """Serialize orchestrations sharing this worker workspace across processes."""
        lock_path = self.worker_root / ".orchestrator.lock"
        deadline = time.monotonic() + self.workspace_lock_timeout
        with open(lock_path, "a+b") as lock_file:
            if os.name == "nt":
                import msvcrt

                # Do not read the lock byte here: another process may already
                # hold the byte-range lock, and Windows rejects overlapping
                # reads with PermissionError instead of letting us reach the
                # non-blocking acquisition/retry path. Initialize an empty
                # lock file using metadata only; a harmless extra byte from a
                # concurrent initializer does not affect locking byte zero.
                if lock_path.stat().st_size == 0:
                    lock_file.seek(0, os.SEEK_END)
                    lock_file.write(b"0")
                    lock_file.flush()
                while True:
                    try:
                        lock_file.seek(0)
                        msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
                        break
                    except OSError as exc:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Timed out waiting for ALICE workspace lock") from exc
                        time.sleep(min(0.05, max(0.001, deadline - time.monotonic())))
                try:
                    yield
                finally:
                    lock_file.seek(0)
                    msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
            else:
                import fcntl

                while True:
                    try:
                        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                        break
                    except BlockingIOError as exc:
                        if time.monotonic() >= deadline:
                            raise TimeoutError("Timed out waiting for ALICE workspace lock") from exc
                        time.sleep(min(0.05, max(0.001, deadline - time.monotonic())))
                try:
                    yield
                finally:
                    fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def run(self, objective, specs=None, context="", verify=True):
        # The lock covers validation, worker directory lifecycle, checkpoint
        # replacement, and cleanup: separate processes cannot collide on names.
        with self._workspace_lock():
            return self._run_locked(objective, specs, context, verify)

    def _run_locked(self, objective, specs=None, context="", verify=True):
        if not isinstance(objective, str) or not objective.strip():
            raise ValueError("objective must be a non-empty string")
        if len(objective) > self.MAX_OBJECTIVE_CHARS:
            raise ValueError(f"objective exceeds {self.MAX_OBJECTIVE_CHARS} characters")
        if not isinstance(context, str):
            raise TypeError("context must be a string")
        if len(context) > self.MAX_CONTEXT_CHARS:
            raise ValueError(f"context exceeds {self.MAX_CONTEXT_CHARS} characters")
        if type(verify) is not bool:
            raise TypeError("verify must be a boolean")
        specs = list(specs if specs is not None else self._default_specs(objective))
        if not specs:
            raise ValueError("At least one worker is required")
        if len(specs) > self.MAX_WORKERS:
            raise ValueError(f"At most {self.MAX_WORKERS} workers are allowed per orchestration")
        # Validate the complete batch before creating any worker directory. Names
        # are single path components, not arbitrary relative paths, and the
        # checkpoint filename is reserved by the orchestrator itself.
        names = []
        for spec in specs:
            if not isinstance(spec, WorkerSpec):
                raise TypeError("specs must contain WorkerSpec instances")
            name = spec.name
            if (not isinstance(name, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,63}", name)
                    or name in {".", "..", "last_orchestration.json"}):
                raise ValueError("Worker name must be a safe 1-64 character path component")
            if not isinstance(spec.role, str) or not spec.role.strip() or len(spec.role) > 80:
                raise ValueError("Worker role must be a non-empty string of at most 80 characters")
            if not isinstance(spec.objective, str) or not spec.objective.strip() or len(spec.objective) > 12000:
                raise ValueError("Worker objective must be a non-empty string of at most 12000 characters")
            if (not isinstance(spec.allowed_tools, list)
                    or any(not isinstance(tool_name, str) or not tool_name.strip() for tool_name in spec.allowed_tools)
                    or len(set(spec.allowed_tools)) != len(spec.allowed_tools)):
                raise ValueError("Worker allowed_tools must be a list of unique non-empty names")
            if isinstance(spec.max_steps, bool) or not isinstance(spec.max_steps, int) or not 1 <= spec.max_steps <= 100:
                raise ValueError("Worker max_steps must be an integer between 1 and 100")
            if (isinstance(spec.timeout_seconds, bool) or not isinstance(spec.timeout_seconds, (int, float))
                    or not 0 < spec.timeout_seconds <= 86400):
                raise ValueError("Worker timeout_seconds must be between 0 and 86400 seconds")
            if not isinstance(spec.risk, str) or spec.risk not in {"read", "write", "system"}:
                raise ValueError("Worker risk must be read, write, or system")
            names.append(name)
        if len(set(names)) != len(names):
            raise ValueError("Worker names must be unique within an orchestration")
        worker_dirs = []
        for name in names:
            candidate = self.worker_root / name
            # Reject symlinks, including dangling symlinks, rather than following
            # a path planted between orchestrator runs.
            if candidate.is_symlink():
                raise ValueError("Worker directory must not be a symbolic link")
            worker_dir = candidate.resolve()
            if self.worker_root not in worker_dir.parents:
                raise ValueError("Worker name escapes the worker workspace")
            worker_dirs.append(worker_dir)
        for worker_dir in worker_dirs:
            worker_dir.mkdir(parents=True, exist_ok=True)

        started = time.monotonic()
        results_by_name = {}
        orchestration_errors = []
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(specs))) as pool:
            futures = {pool.submit(SpecialistWorker(self.router, self.tools, spec).run, context): spec for spec in specs}
            for future in as_completed(futures):
                spec = futures[future]
                try:
                    result = future.result()
                    if not isinstance(result, WorkerResult):
                        raise TypeError("worker returned an invalid result object")
                    if (result.name != spec.name or result.role != spec.role
                            or result.objective != spec.objective):
                        raise ValueError("worker result identity does not match its assigned specification")
                    if result.status not in {"completed", "partial", "failed"}:
                        raise ValueError("worker returned an unsupported status")
                    if (not isinstance(result.summary, str) or len(result.summary) > 4000
                            or not isinstance(result.error, str) or len(result.error) > 2000
                            or not isinstance(result.artifacts, list)
                            or len(result.artifacts) > 50
                            or any(not isinstance(item, str) or len(item) > 1024 for item in result.artifacts)
                            or not isinstance(result.tool_results, list)
                            or len(result.tool_results) > spec.max_steps):
                        raise ValueError("worker result exceeds the orchestrator result contract")
                    try:
                        evidence_json = json.dumps(result.tool_results, ensure_ascii=False, allow_nan=False)
                    except (TypeError, ValueError, OverflowError) as evidence_exc:
                        raise ValueError("worker tool evidence is not finite JSON data") from evidence_exc
                    if len(evidence_json.encode("utf-8")) > self.MAX_WORKER_EVIDENCE_BYTES:
                        raise ValueError("worker tool evidence exceeds the 256 KB limit")
                except Exception as exc:
                    result = self._failed_result(spec, exc)
                    orchestration_errors.append({"worker": spec.name, "error": type(exc).__name__})
                results_by_name[spec.name] = result

        results = [results_by_name[spec.name] for spec in specs]
        reports = [asdict(result) for result in results]
        merged = self.merge(objective, reports)
        verification = self.verify(objective, merged, reports) if verify else {"ok": False, "reason": "verification disabled"}
        final = {
            "ok": bool(verification.get("ok")) and all(report["status"] == "completed" for report in reports),
            "objective": objective,
            "workers": reports,
            "merged": merged,
            "verification": verification,
            "orchestration_errors": orchestration_errors,
            "elapsed": time.monotonic() - started,
        }
        checkpoint_error = None
        try:
            self._write_checkpoint(final)
        except Exception as exc:
            checkpoint_error = {"error": type(exc).__name__, "detail": str(exc)[:300]}
            final["ok"] = False
            final["checkpoint_error"] = checkpoint_error
        cleanup_errors = self.dispose(results)
        if cleanup_errors:
            final["ok"] = False
            final["cleanup_errors"] = cleanup_errors
            # Best effort to persist the final, now explicitly degraded status.
            try:
                self._write_checkpoint(final)
            except Exception:
                pass
        return final

    def merge(self, objective, reports):
        successful = [r for r in reports if r["status"] == "completed"]
        evidence = [{"worker": r["name"], "role": r["role"], "summary": r["summary"],
                     "artifacts": r["artifacts"], "tool_results": r["tool_results"][-8:]}
                    for r in successful]
        try:
            evidence_text = json.dumps(evidence, ensure_ascii=False, allow_nan=False)
            prompt = (
                "You are Alice's merge engine. Combine independent temporary-worker reports into one accurate result. "
                "Do not invent facts; identify disagreement and missing evidence. Return JSON only: "
                '{"summary":"...","agreements":[],"conflicts":[],"next_actions":[]}\n'
                + "OBJECTIVE:\n" + objective + "\nREPORTS:\n" + evidence_text
            )
            raw = self.router.ask(prompt)
            if not isinstance(raw, str):
                raise TypeError("Merge model must return text")
            if len(raw) > self.MAX_MERGE_RESPONSE_CHARS:
                raise ValueError("Merge response exceeds the 64 KB limit")
            a, b = raw.find("{"), raw.rfind("}")
            if a < 0 or b < a:
                raise ValueError("InvalidMergeResponse")
            try:
                parsed = json.loads(raw[a:b + 1])
            except json.JSONDecodeError as exc:
                raise ValueError("InvalidMergeResponse") from exc
            if not isinstance(parsed, dict):
                raise ValueError("Merge response must be a JSON object")
            summary = parsed.get("summary")
            if not isinstance(summary, str) or not summary.strip() or len(summary) > self.MAX_MERGE_SUMMARY_CHARS:
                raise ValueError("Merge summary must be non-empty text of at most 8000 characters")
            for field in ("agreements", "conflicts", "next_actions"):
                values = parsed.get(field, [])
                if (not isinstance(values, list) or len(values) > self.MAX_MERGE_LIST_ITEMS
                        or any(not isinstance(item, str) or len(item) > self.MAX_MERGE_ITEM_CHARS for item in values)):
                    raise ValueError(f"Merge field {field} must contain at most 32 strings of at most 1000 characters")
                parsed[field] = values
            # Discard unrecognized model fields; only the declared merge contract
            # is allowed into checkpoints and downstream verification.
            return {key: parsed[key] for key in ("summary", "agreements", "conflicts", "next_actions")}
        except Exception as exc:
            error_name = "InvalidMergeResponse" if str(exc) == "InvalidMergeResponse" else type(exc).__name__
            return {"summary": "Worker reports collected without model merge.", "agreements": [],
                    "conflicts": [], "next_actions": [], "merge_error": error_name}

    def verify(self, objective, merged, reports):
        failed = [r["name"] for r in reports if r["status"] != "completed"]
        return {"ok": not failed and bool(merged.get("summary")), "failed_workers": failed, "evidence_count": sum(len(r.get("tool_results", [])) for r in reports)}

    def _write_checkpoint(self, result):
        path = self.worker_root / "last_orchestration.json"
        fd, temp_name = tempfile.mkstemp(prefix=".orchestration-", suffix=".tmp", dir=self.worker_root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(result, stream, indent=2, ensure_ascii=False, default=str)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(temp_name, path)
            if os.name != "nt":
                directory_fd = os.open(self.worker_root, os.O_RDONLY)
                try:
                    os.fsync(directory_fd)
                finally:
                    os.close(directory_fd)
        except Exception:
            try:
                os.unlink(temp_name)
            except OSError:
                pass
            raise

    def dispose(self, results):
        """Remove only per-run worker directories; preserve checkpoint and report failures."""
        errors = []
        for result in results:
            path = (self.worker_root / result.name).resolve()
            if self.worker_root not in path.parents:
                errors.append({"worker": result.name, "error": "UnsafeCleanupPath"})
                continue
            try:
                if path.exists():
                    shutil.rmtree(path)
            except OSError as exc:
                errors.append({"worker": result.name, "error": type(exc).__name__})
        return errors
