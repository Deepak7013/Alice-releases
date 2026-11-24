import io
import json
import stat
import tarfile
import zipfile
from pathlib import Path

import pytest

from alice.gluttony.assimilation import AssimilationEngine
from alice.gluttony.evolver import DevourEngine
from alice.gluttony.intake import IntakeError, LocalInputAdapter
from alice.security.ingest_guard import IngestGuard


def test_devour_intake_stages_tar_gz_and_dependency_manifest(tmp_path):
    archive_path = tmp_path / "sample.tar.gz"
    with tarfile.open(archive_path, "w:gz") as archive:
        for name, content in {
            "sample/pyproject.toml": '[project]\nname="sample"\n',
            "sample/src/agent.py": "api_key = 'private-value'\ndef run():\n    return 'ok'\n",
            "sample/requirements.txt": "requests>=2.31\n",
        }.items():
            data = content.encode()
            member = tarfile.TarInfo(name)
            member.size = len(data)
            archive.addfile(member, io.BytesIO(data))

    engine = DevourEngine(
        tmp_path,
        gluttony=AssimilationEngine(tmp_path),
        self_manager=object(),
    )
    result = engine.devour(archive_path)
    report = json.loads(Path(result["report"]).read_text(encoding="utf-8"))

    assert result["status"] == "digested"
    assert Path(report["acquired_source"]).is_dir()
    assert IngestGuard().digest_tree(report["acquired_source"]) == report["tree_sha256"]
    assert report["acquisition"]["input_format"] == "tar"
    assert report["acquisition"]["files_copied"] == 3
    assert any(row["path"].endswith("agent.py") for row in report["architecture"]["modules"])
    assert "Python / PEP 517" in report["architecture"]["project"]["build_systems"]
    assert any(row["name"] == "requests" for row in report["architecture"]["project"]["dependencies"])
    snippet = next(row["content"] for row in report["source_samples"] if row["path"].endswith("agent.py"))
    assert "private-value" not in snippet and "[REDACTED]" in snippet
    assert engine.verify_single_postcondition({"source":str(archive_path)},result).ok is True

    report["license"]["kind"]="Forged"
    Path(result["report"]).write_text(json.dumps(report),encoding="utf-8")
    assert engine.verify_single_postcondition({"source":str(archive_path)},result).ok is False


@pytest.mark.parametrize("member_name", ["../escape.py", "/absolute.py", "C:/drive.py"])
def test_zip_archive_paths_cannot_escape_quarantine(tmp_path, member_name):
    archive = tmp_path / "unsafe.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(member_name, "print('unsafe')")
    work = tmp_path / "job"
    work.mkdir()

    with pytest.raises(IntakeError, match="Unsafe archive path"):
        LocalInputAdapter().stage(archive, work)
    assert not (tmp_path / "escape.py").exists()


def test_zip_symbolic_links_are_rejected(tmp_path):
    archive = tmp_path / "link.zip"
    info = zipfile.ZipInfo("project/link.py")
    info.create_system = 3
    info.external_attr = (stat.S_IFLNK | 0o777) << 16
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr(info, "../../outside.py")
    work = tmp_path / "job"
    work.mkdir()

    with pytest.raises(IntakeError, match="Non-regular ZIP member"):
        LocalInputAdapter().stage(archive, work)


def test_local_directory_skips_credentials_and_unneeded_dependency_trees(tmp_path):
    source = tmp_path / "project"
    (source / "src").mkdir(parents=True)
    (source / "node_modules" / "pkg").mkdir(parents=True)
    (source / "src" / "main.py").write_text("print('safe')", encoding="utf-8")
    (source / "go.mod").write_text("module example.org/test\n", encoding="utf-8")
    (source / "Agent.csproj").write_text("<Project />", encoding="utf-8")
    (source / ".env").write_text("API_KEY=do-not-copy", encoding="utf-8")
    (source / "node_modules" / "pkg" / "index.js").write_text("ignored", encoding="utf-8")
    work = tmp_path / "job"
    work.mkdir()

    result = LocalInputAdapter().stage(source, work)

    assert result.method == "local_directory"
    assert result.files_copied == 3
    assert (result.source / "src" / "main.py").is_file()
    assert (result.source / "go.mod").is_file()
    assert (result.source / "Agent.csproj").is_file()
    assert not (result.source / ".env").exists()
    assert not (result.source / "node_modules").exists()


def test_single_source_file_is_supported_and_sensitive_file_is_rejected(tmp_path):
    source = tmp_path / "module.py"
    source.write_text("def capability(): return True", encoding="utf-8")
    work = tmp_path / "job"
    work.mkdir()
    staged = LocalInputAdapter().stage(source, work)
    assert staged.method == "local_file"
    assert (staged.source / "module.py").read_text(encoding="utf-8") == source.read_text(encoding="utf-8")

    secret = tmp_path / ".env"
    secret.write_text("TOKEN=private", encoding="utf-8")
    next_work = tmp_path / "job2"
    next_work.mkdir()
    with pytest.raises(IntakeError, match="Credential and private-key"):
        LocalInputAdapter().stage(secret, next_work)


def test_intake_limits_are_enforced_before_copying(tmp_path):
    archive = tmp_path / "too-large.zip"
    with zipfile.ZipFile(archive, "w") as output:
        output.writestr("project.py", "123456")
    work = tmp_path / "job"
    work.mkdir()
    with pytest.raises(IntakeError, match="size limit"):
        LocalInputAdapter(max_total_bytes=5).stage(archive, work)


def test_ingest_guard_does_not_read_symlink_targets_outside_quarantine(tmp_path):
    source = tmp_path / "quarantine"
    source.mkdir()
    outside = tmp_path / "private.py"
    outside.write_text("password = 'never read'", encoding="utf-8")
    link = source / "external.py"
    try:
        link.symlink_to(outside)
    except (OSError, NotImplementedError):
        pytest.skip("symlink creation is not available")

    report = IngestGuard().scan_tree(source)

    assert report["files_scanned"] == 0
    assert report["symlinks_skipped"] == 1
    assert report["threat_count"] == 0


def test_public_github_archive_uses_default_branch_endpoint_and_safe_zip_staging(tmp_path, monkeypatch):
    import alice.gluttony.assimilation as assimilation_module

    payload = io.BytesIO()
    with zipfile.ZipFile(payload, "w") as archive:
        archive.writestr("repo-default/src/main.py", "def main(): return True")
        archive.writestr("repo-default/.env", "API_KEY=private")
        archive.writestr("repo-default/.git/config", "private origin config")
    payload.seek(0)

    class Response:
        status = 200
        headers = {"Content-Length": str(len(payload.getvalue()))}

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

        def geturl(self):
            return "https://codeload.github.com/owner/repo/legacy.zip/main"

        def read(self, size):
            return payload.read(size)

    called = {}

    def open_url(request, timeout):
        called["url"] = request.full_url
        called["timeout"] = timeout
        return Response()

    monkeypatch.setattr(assimilation_module.urllib.request, "urlopen", open_url)
    engine = AssimilationEngine(tmp_path)
    work = tmp_path / "job"
    work.mkdir()

    source = engine._download_zip("https://github.com/owner/repo", work)

    assert called["url"] == "https://api.github.com/repos/owner/repo/zipball"
    assert called["timeout"] == 60
    assert (source / "src" / "main.py").is_file()
    assert not (source / ".env").exists()
    assert not (source / ".git").exists()
    assert not (work / "repo.zip").exists()
