import json
import shutil
import subprocess
from pathlib import Path

import pytest


@pytest.mark.skipif(shutil.which("powershell.exe") is None, reason="Windows PowerShell is required")
def test_installer_discovery_finds_latest_valid_prior_install_and_excludes_target(tmp_path):
    module_path = Path(__file__).parents[1] / "deployment" / "install_discovery.psm1"
    assert module_path.is_file()

    search_root = tmp_path / "C"
    search_root.mkdir()

    def install(folder, version_text):
        directory = search_root / folder
        directory.mkdir()
        (directory / "VERSION.txt").write_text(version_text + "\n", encoding="utf-8")
        return str(directory)

    oldest = install("Alice_v4.105.0", "ALICE v4.105.0")
    latest = install("Alice_v4.110.3", "ALICE v4.110.3")
    install("Alice_v9.0.0", "ALICE v9.0.0")
    install("Alice_v4.109.0", "ALICE v4.108.9")
    target = install("Alice_v5.0.0", "ALICE v5.0.0")

    harness = tmp_path / "discover.ps1"
    harness.write_text(
        "$ErrorActionPreference = 'Stop'\n"
        "Import-Module -Name $env:ALICE_DISCOVERY_MODULE -Force\n"
        "$found = @(Get-PreviousAliceInstallCandidates -SearchRoot $env:ALICE_DISCOVERY_ROOT "
        "-TargetRoot $env:ALICE_DISCOVERY_TARGET -PackageVersion 'ALICE v5.0.0')\n"
        "$found | ConvertTo-Json -Compress\n",
        encoding="utf-8",
    )
    import os

    env = os.environ.copy()
    env.update(
        {
            "ALICE_DISCOVERY_MODULE": str(module_path),
            "ALICE_DISCOVERY_ROOT": str(search_root),
            "ALICE_DISCOVERY_TARGET": target,
        }
    )
    result = subprocess.run(
        [shutil.which("powershell.exe"), "-NoProfile", "-NonInteractive", "-File", str(harness)],
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip(), result.stderr
    actual = json.loads(result.stdout.strip().splitlines()[-1])
    assert actual == [latest, oldest]
