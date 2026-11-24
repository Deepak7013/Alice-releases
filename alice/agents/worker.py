"""Bounded temporary specialist workers for multi-agent tasks."""
from dataclasses import dataclass, field
from typing import Any, Dict, List
import json, time, uuid
from alice.agent.executor import Executor

@dataclass
class WorkerSpec:
    name: str
    role: str
    objective: str
    allowed_tools: List[str] = field(default_factory=list)
    workspace: str = "alice_workspace/workers"
    max_steps: int = 6
    timeout_seconds: int = 180
    read_scope: List[str] = field(default_factory=list)
    write_scope: List[str] = field(default_factory=list)
    risk: str = "read"

@dataclass
class WorkerResult:
    worker_id: str
    name: str
    role: str
    status: str
    objective: str
    summary: str = ""
    artifacts: List[str] = field(default_factory=list)
    tool_results: List[Dict[str, Any]] = field(default_factory=list)
    error: str = ""
    elapsed: float = 0.0

class SpecialistWorker:
    """A temporary agent with a strict tool allowlist and bounded execution."""
    def __init__(self, router, tools, spec: WorkerSpec):
        if spec.max_steps < 1:
            raise ValueError("Worker max_steps must be at least 1")
        if spec.timeout_seconds <= 0:
            raise ValueError("Worker timeout_seconds must be positive")
        self.router = router
        self.tools = tools
        self.spec = spec
        self.worker_id = uuid.uuid4().hex[:10]
        self.executor = Executor(
            tools,
            capabilities=getattr(tools, "capability_manager", None),
            postconditions=getattr(tools, "postconditions", None),
        )

    MAX_CONTEXT_CHARS = 50000
    MAX_MODEL_RESPONSE_CHARS = 1_000_000
    MAX_SUMMARY_CHARS = 4000
    MAX_ARTIFACTS = 50
    MAX_ARTIFACT_CHARS = 1024
    MAX_TOOL_ARGS_JSON_CHARS = 65536

    def _prompt(self, context: str) -> str:
        if not isinstance(context, str):
            raise TypeError("Worker context must be a string")
        if len(context) > self.MAX_CONTEXT_CHARS:
            raise ValueError(f"Worker context exceeds {self.MAX_CONTEXT_CHARS} characters")
        descriptions = {n: self.tools.tools[n].description for n in self.spec.allowed_tools if n in self.tools.tools}
        return f"""You are a temporary specialist inside Alice Gluttony.
ROLE: {self.spec.role}
OBJECTIVE: {self.spec.objective}
You are NOT the main agent. Solve only this bounded objective and return control to the orchestrator.
Do not request tools outside this allowlist. Never delete important data, access secrets, bypass security, weaken safety, or modify Alice core source.
Maximum tool steps: {self.spec.max_steps}.
AVAILABLE TOOLS:\n{json.dumps(descriptions, indent=2)}
CONTEXT:\n{context}
Return JSON only: {{"summary":"...","steps":[{{"tool":"name","args":{{}}}}],"artifacts":[]}}.
"""

    def run(self, context="") -> WorkerResult:
        started = time.time(); deadline = time.monotonic() + self.spec.timeout_seconds; results=[]
        try:
            raw = self.router.ask(self._prompt(context))
            if time.monotonic() >= deadline:
                raise TimeoutError("Worker deadline exceeded while waiting for its planning model")
            if not isinstance(raw, str):
                raise TypeError("Worker planning model must return text")
            if len(raw) > self.MAX_MODEL_RESPONSE_CHARS:
                raise ValueError("Worker planning response exceeds the 1 MB safety limit")
            text = raw.strip(); a,b=text.find("{"),text.rfind("}")
            if a >= 0 and b >= a:
                candidate = text[a:b+1]
            else:
                # Parse a complete non-object JSON value too, so arrays/scalars
                # receive a precise schema error instead of a vague missing-plan error.
                candidate = text
            plan = json.loads(candidate)
            if not isinstance(plan, dict):
                raise ValueError("Worker plan must be a JSON object")
            summary = plan.get("summary", "")
            if not isinstance(summary, str) or len(summary) > self.MAX_SUMMARY_CHARS:
                raise ValueError("Worker summary must be text of at most 4000 characters")
            steps = plan.get("steps", [])
            if not isinstance(steps, list) or len(steps) > self.spec.max_steps:
                raise ValueError("Worker step budget exceeded")
            artifacts = plan.get("artifacts", [])
            if (not isinstance(artifacts, list) or len(artifacts) > self.MAX_ARTIFACTS
                    or any(not isinstance(item, str) or not item.strip() or len(item) > self.MAX_ARTIFACT_CHARS
                           for item in artifacts)):
                raise ValueError("Worker artifacts must be up to 50 non-empty strings of at most 1024 characters")
            for step in steps:
                if time.monotonic() >= deadline:
                    raise TimeoutError("Worker execution deadline exceeded; remaining steps were not started")
                if not isinstance(step, dict):
                    raise ValueError("Every worker step must be an object")
                name = step.get("tool")
                if not isinstance(name, str) or name not in self.spec.allowed_tools:
                    raise PermissionError(f"Tool not allowed for worker: {name}")
                args = step.get("args", {})
                if not isinstance(args, dict):
                    raise ValueError("Worker tool args must be a JSON object")
                if len(json.dumps(args, ensure_ascii=False, separators=(",", ":"))) > self.MAX_TOOL_ARGS_JSON_CHARS:
                    raise ValueError("Worker tool arguments exceed the 64 KB safety limit")
                tool = self.tools.get(name)
                if tool is None: raise ValueError(f"Unknown tool: {name}")
                if tool.risk in {"system", "write"} and self.spec.risk not in {"write", "system"}:
                    raise PermissionError(f"Worker risk boundary blocks: {name}")
                # Specialist workers use the same permission, admission and
                # postcondition-aware executor as the main agent. Never call a
                # registered function directly from a worker plan.
                executed = self.executor.run({"steps": [{"tool": name, "args": args}]})
                result = executed[0] if executed else {"status": "error", "error": "Executor returned no step result"}
                results.append({"tool": name, "result": result})
                if result.get("status") in {"denied", "error", "not_sent"}:
                    raise RuntimeError(f"Worker tool '{name}' did not execute successfully: {result.get('status')}")
            unverified = [item for item in results if item.get("result", {}).get("status") == "attempted"]
            final_status = "partial" if unverified else "completed"
            if unverified:
                summary = (summary + " " if summary else "") + "Some non-read actions were attempted but lacked independent postcondition verification."
            return WorkerResult(self.worker_id,self.spec.name,self.spec.role,final_status,self.spec.objective,summary,artifacts,results,elapsed=time.time()-started)
        except Exception as exc:
            return WorkerResult(self.worker_id,self.spec.name,self.spec.role,"failed",self.spec.objective,error=str(exc),tool_results=results,elapsed=time.time()-started)
