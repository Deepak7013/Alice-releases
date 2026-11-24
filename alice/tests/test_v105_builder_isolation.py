import subprocess

from alice.builder.isolation import DockerBuilderTestRunner


class FakeRunner:
    def __init__(self):
        self.calls = []
        self.staged_files = []

    def run_tests(self, stage, *, timeout, test_paths):
        self.calls.append((stage, timeout, test_paths))
        self.staged_files = sorted(path.name for path in stage.iterdir())
        result = subprocess.CompletedProcess(["docker"], 0, "1 passed", "")
        result.sandbox_evidence = {"verified": True, "backend": "docker"}
        return result


def test_runner_copies_only_generated_project_and_excludes_secrets(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    (project / "test_app.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    (project / ".env").write_text("TOKEN=private\n", encoding="utf-8")
    (project / "identity.pem").write_text("private key\n", encoding="utf-8")
    runner = FakeRunner()

    result = DockerBuilderTestRunner(runner).run(project, "pytest -q test_app.py")

    assert result.returncode == 0
    assert result.sandbox_evidence["verified"] is True
    assert result.sandbox_evidence["generated_project_copy_only"] is True
    assert result.sandbox_evidence["project_files_writable_to_test"] is False
    staged, timeout, paths = runner.calls[0]
    assert staged != project
    assert paths == ("test_app.py",)
    assert timeout == 240
    assert runner.staged_files == ["test_app.py"]


def test_runner_rejects_non_pytest_commands_without_running_them(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    runner = FakeRunner()
    result = DockerBuilderTestRunner(runner).run(project, "python -c 'print(1)'")
    assert result.returncode != 0
    assert result.sandbox_evidence["verified"] is False
    assert not runner.calls


def test_runner_rejects_path_escape_and_pytest_code_loading_options(tmp_path):
    project = tmp_path / "project"
    project.mkdir()
    runner = FakeRunner()
    isolated = DockerBuilderTestRunner(runner)
    assert isolated.run(project, "pytest ..\\secret.py").returncode != 0
    assert isolated.run(project, "pytest -p malicious_plugin").returncode != 0
    assert not runner.calls


def test_runner_accepts_supported_python_pytest_module_command(tmp_path):
    project = tmp_path / "project"
    (project / "tests").mkdir(parents=True)
    (project / "tests" / "test_ok.py").write_text("def test_ok(): assert True\n", encoding="utf-8")
    runner = FakeRunner()
    result = DockerBuilderTestRunner(runner).run(project, "python -m pytest -q tests")
    assert result.returncode == 0
    assert runner.calls[0][2] == ("tests",)
