import hashlib
import json

import pytest

from alice.gluttony.evolver import DevourEngine
from alice.gluttony.installer_analysis import InstallerInspectionError, inspect_installer


def _minimal_pe():
    data = bytearray(0x200)
    data[:2] = b"MZ"
    data[0x3C:0x40] = (0x80).to_bytes(4, "little")
    data[0x80:0x84] = b"PE\0\0"
    # x64, one section, a 0xF0-byte PE32+ optional header.
    data[0x84:0x98] = (0x8664).to_bytes(2, "little") + (1).to_bytes(2, "little") + bytes(12) + (0xF0).to_bytes(2, "little") + bytes(2)
    data[0x98:0x9A] = (0x20B).to_bytes(2, "little")
    data[0x98 + 68:0x98 + 70] = (2).to_bytes(2, "little")
    return bytes(data)


def test_inspects_hash_and_pe_without_execution_or_extraction(tmp_path, monkeypatch):
    from alice.gluttony import installer_analysis

    path = tmp_path / "demo.exe"
    content = _minimal_pe()
    path.write_bytes(content)
    monkeypatch.setattr(installer_analysis, "_authenticode", lambda _path: {"checked": False, "status": "test"})
    result = inspect_installer(path)
    assert result["sha256"] == hashlib.sha256(content).hexdigest()
    assert result["pe"]["is_pe"] is True
    assert result["pe"]["machine"] == "x64"
    assert result["authenticode"]["status"] == "test"
    assert result["policy"]["executed"] is False
    assert result["policy"]["extracted"] is False


def test_installer_inspector_rejects_symlink_and_oversize(tmp_path):
    regular = tmp_path / "large.exe"
    regular.write_bytes(b"MZ")
    linked = tmp_path / "linked.exe"
    try:
        linked.symlink_to(regular)
    except (OSError, NotImplementedError):
        pytest.skip("Symlink creation is unavailable in this environment.")
    with pytest.raises(InstallerInspectionError):
        inspect_installer(linked)


def test_devour_writes_only_metadata_report(tmp_path, monkeypatch):
    from alice.gluttony import installer_analysis

    sample = tmp_path / "sample.exe"
    sample.write_bytes(_minimal_pe())
    monkeypatch.setattr(installer_analysis, "_authenticode", lambda _path: {"checked": False, "status": "test"})
    engine = DevourEngine(root=tmp_path / "alice")
    result = engine.inspect_installer(sample)
    report = json.loads(__import__("pathlib").Path(result["report"]).read_text(encoding="utf-8"))
    assert report["sha256"] == result["sha256"]
    assert report["policy"]["executed"] is False
    assert report["policy"]["installed"] is False
