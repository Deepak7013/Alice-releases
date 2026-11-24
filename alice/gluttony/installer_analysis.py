"""Read-only metadata inspection for Windows installers; never launches them."""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
from pathlib import Path


class InstallerInspectionError(ValueError):
    pass


MAX_INSTALLER_BYTES = 2_000_000_000
CHUNK = 1024 * 1024


def _pe_metadata(path: Path) -> dict:
    result = {"is_pe": False, "machine": None, "sections": None,
              "optional_header": None, "subsystem": None}
    with path.open("rb") as stream:
        if stream.read(2) != b"MZ":
            return result
        stream.seek(0x3C)
        raw = stream.read(4)
        if len(raw) != 4:
            return result
        offset = struct.unpack("<I", raw)[0]
        if offset > min(path.stat().st_size - 24, 16 * 1024 * 1024):
            return result
        stream.seek(offset)
        header = stream.read(24)
        if len(header) < 24 or header[:4] != b"PE\0\0":
            return result
        machine, sections, _time, _sym, _nsym, opt_size, _flags = struct.unpack("<HHIIIHH", header[4:24])
        stream.seek(offset + 24)
        optional = stream.read(min(opt_size, 256))
        magic = struct.unpack("<H", optional[:2])[0] if len(optional) >= 2 else None
        subsystem = struct.unpack("<H", optional[68:70])[0] if len(optional) >= 70 else None
        result.update({"is_pe": True,
            "machine": {0x014C: "x86", 0x8664: "x64", 0xAA64: "ARM64"}.get(machine, f"unknown:0x{machine:04x}"),
            "sections": sections,
            "optional_header": {0x10B: "PE32", 0x20B: "PE32+"}.get(magic, "unknown"),
            "subsystem": {2: "Windows GUI", 3: "Windows console"}.get(subsystem, f"unknown:{subsystem}" if subsystem is not None else None),
        })
    return result


def _authenticode(path: Path) -> dict:
    if os.name != "nt":
        return {"checked": False, "status": "unavailable outside Windows"}
    shell = shutil.which("pwsh.exe") or shutil.which("powershell.exe")
    if not shell:
        return {"checked": False, "status": "PowerShell is unavailable"}
    env = os.environ.copy()
    env["ALICE_INSTALLER_INSPECT_PATH"] = str(path)
    command = ("$s=Get-AuthenticodeSignature -LiteralPath $env:ALICE_INSTALLER_INSPECT_PATH; "
               "$signer=$null; $thumbprint=$null; "
               "if($s.SignerCertificate){$signer=$s.SignerCertificate.Subject; $thumbprint=$s.SignerCertificate.Thumbprint}; "
               "[pscustomobject]@{Status=[string]$s.Status; StatusMessage=[string]$s.StatusMessage; "
               "Signer=$signer; Thumbprint=$thumbprint} | ConvertTo-Json -Compress")
    try:
        completed = subprocess.run([shell, "-NoProfile", "-NonInteractive", "-Command", command],
            env=env, capture_output=True, text=True, timeout=12, check=False,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
        if completed.returncode != 0 or completed.stderr.strip():
            return {"checked": False, "status": "signature check failed", "detail": "PowerShell returned an error."}
        value = json.loads(completed.stdout.strip()) if completed.stdout.strip() else {}
        return {"checked": bool(value.get("Status")), "status": str(value.get("Status") or "Unknown")[:80],
            "status_message": str(value.get("StatusMessage") or "")[:240],
            "signer": str(value.get("Signer"))[:240] if value.get("Signer") else None,
            "thumbprint": str(value.get("Thumbprint"))[:80] if value.get("Thumbprint") else None}
    except Exception as exc:
        return {"checked": False, "status": "signature check unavailable",
                "detail": type(exc).__name__}


def inspect_installer(path: str | os.PathLike) -> dict:
    """Hash and inspect bounded executable metadata without extraction or execution."""
    raw = Path(path).expanduser()
    try:
        resolved = raw.resolve(strict=True)
    except OSError as exc:
        raise InstallerInspectionError("Installer path does not exist or cannot be read.") from exc
    if raw.is_symlink() or not resolved.is_file():
        raise InstallerInspectionError("Choose a regular installer file, not a link or folder.")
    size = resolved.stat().st_size
    if size <= 0 or size > MAX_INSTALLER_BYTES:
        raise InstallerInspectionError("Installer must be between 1 byte and 2 GB for static inspection.")
    digest = hashlib.sha256()
    with resolved.open("rb") as stream:
        for block in iter(lambda: stream.read(CHUNK), b""):
            digest.update(block)
    return {
        "ok": True,
        "inspection": "read_only_installer_metadata",
        "file_name": resolved.name[:240],
        "file_size_bytes": size,
        "sha256": digest.hexdigest(),
        "pe": _pe_metadata(resolved),
        "authenticode": _authenticode(resolved),
        "policy": {
            "executed": False,
            "extracted": False,
            "installed": False,
            "static_metadata_only": True,
            "full_file_contents_or_embedded_models_analyzed": False,
        },
        "next_step": "Use a separate sandboxed archive inspection to enumerate package contents; review licenses before copying code, models, or assets.",
    }
