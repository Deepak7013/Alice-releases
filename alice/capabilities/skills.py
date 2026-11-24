"""Controlled self-building skill forge.

Generated skills are deliberately small, pure adapters. They are staged, statically
validated and smoke-tested before registration. External I/O must be performed by
Alice's existing approved tools rather than arbitrary generated code.
"""
import ast, json, re, subprocess, sys, time
from pathlib import Path

ALLOWED_IMPORT_ROOTS = {
    "alice", "math", "json", "re", "statistics", "collections",
    "datetime", "decimal", "fractions", "itertools", "functools",
    "typing", "dataclasses", "enum",
}
DENY_CALLS = {
    "system", "popen", "remove", "rmtree", "unlink", "kill", "terminate",
    "eval", "exec", "__import__", "compile",
}
DENY_NAMES = {"__builtins__", "__globals__", "__locals__"}
DENY_ATTRS = {"system", "popen", "run", "Popen", "remove", "rmtree", "unlink"}

class SkillForge:
    def __init__(self, router, root=None, capabilities=None):
        self.router = router
        self.root = Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.dir = self.root / "alice_workspace" / "skills"
        self.dir.mkdir(parents=True, exist_ok=True)
        self.capabilities = capabilities

    def _validate(self, source):
        tree = ast.parse(source)
        if not any(isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == "run"
                   for n in tree.body):
            raise ValueError("Generated skill must define run(**kwargs)")
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    root = alias.name.split(".")[0]
                    if root not in ALLOWED_IMPORT_ROOTS:
                        raise ValueError(f"Import not allowed in generated skill: {root}")
            elif isinstance(node, ast.ImportFrom):
                root = (node.module or "").split(".")[0]
                if root not in ALLOWED_IMPORT_ROOTS:
                    raise ValueError(f"Import not allowed in generated skill: {root}")
            elif isinstance(node, ast.Call):
                if isinstance(node.func, ast.Name) and node.func.id in DENY_CALLS:
                    raise ValueError(f"Unsafe call in generated skill: {node.func.id}")
                if isinstance(node.func, ast.Attribute) and node.func.attr in DENY_ATTRS:
                    raise ValueError(f"Unsafe call in generated skill: {node.func.attr}")
            elif isinstance(node, ast.Name) and node.id in DENY_NAMES:
                raise ValueError(f"Unsafe name in generated skill: {node.id}")
            elif isinstance(node, (ast.With, ast.AsyncWith)):
                # Context managers are unnecessary for pure adapters and make hidden I/O easier.
                raise ValueError("Context managers are not allowed in generated skills")
        compile(tree, "<alice-skill>", "exec")
        return True

    def _smoke_test(self, path):
        # Import in a fresh interpreter only after static validation. The generated
        # skill itself must remain side-effect-light by policy; the smoke test checks
        # the public contract without executing run().
        code = (
            "import importlib.util, sys\n"
            f"sys.path.insert(0, {str(self.root)!r})\n"
            f"spec=importlib.util.spec_from_file_location('alice_skill_smoke', {str(path)!r})\n"
            "m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\n"
            "assert callable(getattr(m,'run',None))\n"
        )
        r = subprocess.run(
            [sys.executable, "-I", "-c", code],
            cwd=self.dir, capture_output=True, text=True, timeout=20,
            env={"PYTHONDONTWRITEBYTECODE":"1"},
        )
        return {"ok": r.returncode == 0, "stdout": r.stdout[-2000:], "stderr": r.stderr[-2000:]}

    def learn(self, goal, missing_capability=""):
        prompt = (
            "You are Alice's skill engineer. Create ONE small reusable Python skill adapter "
            "that fills a capability gap. Return JSON only: "
            '{"name":"...","description":"...","code":"...","tests":["description"]}. '
            "The module must expose run(**kwargs). It must be a PURE adapter: no filesystem, "
            "network, shell, subprocess, credentials, private browser state, persistence, "
            "destructive operations, or security bypasses. Use only allowed standard-library "
            "modules and Alice APIs. Existing Alice tools should perform external I/O. "
            "Do not put executable test commands in the tests field; provide human-readable "
            "test descriptions only. The skill must be narrow and testable.\n"
            "GOAL:\n" + str(goal) + "\nMISSING CAPABILITY:\n" + str(missing_capability)
        )
        raw = self.router.ask(prompt)
        a, b = raw.find("{"), raw.rfind("}")
        if a < 0 or b < a:
            raise ValueError("Skill model did not return JSON")
        spec = json.loads(raw[a:b+1])
        name = self._safe_name(spec.get("name"))
        code = str(spec.get("code", ""))
        self._validate(code)
        stage = self.dir / (name + ".candidate.py")
        final = self.dir / (name + ".py")
        stage.write_text(code, encoding="utf-8")
        smoke = self._smoke_test(stage)
        if not smoke["ok"]:
            stage.unlink(missing_ok=True)
            raise RuntimeError("Generated skill failed smoke validation: " + smoke["stderr"])
        stage.replace(final)
        if self.capabilities:
            self.capabilities.register(
                name, str(spec.get("description", "")),
                kind="learned", source="skillforge"
            )
        return {
            "ok": True, "name": name,
            "description": spec.get("description", ""),
            "path": str(final),
            "tests": {"ok": True, "smoke": smoke, "descriptions": list(spec.get("tests", []))[:4]},
        }

    @staticmethod
    def _safe_name(name):
        name = re.sub(r"[^a-zA-Z0-9_]+", "_", str(name).strip().lower()).strip("_")
        return name[:50] or "learned_skill"
