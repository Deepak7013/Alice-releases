import json

from alice.maintenance.candidate_container import (
    CPU_NANOS,
    MEMORY_BYTES,
    PIDS_LIMIT,
    DockerCandidateRunner,
)


def _inspect(stage):
    return {
        "Config": {"User": "65532:65532"},
        "HostConfig": {
            "NetworkMode": "none",
            "ReadonlyRootfs": True,
            "CapDrop": ["ALL"],
            "CapAdd": None,
            "SecurityOpt": ["no-new-privileges=true"],
            "PidsLimit": PIDS_LIMIT,
            "Memory": MEMORY_BYTES,
            "NanoCpus": CPU_NANOS,
            "Privileged": False,
            "PidMode": "",
            "IpcMode": "private",
            "Devices": None,
            "DeviceRequests": None,
            "Tmpfs": {"/tmp": "rw,noexec,nosuid,nodev,size=256m"},
        },
        "Mounts": [
            {"Type": "bind", "Source": str(stage), "Destination": "/workspace", "RW": False},
            {"Type": "tmpfs", "Source": "", "Destination": "/tmp", "RW": True},
        ],
    }


def test_runner_checks_restrictions_before_start_and_records_evidence(tmp_path, monkeypatch):
    stage = tmp_path / "candidate"
    stage.mkdir()
    calls = []
    container_id = "f" * 64

    def fake_run(command, *, capture_output, text, timeout):
        calls.append(command)
        args = command[1:]
        if args == ["info", "--format", "{{.OSType}}"]:
            return type("Result", (), {"returncode": 0, "stdout": "linux\n", "stderr": ""})()
        if args == ["info", "--format", "{{json .SecurityOptions}}"]:
            return type("Result", (), {
                "returncode": 0,
                "stdout": '["name=seccomp,profile=builtin","name=cgroupns"]',
                "stderr": "",
            })()
        if args[:2] == ["image", "inspect"]:
            return type("Result", (), {"returncode": 0, "stdout": "sha256:" + "a" * 64, "stderr": ""})()
        if args[0] == "create":
            return type("Result", (), {"returncode": 0, "stdout": container_id, "stderr": ""})()
        if args == ["inspect", container_id]:
            return type("Result", (), {
                "returncode": 0, "stdout": json.dumps([_inspect(stage)]), "stderr": "",
            })()
        if args == ["start", "--attach", container_id]:
            return type("Result", (), {"returncode": 0, "stdout": "8 passed", "stderr": ""})()
        if args == ["inspect", "--format", "{{.State.ExitCode}}", container_id]:
            return type("Result", (), {"returncode": 0, "stdout": "0\n", "stderr": ""})()
        if args == ["rm", "--force", container_id]:
            return type("Result", (), {"returncode": 0, "stdout": "", "stderr": ""})()
        raise AssertionError(command)

    monkeypatch.setattr("alice.maintenance.candidate_container.subprocess.run", fake_run)
    result = DockerCandidateRunner().run_tests(stage)

    assert result.returncode == 0
    assert result.sandbox_evidence["verified"] is True
    assert result.sandbox_evidence["image_id"] == "sha256:" + "a" * 64
    assert result.sandbox_evidence["checks"]["network_disabled"] is True
    create = next(call for call in calls if call[1] == "create")
    assert "--network=none" in create
    assert "--read-only" in create
    assert "--cap-drop=ALL" in create
    assert "--security-opt=no-new-privileges:true" in create
    assert "--pull=never" in create
    assert not any("/var/run/docker.sock" in value for value in create)
    assert calls.index(create) < next(i for i, call in enumerate(calls) if call[1:3] == ["start", "--attach"])
    assert calls[-1][1:] == ["rm", "--force", container_id]


def test_runner_fails_closed_when_docker_is_not_a_linux_engine(tmp_path, monkeypatch):
    stage = tmp_path / "candidate"
    stage.mkdir()
    calls = []

    def fake_run(command, **kwargs):
        calls.append(command)
        return type("Result", (), {"returncode": 0, "stdout": "windows\n", "stderr": ""})()

    monkeypatch.setattr("alice.maintenance.candidate_container.subprocess.run", fake_run)
    result = DockerCandidateRunner().run_tests(stage)

    assert result.returncode != 0
    assert result.sandbox_evidence["verified"] is False
    assert not any(call[1] == "create" for call in calls)


def test_container_policy_rejects_network_or_writable_candidate_mount(tmp_path):
    stage = tmp_path / "candidate"
    stage.mkdir()
    inspect = _inspect(stage)
    inspect["HostConfig"]["NetworkMode"] = "bridge"

    try:
        DockerCandidateRunner._verify_container(inspect, stage)
    except RuntimeError as exc:
        assert "network_disabled" in str(exc)
    else:
        raise AssertionError("weaker Docker restrictions must reject candidate execution")

    inspect = _inspect(stage)
    inspect["Mounts"][0]["RW"] = True
    try:
        DockerCandidateRunner._verify_container(inspect, stage)
    except RuntimeError as exc:
        assert "only_candidate_bind_mount" in str(exc)
    else:
        raise AssertionError("a writable host mount must reject candidate execution")
