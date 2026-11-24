"""Privacy-bounded workflow replay based on current executor evidence."""
from __future__ import annotations

import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path


READ_ONLY = {
    "list_files", "read_file", "browser_tabs", "browser_page_text",
    "browser_snapshot", "browser_screenshot", "take_screenshot",
    "ground_screen", "screen_state", "running_apps", "screen_size",
    "mouse_position", "discover_apps", "capability_inventory",
    "integration_inventory", "world_state", "self_diagnostics",
    "research_web", "fetch_webpage", "search_knowledge",
}


def _sig(text):
    normalized = re.sub(r"\s+", " ", str(text).strip().lower())
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class WorkflowReplay:
    """Store advisory workflows only after every executor result is verified.

    Replay records deliberately omit request and argument values. Their hashes and
    argument names are enough to recognize a previously successful tool sequence
    without persisting message bodies, paths, or credentials.
    """

    VERSION = "v3.27.0"

    def __init__(self, root=None, max_records=300):
        self.root = Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.path = self.root / "alice_workspace" / "workflow_replay.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.max_records = max(1, int(max_records))
        self._lock = threading.RLock()
        self.data = self._load()

    def _load(self):
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("workflows", []), list):
                return {"workflows": []}
            return {"workflows": data.get("workflows", [])}
        except (OSError, ValueError, TypeError):
            return {"workflows": []}

    def _save(self, data=None):
        payload = self.data if data is None else data
        tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        try:
            with tmp.open("w", encoding="utf-8", newline="\n") as stream:
                json.dump(payload, stream, indent=2, ensure_ascii=False)
                stream.flush()
                os.fsync(stream.fileno())
            tmp.replace(self.path)
        except Exception:
            try:
                tmp.unlink(missing_ok=True)
            except OSError:
                pass
            raise

    @staticmethod
    def _argument_summary(args):
        if not isinstance(args, dict):
            args = {}
        entries = list(args.items())[:30]
        names = sorted(str(key)[:100] for key, _ in entries)
        # Hash a bounded canonical view. Values are never written to the replay file.
        bounded = {}
        for key, value in entries:
            name = str(key)[:100]
            try:
                encoded = json.dumps(value, ensure_ascii=False, sort_keys=True, default=str)
            except Exception:
                encoded = type(value).__name__
            bounded[name] = encoded[:2048]
        canonical = json.dumps(bounded, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return names, hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    @classmethod
    def _verified_result(cls, expected_tool, result, index):
        if not isinstance(result, dict) or result.get("tool") != expected_tool:
            return False
        if result.get("step") != index:
            return False
        status = result.get("status")
        if expected_tool in READ_ONLY:
            return status == "observed" and result.get("verified") is not True
        check = result.get("postcondition")
        evidence = check.get("evidence") if isinstance(check, dict) else None
        return (
            status == "verified"
            and result.get("verified") is True
            and isinstance(check, dict)
            and check.get("ok") is True
            and isinstance(evidence, dict)
            and evidence.get("observed") is True
        )

    def record(self, request, plan, results):
        plan_steps = plan.get("steps") if isinstance(plan, dict) else None
        if not isinstance(plan_steps, list) or not plan_steps or not isinstance(results, list):
            return False
        if len(plan_steps) != len(results):
            return False

        steps = []
        for index, (planned, result) in enumerate(zip(plan_steps, results), 1):
            if not isinstance(planned, dict):
                return False
            tool = planned.get("tool")
            if not isinstance(tool, str) or not tool or not self._verified_result(tool, result, index):
                return False
            argument_keys, arguments_sha256 = self._argument_summary(planned.get("args") or {})
            risk = planned.get("risk", "")
            steps.append({
                "tool": tool,
                "argument_keys": argument_keys,
                "arguments_sha256": arguments_sha256,
                "risk": str(risk)[:40],
            })

        signature = _sig(request)
        with self._lock:
            workflows = list(self.data.get("workflows", []))
            existing = next((row for row in workflows if isinstance(row, dict)
                             and row.get("signature") == signature
                             and row.get("verification_version") == self.VERSION), None)
            row = {
                "signature": signature,
                "verification_version": self.VERSION,
                "steps": steps,
                "verified": True,
                "runs": int(existing.get("runs", 0)) + 1 if existing else 1,
                "updated_at": time.time(),
            }
            workflows = [item for item in workflows if not (
                isinstance(item, dict) and item.get("signature") == signature
            )]
            workflows.append(row)
            updated = {"workflows": workflows[-self.max_records:]}
            self._save(updated)
            self.data = updated
        return True

    def exact(self, request):
        signature = _sig(request)
        with self._lock:
            rows = list(self.data.get("workflows", []))
        for row in reversed(rows):
            if (not isinstance(row, dict) or row.get("signature") != signature
                    or row.get("verification_version") != self.VERSION
                    or row.get("verified") is not True):
                continue
            steps = row.get("steps")
            if not isinstance(steps, list) or not steps:
                continue
            if any(not isinstance(step, dict) or not isinstance(step.get("tool"), str)
                   or not isinstance(step.get("argument_keys"), list)
                   or not isinstance(step.get("arguments_sha256"), str)
                   for step in steps):
                continue
            return dict(row)
        return None

    def candidate(self, request):
        row = self.exact(request)
        if not row:
            return None
        steps = row["steps"]
        return {
            "request_signature": row["signature"],
            "steps": steps,
            "runs": row.get("runs", 1),
            "verified": True,
            "replay_safe": all(step.get("tool") in READ_ONLY for step in steps),
        }

    def stats(self):
        with self._lock:
            rows = list(self.data.get("workflows", []))
        valid = [row for row in rows if isinstance(row, dict)
                 and row.get("verification_version") == self.VERSION
                 and row.get("verified") is True]
        return {
            "version": self.VERSION,
            "workflows": len(valid),
            "replay_safe": sum(1 for row in valid if all(
                isinstance(step, dict) and step.get("tool") in READ_ONLY
                for step in row.get("steps", [])
            )),
        }
