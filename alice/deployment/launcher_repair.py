"""Repair ALICE's Windows launcher to point at the active installation root."""
from __future__ import annotations
import os
import subprocess
from pathlib import Path


def repair_windows_launchers(root: str | Path, *, start_visible: bool = False) -> dict:
    """Repair desktop shortcut + logon task using *root*, never a hard-coded version.

    This is deliberately idempotent. It is safe to call after every successful
    in-place upgrade, including upgrades performed inside an older folder such
    as C:\\Alice_v3.33.0.
    """
    root = Path(root).expanduser().resolve()
    pyw = root / ".venv" / "Scripts" / "pythonw.exe"
    py = root / ".venv" / "Scripts" / "python.exe"
    launcher = pyw if pyw.exists() else py
    if not launcher.exists():
        raise RuntimeError(f"ALICE Python launcher not found under {root}")
    if os.name != "nt":
        return {"ok": True, "platform": "non-windows", "root": str(root)}

    # Use PowerShell only for the two Windows-native shell integrations. The
    # application itself remains Python; no version-specific path is embedded.
    ps = r'''$ErrorActionPreference = "Stop"
$root = [Environment]::GetEnvironmentVariable("ALICE_REPAIR_ROOT", "Process")
$pythonw = [Environment]::GetEnvironmentVariable("ALICE_REPAIR_PYTHONW", "Process")
$desktop = [Environment]::GetFolderPath("Desktop")
$ws = New-Object -ComObject WScript.Shell
$link = $ws.CreateShortcut((Join-Path $desktop "Alice - Restart.lnk"))
$link.TargetPath = $pythonw
$link.Arguments = "-m alice --show"
$link.WorkingDirectory = $root
$link.Description = "Start Alice Gluttony"
$link.Hotkey = "CTRL+ALT+A"
$link.Save()

# One authoritative logon owner. Existing legacy Startup-folder helper is removed.
schtasks /Delete /TN "ALICE Gluttony" /F | Out-Null
$taskAction = '"' + $pythonw + '" -m alice.desktop.launcher'
schtasks /Create /TN "ALICE Gluttony" /SC ONLOGON /TR $taskAction /F | Out-Null
$startupDir = Join-Path $env:APPDATA "Microsoft\Windows\Start Menu\Programs\Startup"
foreach ($legacy in @("Alice Launcher.lnk", "ALICE Launcher.lnk", "Alice.lnk", "ALICE.lnk")) {
  $p = Join-Path $startupDir $legacy
  if (Test-Path $p) { Remove-Item -Force $p }
}
foreach ($legacy in @("Alice.lnk", "ALICE.lnk")) {
  $p = Join-Path $desktop $legacy
  if (Test-Path $p) { Remove-Item -Force $p }
}
'''
    env = os.environ.copy()
    env["ALICE_REPAIR_ROOT"] = str(root)
    env["ALICE_REPAIR_PYTHONW"] = str(launcher)
    r = subprocess.run(["powershell", "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass", "-Command", ps],
                       env=env, capture_output=True, text=True, timeout=30)
    if r.returncode:
        raise RuntimeError((r.stderr or r.stdout or "Windows launcher repair failed").strip())
    if start_visible:
        flags = getattr(subprocess, "DETACHED_PROCESS", 0) | getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
        subprocess.Popen([str(launcher), "-m", "alice", "--show"], cwd=str(root), creationflags=flags)
    return {"ok": True, "root": str(root), "shortcut": "Alice - Restart.lnk", "task": "ALICE Gluttony", "started": bool(start_visible)}
