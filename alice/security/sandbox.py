"""Bounded execution sandbox for untrusted/newly acquired capabilities.

This is a defense-in-depth boundary, not a claim of OS-level isolation.  On
POSIX systems it uses subprocess resource limits; on Windows it uses process
creation flags and strict path/command checks.  For stronger isolation Alice
can optionally hand work to an external sandbox/container in a future layer.
"""
from __future__ import annotations

import os
import re
import shutil
import signal
import subprocess
import tempfile
import time
from dataclasses import dataclass, field, asdict
from pathlib import Path


class SandboxViolation(RuntimeError):
    pass


@dataclass
class SandboxPolicy:
    name: str = "capability"
    timeout_seconds: int = 30
    max_output_bytes: int = 200_000
    max_workspace_bytes: int = 50_000_000
    allow_network: bool = False
    allowed_commands: list[str] = field(default_factory=list)
    read_roots: list[str] = field(default_factory=list)
    write_roots: list[str] = field(default_factory=list)
    env_allowlist: list[str] = field(default_factory=lambda: ["PATH", "PYTHONPATH", "TEMP", "TMP", "TMPDIR"])
    max_processes: int = 8


@dataclass
class SandboxResult:
    ok: bool
    returncode: int | None
    stdout: str
    stderr: str
    duration_seconds: float
    timed_out: bool = False
    killed: bool = False
    violation: str | None = None

    def to_dict(self):
        return asdict(self)


class Sandbox:
    """Execute a capability with bounded time, paths, commands and output."""

    _WINDOWS_META = re.compile(r"[&|<>`\n\r]")
    _UNIX_META = re.compile(r"[;&|<>`\n\r]")

    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.sandbox_root = self.root / "alice_workspace" / "sandboxes"
        self.sandbox_root.mkdir(parents=True, exist_ok=True)

    def create_workspace(self, name: str) -> Path:
        safe = re.sub(r"[^a-zA-Z0-9_-]+", "_", name)[:48].strip("_") or "capability"
        path = Path(tempfile.mkdtemp(prefix=safe + "_", dir=self.sandbox_root))
        return path.resolve()

    def _inside(self, path: Path, roots: list[str]) -> bool:
        p = path.resolve()
        return any(p == Path(r).resolve() or Path(r).resolve() in p.parents for r in roots)

    def _validate_command(self, command: list[str], policy: SandboxPolicy):
        if not command or not all(isinstance(x, str) and x for x in command):
            raise SandboxViolation("Command must be a non-empty argument list")
        # shell=False is mandatory below, so arguments may legitimately contain
        # code such as Python expressions. Only the executable token is checked
        # for shell metacharacters.
        if (self._WINDOWS_META if os.name == "nt" else self._UNIX_META).search(command[0]):
            raise SandboxViolation("Unsafe executable token")
        exe = Path(command[0]).name.lower()
        shell_executables = {"sh", "bash", "zsh", "fish", "cmd", "cmd.exe", "powershell", "powershell.exe", "pwsh", "pwsh.exe"}
        if exe in shell_executables and exe not in {Path(x).name.lower() for x in policy.allowed_commands}:
            raise SandboxViolation("Shell executables require an explicit allowlist entry")
        if policy.allowed_commands:
            exe = Path(command[0]).name.lower()
            allowed = {Path(x).name.lower() for x in policy.allowed_commands}
            if exe not in allowed:
                raise SandboxViolation(f"Command not allowed by sandbox policy: {exe}")

    def _preexec(self, policy: SandboxPolicy):
        if os.name == "nt":
            return None
        def limit():
            try:
                import resource
                cpu = max(1, int(policy.timeout_seconds))
                resource.setrlimit(resource.RLIMIT_CPU, (cpu, cpu))
                resource.setrlimit(resource.RLIMIT_FSIZE, (policy.max_output_bytes, policy.max_output_bytes))
                resource.setrlimit(resource.RLIMIT_NPROC, (policy.max_processes, policy.max_processes))
            except Exception:
                pass
            os.setsid()
        return limit

    def run(self, command: list[str], policy: SandboxPolicy | None = None, workspace=None, env=None) -> SandboxResult:
        policy = policy or SandboxPolicy()
        started = time.monotonic()
        ws = Path(workspace).resolve() if workspace else self.create_workspace(policy.name)
        if not self._inside(ws, [str(self.sandbox_root)]):
            raise SandboxViolation("Workspace must be inside Alice sandbox root")
        self._validate_command(command, policy)

        safe_env = {k: os.environ[k] for k in policy.env_allowlist if k in os.environ}
        if env:
            for k, v in env.items():
                if k in policy.env_allowlist:
                    safe_env[k] = str(v)
        safe_env["ALICE_SANDBOX"] = "1"
        safe_env["ALICE_SANDBOX_NETWORK"] = "1" if policy.allow_network else "0"

        # Do not expose Alice's full environment, credentials or provider keys.
        creationflags = 0
        if os.name == "nt":
            creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0) | getattr(subprocess, "CREATE_NO_WINDOW", 0)

        try:
            proc = subprocess.Popen(
                command,
                cwd=str(ws),
                env=safe_env,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                shell=False,
                preexec_fn=self._preexec(policy),
                creationflags=creationflags,
            )
            try:
                out, err = proc.communicate(timeout=policy.timeout_seconds)
            except subprocess.TimeoutExpired:
                if os.name != "nt":
                    try: os.killpg(proc.pid, signal.SIGKILL)
                    except Exception: proc.kill()
                else:
                    proc.kill()
                out, err = proc.communicate()
                return SandboxResult(False, proc.returncode, out[:policy.max_output_bytes], err[:policy.max_output_bytes], time.monotonic()-started, True, True)

            out = out[:policy.max_output_bytes]
            err = err[:policy.max_output_bytes]
            ok = proc.returncode == 0
            return SandboxResult(ok, proc.returncode, out, err, time.monotonic()-started)
        except (OSError, subprocess.SubprocessError) as exc:
            return SandboxResult(False, None, "", str(exc), time.monotonic()-started, violation=str(exc))

    def cleanup(self, workspace):
        p = Path(workspace).resolve()
        if not self._inside(p, [str(self.sandbox_root)]) or p == self.sandbox_root:
            raise SandboxViolation("Refusing to delete outside sandbox root")
        shutil.rmtree(p, ignore_errors=False)
