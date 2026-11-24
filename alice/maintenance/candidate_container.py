"""Restricted Docker runner for untrusted ALICE upgrade candidates.

Candidate code is executed only after the Docker daemon, immutable local image,
and created container configuration have passed explicit isolation checks.
The candidate tree is the sole host bind mount and is read-only.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import uuid
from pathlib import Path


DEFAULT_IMAGE = "alice-devour-candidate:py314"
MEMORY_BYTES = 2 * 1024 * 1024 * 1024
CPU_NANOS = 2_000_000_000
PIDS_LIMIT = 128


class DockerCandidateRunner:
    """Run candidate pytest suites in a networkless, read-only container."""

    def __init__(self, image: str = DEFAULT_IMAGE, docker: str | None = None):
        self.image = image
        self.docker = docker or shutil.which("docker") or "docker"

    def _completed(self, code: int, message: str) -> subprocess.CompletedProcess[str]:
        result = subprocess.CompletedProcess([self.docker], code, "", message)
        result.sandbox_evidence = {"verified": False, "reason": message[-2000:]}
        return result

    def _docker(self, *args: str, timeout: int = 20) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            [self.docker, *args], capture_output=True, text=True, timeout=timeout,
        )

    def _image_id(self) -> tuple[str, list[str]]:
        info = self._docker("info", "--format", "{{.OSType}}")
        if info.returncode or info.stdout.strip().lower() != "linux":
            raise RuntimeError("Docker must provide a reachable Linux engine")
        security = self._docker("info", "--format", "{{json .SecurityOptions}}")
        try:
            security_options = json.loads(security.stdout)
        except (TypeError, ValueError) as exc:
            raise RuntimeError("Could not verify Docker seccomp and namespace support") from exc
        lowered_options = [str(option).lower() for option in security_options]
        if (security.returncode or not any("seccomp,profile=builtin" in option for option in lowered_options)
                or not any("cgroupns" in option for option in lowered_options)):
            raise RuntimeError("Docker must report its built-in seccomp profile and cgroup namespace isolation")
        image = self._docker("image", "inspect", "--format", "{{.Id}}", self.image)
        image_id = image.stdout.strip()
        if image.returncode or not image_id.startswith("sha256:"):
            raise RuntimeError(
                f"Required local sandbox image {self.image!r} is missing; build it with "
                "docker build -f docker/devour/Dockerfile -t alice-devour-candidate:py314 ."
            )
        return image_id, security_options

    def _create_args(self, stage: Path, name: str, test_paths: tuple[str, ...]) -> list[str]:
        selected_paths = json.dumps(list(test_paths))
        wrapper = (
            "import os,pathlib,sys; "
            "[pathlib.Path(p).mkdir(parents=True,exist_ok=True) for p in "
            "('/tmp/home','/tmp/profile/config','/tmp/profile/cache')]; "
            "os.execv(sys.executable,[sys.executable,'-m','pytest','-q','-p',"
            "'no:cacheprovider','--basetemp','/tmp/pytest',*"
            + selected_paths + "])"
        )
        args = [
            "create", "--pull=never", "--name", name,
            "--network=none", "--read-only", "--cap-drop=ALL",
            "--security-opt=no-new-privileges:true", "--pids-limit", str(PIDS_LIMIT),
            "--memory", str(MEMORY_BYTES), "--cpus", "2.0",
            "--user", "65532:65532", "--workdir", "/workspace",
            "--tmpfs", "/tmp:rw,nosuid,nodev,noexec,size=256m",
            "--mount", f"type=bind,source={stage},target=/workspace,readonly",
            "--env", "HOME=/tmp/home", "--env", "USERPROFILE=/tmp/home",
            "--env", "XDG_CONFIG_HOME=/tmp/profile/config",
            "--env", "XDG_CACHE_HOME=/tmp/profile/cache",
            "--env", "TMPDIR=/tmp", "--env", "TEMP=/tmp", "--env", "TMP=/tmp",
            "--env", "PYTHONDONTWRITEBYTECODE=1", "--env", "PYTHONNOUSERSITE=1",
            "--env", "PYTHON_DOTENV_DISABLED=1", "--env", "PYTEST_DISABLE_PLUGIN_AUTOLOAD=1",
            self.image, "python", "-c", wrapper,
        ]
        return args

    @staticmethod
    def _verify_container(inspect: dict, stage: Path) -> dict:
        config = inspect.get("Config") or {}
        host = inspect.get("HostConfig") or {}
        mounts = inspect.get("Mounts") or []
        bind_mounts = [mount for mount in mounts if mount.get("Type") == "bind"]
        tmpfs_mounts = [mount for mount in mounts if mount.get("Type") == "tmpfs"]
        security = [str(value).lower() for value in (host.get("SecurityOpt") or [])]
        tmpfs = host.get("Tmpfs") or {}
        workspace = bind_mounts[0] if len(bind_mounts) == 1 else {}
        temp = tmpfs_mounts[0] if len(tmpfs_mounts) == 1 else {}

        checks = {
            "non_root_user": config.get("User") == "65532:65532",
            "network_disabled": host.get("NetworkMode") == "none",
            "root_filesystem_read_only": host.get("ReadonlyRootfs") is True,
            "all_capabilities_dropped": "ALL" in (host.get("CapDrop") or []),
            "no_added_capabilities": not host.get("CapAdd"),
            "no_new_privileges": any("no-new-privileges" in item for item in security),
            "resource_limits": (
                host.get("Memory") == MEMORY_BYTES
                and host.get("NanoCpus") == CPU_NANOS
                and host.get("PidsLimit") == PIDS_LIMIT
            ),
            "only_candidate_bind_mount": (
                len(bind_mounts) == 1
                and workspace.get("Destination") == "/workspace"
                and Path(str(workspace.get("Source", "")).replace("\\", "/")).name.casefold()
                    == stage.name.casefold()
                and workspace.get("RW") is False
            ),
            "restricted_temporary_filesystem": (
                set(tmpfs) == {"/tmp"}
                and len(tmpfs_mounts) <= 1
                and (not tmpfs_mounts or (
                    temp.get("Destination") == "/tmp" and temp.get("RW") is True
                ))
                and all(option in str(tmpfs.get("/tmp", ""))
                        for option in ("nosuid", "nodev", "noexec", "size=256m"))
            ),
            "not_privileged_or_host_namespaced": (
                host.get("Privileged") is not True
                and host.get("PidMode") != "host"
                and host.get("IpcMode") != "host"
                and host.get("UsernsMode") != "host"
                and not host.get("Devices")
                and not host.get("DeviceRequests")
            ),
        }
        if not all(checks.values()):
            failed = ", ".join(name for name, passed in checks.items() if not passed)
            raise RuntimeError("Docker candidate sandbox restrictions were not applied: " + failed)
        return {"verified": True, "backend": "docker", "checks": checks}

    def run_tests(
        self, stage: str | Path, *, timeout: int = 240,
        test_paths: tuple[str, ...] | list[str] | None = None,
    ) -> subprocess.CompletedProcess[str]:
        stage = Path(stage).resolve(strict=True)
        if not stage.is_dir():
            return self._completed(125, "Candidate stage is not a directory")
        selected_paths = tuple(test_paths or ())
        for raw in selected_paths:
            rel = Path(str(raw).replace("\\", "/"))
            resolved = (stage / rel).resolve()
            if (rel.is_absolute() or ".." in rel.parts or str(raw).startswith("-"
                    ) or (stage not in resolved.parents and resolved != stage)
                    or not (resolved.is_file() or resolved.is_dir())):
                return self._completed(125, "Focused pytest paths must be existing files or directories within the candidate stage")
        name = "alice-candidate-" + uuid.uuid4().hex[:16]
        container_id = ""
        output = subprocess.CompletedProcess([self.docker], 125, "", "")
        try:
            image_id, security_options = self._image_id()
            created = self._docker(*self._create_args(stage, name, selected_paths), timeout=60)
            if created.returncode:
                return self._completed(125, created.stderr or created.stdout or "Docker create failed")
            container_id = created.stdout.strip()
            if not container_id:
                return self._completed(125, "Docker did not return a container id")
            raw = self._docker("inspect", container_id)
            if raw.returncode:
                return self._completed(125, raw.stderr or "Could not inspect candidate container")
            inspect = json.loads(raw.stdout)[0]
            evidence = self._verify_container(inspect, stage)
            evidence.update({
                "image": self.image,
                "image_id": image_id,
                "daemon_security_options": security_options,
                "checks": {**evidence["checks"], "daemon_seccomp_profile": True,
                           "daemon_cgroup_namespace": True},
                "container_id": container_id,
                "mounts": [
                    {"type": item.get("Type"), "destination": item.get("Destination"),
                     "read_only": item.get("RW") is False}
                    for item in inspect.get("Mounts", [])
                ],
            })
            try:
                started = self._docker("start", "--attach", container_id, timeout=timeout)
            except subprocess.TimeoutExpired as exc:
                self._docker("kill", container_id, timeout=10)
                out = exc.stdout.decode(errors="replace") if isinstance(exc.stdout, bytes) else (exc.stdout or "")
                err = exc.stderr.decode(errors="replace") if isinstance(exc.stderr, bytes) else (exc.stderr or "")
                output = subprocess.CompletedProcess([self.docker], 124, out, err or "candidate tests timed out")
                output.sandbox_evidence = evidence
                return output
            state = self._docker("inspect", "--format", "{{.State.ExitCode}}", container_id)
            if state.returncode or not state.stdout.strip().isdigit():
                return self._completed(125, state.stderr or "Could not verify candidate test exit status")
            output = subprocess.CompletedProcess(
                [self.docker, "start", "--attach", container_id],
                int(state.stdout.strip()), started.stdout or "", started.stderr or "",
            )
            output.sandbox_evidence = evidence
            return output
        except (OSError, subprocess.SubprocessError, ValueError, KeyError, TypeError, RuntimeError) as exc:
            return self._completed(125, str(exc))
        finally:
            if container_id:
                try:
                    self._docker("rm", "--force", container_id, timeout=15)
                except (OSError, subprocess.SubprocessError):
                    pass
