"""Fail-closed Ed25519 verification for externally supplied ALICE updates.

Private release keys are never stored by ALICE.  A trusted installation must
pin a publisher public key out of band before a package can be scheduled.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import platform
import re
import sys
import tempfile
import time
import unicodedata
import zipfile
from pathlib import Path, PurePosixPath

from .updater import UpgradeError, InPlaceUpdater, read_version, sha256_file, version_tuple

MAX_MANIFEST_BYTES = 256 * 1024
MAX_PACKAGE_BYTES = 512 * 1024 * 1024
MAX_EXPANDED_BYTES = 2 * 1024 * 1024 * 1024
MAX_FILE_BYTES = 512 * 1024 * 1024
MAX_FILES = 20_000
_MANIFEST_FIELDS = {
    "schema", "product", "channel", "version", "sequence", "platform",
    "minimum_os", "minimum_runtime", "minimum_supported_version", "package", "files",
    "release_notes", "migrations", "key_id",
}
_JOURNAL_STATES = {
    "IDLE", "CHECKING", "AVAILABLE", "DOWNLOADING", "STAGED", "VERIFIED",
    "BACKED_UP", "APPLYING", "HEALTH_CHECK", "ACCEPTED", "FAILED",
    "ROLLING_BACK", "ROLLED_BACK",
}


def _assert_no_reparse(path: Path) -> None:
    """Reject symlink/junction/reparse components used as a trust boundary."""
    absolute = path.absolute()
    current = Path(absolute.anchor)
    for part in absolute.parts[1:]:
        current = current / part
        try:
            if not current.exists() and not current.is_symlink():
                continue
            stat = current.lstat()
            attributes = getattr(stat, "st_file_attributes", 0)
            is_junction = getattr(current, "is_junction", lambda: False)()
            if current.is_symlink() or is_junction or attributes & 0x400:
                raise UpgradeError(f"Update trust path contains a reparse point: {current}")
        except FileNotFoundError:
            continue


def _pairs_no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise UpgradeError(f"Duplicate JSON key: {key}")
        result[key] = value
    return result


def strict_json_loads(raw: bytes | str, *, limit: int = MAX_MANIFEST_BYTES):
    if isinstance(raw, bytes):
        if len(raw) > limit:
            raise UpgradeError("Signed update manifest exceeds its size limit")
        try:
            raw = raw.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise UpgradeError("Signed update manifest is not UTF-8") from exc
    elif len(raw.encode("utf-8")) > limit:
        raise UpgradeError("Signed update manifest exceeds its size limit")
    try:
        return json.loads(
            raw,
            object_pairs_hook=_pairs_no_duplicates,
            parse_constant=lambda value: (_ for _ in ()).throw(UpgradeError(f"Non-finite JSON value: {value}")),
        )
    except UpgradeError:
        raise
    except Exception as exc:
        raise UpgradeError(f"Invalid signed update JSON: {exc}") from exc


def canonical_manifest_bytes(manifest: dict) -> bytes:
    try:
        return json.dumps(manifest, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False).encode("utf-8")
    except (TypeError, ValueError) as exc:
        raise UpgradeError(f"Manifest cannot be canonicalized: {exc}") from exc


def create_signed_update_envelope(
    package_path: str | Path,
    private_key,
    *,
    package_url: str,
    channel: str,
    sequence: int,
    platform_name: str,
    minimum_os: str,
    minimum_runtime: str,
    minimum_supported_version: str,
    release_notes: str,
) -> dict:
    """Create a detached signed manifest using a caller-held Ed25519 key.

    This function never loads, stores or serializes the private key. Release
    tooling must keep that key outside the ALICE tree and pass it in memory.
    """
    try:
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
    except ImportError as exc:
        raise UpgradeError("Release signing dependency missing; install cryptography") from exc
    if not isinstance(private_key, Ed25519PrivateKey):
        raise UpgradeError("Release signing requires an Ed25519 private key")
    package_file = Path(package_path).expanduser().absolute()
    _assert_no_reparse(package_file)
    if not package_file.is_file() or package_file.suffix.lower() != ".zip":
        raise UpgradeError("Release package must be an existing ZIP")
    if package_file.stat().st_size > MAX_PACKAGE_BYTES:
        raise UpgradeError("Release package exceeds the maximum size")
    if not isinstance(package_url, str) or not package_url.lower().startswith("https://"):
        raise UpgradeError("Signed release package URL must use HTTPS")
    if channel not in {"stable", "beta", "dev"}:
        raise UpgradeError("Unsupported release channel")
    if isinstance(sequence, bool) or not isinstance(sequence, int) or not 1 <= sequence <= 2**63 - 1:
        raise UpgradeError("Invalid release sequence")
    if not isinstance(release_notes, str) or len(release_notes) > 50_000:
        raise UpgradeError("Invalid or oversized release notes")
    _runtime_version(minimum_runtime)
    if minimum_os != "any" and not re.fullmatch(r"\d+(?:\.\d+){1,2}", str(minimum_os)):
        raise UpgradeError("Invalid minimum OS version")
    if platform_name != "any" and not re.fullmatch(r"[a-z0-9]+-[a-z0-9]+", str(platform_name)):
        raise UpgradeError("Invalid release platform")
    if not re.fullmatch(r"ALICE v\d+\.\d+(?:\.\d+)?", str(minimum_supported_version)):
        raise UpgradeError("Invalid minimum supported ALICE version")

    try:
        with zipfile.ZipFile(package_file) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES + 1:
                raise UpgradeError("Release ZIP contains too many entries")
            seen = set()
            file_infos = {}
            expanded = 0
            for info in infos:
                raw = info.filename
                name = raw[:-1] if raw.endswith("/") else raw
                rel = _safe_relative_path(name)
                folded = _path_key(rel)
                if folded in seen:
                    raise UpgradeError(f"Duplicate normalized release ZIP path: {rel}")
                seen.add(folded)
                mode = (info.external_attr >> 16) & 0o170000
                if mode and mode not in (0o100000, 0o040000):
                    raise UpgradeError(f"Release ZIP contains a symlink or special file: {rel}")
                if info.flag_bits & 0x1:
                    raise UpgradeError("Encrypted release ZIP members are not supported")
                if info.file_size > MAX_FILE_BYTES:
                    raise UpgradeError(f"Release ZIP member exceeds its size limit: {rel}")
                expanded += info.file_size
                if expanded > MAX_EXPANDED_BYTES:
                    raise UpgradeError("Release ZIP expanded size exceeds its limit")
                if not info.is_dir():
                    file_infos[folded] = info
            info = file_infos.get("upgrade_manifest.json")
            if info is None or info.file_size > MAX_MANIFEST_BYTES:
                raise UpgradeError("Release ZIP upgrade manifest is missing or oversized")
            if archive.testzip() is not None:
                raise UpgradeError("Release ZIP CRC verification failed")
            internal = strict_json_loads(archive.read(info))
            if not isinstance(internal, dict) or internal.get("format") != 1 or internal.get("product") != "ALICE":
                raise UpgradeError("Unsupported release upgrade manifest")
            version = internal.get("version")
            if not isinstance(version, str) or not re.fullmatch(r"ALICE v\d+\.\d+(?:\.\d+)?", version):
                raise UpgradeError("Malformed ALICE release version")
            rows = internal.get("files")
            if not isinstance(rows, list) or not rows or len(rows) > MAX_FILES:
                raise UpgradeError("Release package file inventory is empty or oversized")
            signed_rows = []
            expected_paths = {"upgrade_manifest.json"}
            total_size = 0
            for row in rows:
                if not isinstance(row, dict):
                    raise UpgradeError("Release package file record is malformed")
                rel = _safe_relative_path(row.get("path"))
                folded = _path_key(rel)
                if folded in expected_paths:
                    raise UpgradeError(f"Duplicate release file path: {rel}")
                expected_paths.add(folded)
                digest = row.get("sha256")
                size = row.get("size")
                if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
                    raise UpgradeError(f"Invalid release file digest: {rel}")
                if isinstance(size, bool) or not isinstance(size, int) or not 0 <= size <= MAX_FILE_BYTES:
                    raise UpgradeError(f"Invalid release file size: {rel}")
                total_size += size
                if total_size > MAX_EXPANDED_BYTES:
                    raise UpgradeError("Release file inventory exceeds expanded size limit")
                archived = file_infos.get(folded)
                if archived is None or archived.file_size != size:
                    raise UpgradeError(f"Release ZIP file missing or size mismatch: {rel}")
                digest_check = hashlib.sha256()
                actual_size = 0
                with archive.open(archived) as stream:
                    for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                        digest_check.update(chunk)
                        actual_size += len(chunk)
                if actual_size != size or digest_check.hexdigest() != digest:
                    raise UpgradeError(f"Release ZIP file hash mismatch: {rel}")
                signed_rows.append({"path": rel, "sha256": digest, "size": size})
            if set(file_infos) != expected_paths:
                raise UpgradeError("Release ZIP contents do not exactly match its file manifest")
    except zipfile.BadZipFile as exc:
        raise UpgradeError("Release package is not a valid ZIP") from exc

    public = private_key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
    manifest = {
        "schema": 1,
        "product": "ALICE",
        "channel": channel,
        "version": version,
        "sequence": sequence,
        "platform": platform_name,
        "minimum_os": minimum_os,
        "minimum_runtime": minimum_runtime,
        "minimum_supported_version": minimum_supported_version,
        "package": {"url": package_url, "sha256": sha256_file(package_file), "size": package_file.stat().st_size},
        "files": signed_rows,
        "release_notes": release_notes,
        "migrations": [],
        "key_id": hashlib.sha256(public).hexdigest(),
    }
    signature = private_key.sign(canonical_manifest_bytes(manifest))
    return {"manifest": manifest, "signature": base64.b64encode(signature).decode("ascii")}


def _crypto():
    try:
        from cryptography.exceptions import InvalidSignature
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
    except ImportError as exc:
        raise UpgradeError("Ed25519 verification dependency missing; install the project's cryptography requirement") from exc
    return Ed25519PublicKey, InvalidSignature


def _runtime_platform() -> str:
    system = platform.system().lower()
    machine = platform.machine().lower()
    aliases = {"amd64": "amd64", "x86_64": "amd64", "arm64": "arm64", "aarch64": "arm64", "x86": "x86"}
    return f"{system}-{aliases.get(machine, machine)}"


def _runtime_version(value: str) -> tuple[int, ...]:
    if not isinstance(value, str) or not re.fullmatch(r"\d+(?:\.\d+){1,2}", value):
        raise UpgradeError("Invalid minimum Python runtime version")
    return tuple(int(part) for part in value.split("."))


def _safe_relative_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or ":" in value:
        raise UpgradeError("Invalid signed package path")
    path = PurePosixPath(value)
    parts = value.split("/")
    reserved = {"CON", "PRN", "AUX", "NUL", *(f"COM{i}" for i in range(1, 10)), *(f"LPT{i}" for i in range(1, 10))}
    if path.is_absolute() or value.startswith("//") or any(part in ("", ".", "..") for part in parts):
        raise UpgradeError(f"Unsafe signed package path: {value}")
    if any(part.endswith((" ", ".")) or part.split(".", 1)[0].upper() in reserved for part in parts):
        raise UpgradeError(f"Windows-reserved package path: {value}")
    return path.as_posix()


def _path_key(value: str) -> str:
    return unicodedata.normalize("NFC", value).casefold()


class SignedUpdateVerifier:
    """Verify signed envelopes, pinned keys, package inventories and sequence."""

    def __init__(self, root: str | Path):
        requested = Path(root).expanduser().absolute()
        _assert_no_reparse(requested)
        self.root = requested.resolve()
        self.runtime = self.root / "alice_workspace" / "runtime"
        self.key_store = self.runtime / "trusted_update_keys.json"
        self.sequence_store = self.runtime / "update_sequence.json"

    def trusted_keys(self) -> dict[str, bytes]:
        _assert_no_reparse(self.key_store)
        if not self.key_store.exists():
            return {}
        data = strict_json_loads(self.key_store.read_bytes())
        if not isinstance(data, dict) or set(data) != {"schema", "keys"} or data.get("schema") != 1 or not isinstance(data.get("keys"), list):
            raise UpgradeError("Trusted update key store is malformed; refusing update")
        result = {}
        for row in data["keys"]:
            if not isinstance(row, dict) or set(row) != {"key_id", "public_key"}:
                raise UpgradeError("Trusted update key record is malformed")
            try:
                public = base64.b64decode(row["public_key"], validate=True)
            except Exception as exc:
                raise UpgradeError("Trusted update public key is malformed") from exc
            key_id = hashlib.sha256(public).hexdigest()
            if len(public) != 32 or row["key_id"] != key_id or key_id in result:
                raise UpgradeError("Trusted update key fingerprint is invalid or duplicated")
            result[key_id] = public
        return result

    def verify_envelope(self, envelope: dict, *, expected_channel: str = "stable") -> dict:
        if not isinstance(envelope, dict) or set(envelope) != {"manifest", "signature"}:
            raise UpgradeError("Update must contain only a signed manifest and signature")
        manifest = envelope["manifest"]
        if not isinstance(manifest, dict) or set(manifest) != _MANIFEST_FIELDS:
            raise UpgradeError("Signed update manifest has missing or unknown fields")
        if manifest.get("schema") != 1 or manifest.get("product") != "ALICE":
            raise UpgradeError("Unsupported signed update product or schema")
        if manifest.get("channel") != expected_channel:
            raise UpgradeError("Update release channel does not match the configured channel")
        version = manifest.get("version")
        if not isinstance(version, str) or not re.fullmatch(r"ALICE v\d+\.\d+(?:\.\d+)?", version):
            raise UpgradeError("Malformed ALICE update version")
        sequence = manifest.get("sequence")
        if isinstance(sequence, bool) or not isinstance(sequence, int) or not 1 <= sequence <= 2**63 - 1:
            raise UpgradeError("Invalid monotonically increasing update sequence")
        package = manifest.get("package")
        if not isinstance(package, dict) or set(package) != {"url", "sha256", "size"}:
            raise UpgradeError("Signed package metadata is incomplete")
        url, digest, size = package["url"], package["sha256"], package["size"]
        if not isinstance(url, str) or (url and not url.lower().startswith("https://")):
            raise UpgradeError("Signed update package URL must use HTTPS")
        if not isinstance(digest, str) or not re.fullmatch(r"[0-9a-f]{64}", digest):
            raise UpgradeError("Invalid signed package SHA-256")
        if isinstance(size, bool) or not isinstance(size, int) or not 1 <= size <= MAX_PACKAGE_BYTES:
            raise UpgradeError("Signed update package exceeds its size limit")
        if manifest.get("platform") not in ("any", _runtime_platform()):
            raise UpgradeError("Signed update does not support this operating system and architecture")
        minimum_os = manifest.get("minimum_os")
        if not isinstance(minimum_os, str) or (minimum_os != "any" and not re.fullmatch(r"\d+(?:\.\d+){1,2}", minimum_os)):
            raise UpgradeError("Invalid minimum operating system version")
        if minimum_os != "any":
            if platform.system().lower() != "windows" or not hasattr(sys, "getwindowsversion"):
                raise UpgradeError("Signed update requires Windows")
            required_os = tuple(int(part) for part in minimum_os.split("."))
            current_os = tuple(sys.getwindowsversion()[:len(required_os)])
            if current_os < required_os:
                raise UpgradeError("This update requires a newer Windows version")
        minimum_runtime = _runtime_version(manifest.get("minimum_runtime"))
        if tuple(__import__("sys").version_info[:len(minimum_runtime)]) < minimum_runtime:
            raise UpgradeError("This update requires a newer Python runtime")
        minimum_prior = manifest.get("minimum_supported_version")
        if not isinstance(minimum_prior, str) or not re.fullmatch(r"ALICE v\d+\.\d+(?:\.\d+)?", minimum_prior):
            raise UpgradeError("Invalid minimum supported ALICE version")
        if version_tuple(read_version(self.root)) < version_tuple(minimum_prior):
            raise UpgradeError(f"This update requires {minimum_prior} or newer")
        notes = manifest.get("release_notes")
        if not isinstance(notes, str) or len(notes) > 50_000:
            raise UpgradeError("Invalid or oversized release notes")
        migrations = manifest.get("migrations")
        if not isinstance(migrations, list) or len(migrations) > 100 or any(not isinstance(m, str) or not re.fullmatch(r"[a-z0-9_.-]{1,80}", m) for m in migrations):
            raise UpgradeError("Invalid migration declarations")
        if migrations:
            raise UpgradeError("This ALICE build has no reviewed migration handlers; refusing automatic migration")
        files = manifest.get("files")
        if not isinstance(files, list) or not files or len(files) > MAX_FILES:
            raise UpgradeError("Signed package file inventory is empty or oversized")
        normalized = set()
        total_size = 0
        for item in files:
            if not isinstance(item, dict) or set(item) != {"path", "sha256", "size"}:
                raise UpgradeError("Signed package file record is malformed")
            rel = _safe_relative_path(item["path"])
            folded = _path_key(rel)
            if folded in normalized:
                raise UpgradeError(f"Duplicate normalized package path: {rel}")
            normalized.add(folded)
            if not isinstance(item["sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", item["sha256"]):
                raise UpgradeError(f"Invalid file digest: {rel}")
            if isinstance(item["size"], bool) or not isinstance(item["size"], int) or not 0 <= item["size"] <= MAX_FILE_BYTES:
                raise UpgradeError(f"Invalid file size: {rel}")
            total_size += item["size"]
            if total_size > MAX_EXPANDED_BYTES:
                raise UpgradeError("Signed update expanded size exceeds its limit")
        key_id = manifest.get("key_id")
        if not isinstance(key_id, str) or not re.fullmatch(r"[0-9a-f]{64}", key_id):
            raise UpgradeError("Invalid update signing key identifier")
        keys = self.trusted_keys()
        public = keys.get(key_id)
        if public is None:
            raise UpgradeError("Update signing key is not trusted by this installation")
        try:
            signature = base64.b64decode(envelope["signature"], validate=True)
        except Exception as exc:
            raise UpgradeError("Malformed Ed25519 signature") from exc
        if len(signature) != 64:
            raise UpgradeError("Malformed Ed25519 signature length")
        Ed25519PublicKey, InvalidSignature = _crypto()
        try:
            Ed25519PublicKey.from_public_bytes(public).verify(signature, canonical_manifest_bytes(manifest))
        except InvalidSignature as exc:
            raise UpgradeError("Update manifest signature verification failed") from exc
        except Exception as exc:
            raise UpgradeError(f"Update signature verification failed: {exc}") from exc
        highest = self.highest_sequence()
        if sequence <= highest:
            accepted_version = "unknown version"
            if self.sequence_store.exists():
                state = strict_json_loads(self.sequence_store.read_bytes())
                accepted_version = str(state.get("version", accepted_version))
            raise UpgradeError(
                "Update sequence is a replay or downgrade "
                f"(package sequence {sequence}; highest accepted sequence {highest} "
                f"for {accepted_version}). Select a newly signed forward update."
            )
        return manifest

    def highest_sequence(self) -> int:
        _assert_no_reparse(self.sequence_store)
        if not self.sequence_store.exists():
            return 0
        state = strict_json_loads(self.sequence_store.read_bytes())
        if not isinstance(state, dict) or set(state) != {"schema", "sequence", "version"} or state.get("schema") != 1:
            raise UpgradeError("Persisted update sequence is corrupt; refusing update")
        value = state.get("sequence")
        if isinstance(value, bool) or not isinstance(value, int) or value < 0:
            raise UpgradeError("Persisted update sequence is invalid; refusing update")
        return value

    def record_success(self, sequence: int, version: str) -> None:
        highest = self.highest_sequence()
        if sequence < highest:
            raise UpgradeError("Cannot persist a replayed update sequence")
        if sequence == highest:
            state = strict_json_loads(self.sequence_store.read_bytes())
            if state.get("version") == version:
                return
            raise UpgradeError("Update sequence is already bound to another version")
        self.runtime.mkdir(parents=True, exist_ok=True)
        data = json.dumps({"schema": 1, "sequence": sequence, "version": version}, sort_keys=True, separators=(",", ":"))
        fd, name = tempfile.mkstemp(prefix="update_sequence_", suffix=".tmp", dir=self.runtime)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.sequence_store)
        finally:
            Path(name).unlink(missing_ok=True)


class UpdateJournal:
    """Small atomic update-state journal used for interruption recovery."""

    def __init__(self, root: str | Path):
        self.verifier = SignedUpdateVerifier(root)
        self.path = self.verifier.runtime / "update_state_machine.json"

    def read(self) -> dict:
        _assert_no_reparse(self.path)
        if not self.path.exists():
            return {"schema": 1, "state": "IDLE"}
        data = strict_json_loads(self.path.read_bytes())
        if (not isinstance(data, dict) or data.get("schema") != 1
                or data.get("state") not in _JOURNAL_STATES):
            raise UpgradeError("Update state journal is corrupt; refusing to continue")
        return data

    def transition(self, state: str, **details) -> dict:
        if state not in _JOURNAL_STATES:
            raise UpgradeError("Invalid updater state transition")
        previous = self.read()
        data = {"schema": 1, "state": state, "updated_at": int(time.time())}
        for key in ("version", "sequence", "package_sha256", "backup", "error", "helper_pid"):
            value = details.get(key)
            if value is not None:
                data[key] = str(value)[:1000] if key in ("backup", "error") else value
        self.verifier.runtime.mkdir(parents=True, exist_ok=True)
        fd, name = tempfile.mkstemp(prefix="update_journal_", suffix=".tmp", dir=self.verifier.runtime)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                json.dump(data, stream, sort_keys=True, separators=(",", ":"))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.path)
        finally:
            Path(name).unlink(missing_ok=True)
        return data


def verify_signed_package(root: str | Path, package_path: str | Path, sidecar_path: str | Path | None = None, *, expected_channel: str = "stable") -> dict:
    package_requested = Path(package_path).expanduser().absolute()
    _assert_no_reparse(package_requested)
    package = package_requested.resolve()
    sidecar_requested = Path(sidecar_path).expanduser().absolute() if sidecar_path else Path(str(package) + ".update.json")
    _assert_no_reparse(sidecar_requested)
    sidecar = sidecar_requested.resolve()
    if not package.is_file() or package.suffix.lower() != ".zip":
        raise UpgradeError("Signed update package must be an existing ZIP")
    if package.stat().st_size > MAX_PACKAGE_BYTES:
        raise UpgradeError("Update package exceeds its size limit")
    if not sidecar.is_file() or sidecar.stat().st_size > MAX_MANIFEST_BYTES:
        raise UpgradeError("Signed update sidecar is missing or oversized")
    envelope = strict_json_loads(sidecar.read_bytes())
    verifier = SignedUpdateVerifier(root)
    manifest = verifier.verify_envelope(envelope, expected_channel=expected_channel)
    expected = manifest["package"]
    if package.stat().st_size != expected["size"] or sha256_file(package) != expected["sha256"]:
        raise UpgradeError("Update ZIP size or SHA-256 does not match its signed manifest")
    try:
        with zipfile.ZipFile(package) as archive:
            infos = archive.infolist()
            if len(infos) > MAX_FILES + 1:
                raise UpgradeError("Update ZIP contains too many entries")
            names = set()
            file_names = set()
            expanded = 0
            for info in infos:
                raw_name = info.filename
                if raw_name.casefold() == "upgrade_manifest.json" and raw_name != "upgrade_manifest.json":
                    raise UpgradeError("Package upgrade manifest path has non-canonical casing")
                name = raw_name[:-1] if raw_name.endswith("/") else raw_name
                if not name:
                    raise UpgradeError("Update ZIP contains an empty member path")
                rel = _safe_relative_path(name)
                folded = _path_key(rel)
                if folded in names:
                    raise UpgradeError(f"Duplicate normalized ZIP member: {rel}")
                names.add(folded)
                if not info.is_dir():
                    file_names.add(folded)
                mode = (info.external_attr >> 16) & 0o170000
                if mode and mode not in (0o100000, 0o040000):
                    raise UpgradeError(f"Update ZIP contains a symlink or special file: {rel}")
                if info.flag_bits & 0x1:
                    raise UpgradeError("Encrypted update ZIP members are not supported")
                if info.file_size > MAX_FILE_BYTES:
                    raise UpgradeError(f"Update ZIP member exceeds its size limit: {rel}")
                expanded += info.file_size
                if expanded > MAX_EXPANDED_BYTES:
                    raise UpgradeError("Update ZIP expanded size exceeds its limit")
            if "upgrade_manifest.json" not in names:
                raise UpgradeError("Signed update ZIP has no upgrade manifest")
            manifest_info = next((item for item in infos if item.filename == "upgrade_manifest.json"), None)
            if manifest_info is None or manifest_info.file_size > MAX_MANIFEST_BYTES:
                raise UpgradeError("Package upgrade manifest is missing or oversized")
            if archive.testzip() is not None:
                raise UpgradeError("Update ZIP CRC verification failed")
            internal = strict_json_loads(archive.read("upgrade_manifest.json"))
            if not isinstance(internal, dict) or internal.get("product") != "ALICE" or internal.get("version") != manifest["version"]:
                raise UpgradeError("Signed envelope and package upgrade manifest disagree")
            internal_files = internal.get("files")
            if not isinstance(internal_files, list):
                raise UpgradeError("Package upgrade file manifest is malformed")
            declared = {}
            for row in manifest["files"]:
                rel = _safe_relative_path(row["path"])
                declared[_path_key(rel)] = (row["sha256"], row["size"], rel)
            package_files = {}
            for row in internal_files:
                if not isinstance(row, dict):
                    raise UpgradeError("Package upgrade file record is malformed")
                rel = _safe_relative_path(row.get("path"))
                package_files[_path_key(rel)] = (row.get("sha256"), row.get("size"), rel)
            if package_files != declared:
                raise UpgradeError("Signed file inventory does not match upgrade_manifest.json")
            zip_file_sizes = {_path_key(item.filename): item.file_size for item in infos if not item.is_dir() and item.filename != "upgrade_manifest.json"}
            if any(zip_file_sizes.get(path) != row[1] for path, row in declared.items()):
                raise UpgradeError("Signed per-file sizes do not match ZIP contents")
            actual_members = file_names - {"upgrade_manifest.json"}
            if actual_members != set(declared):
                raise UpgradeError("Signed file inventory does not match ZIP contents")
    except zipfile.BadZipFile as exc:
        raise UpgradeError("Signed update is not a valid ZIP archive") from exc
    checked = InPlaceUpdater(root).validate_package(package)
    return {"ok": True, "package": str(package), "sidecar": str(sidecar), "manifest": manifest,
            "file_count": checked["file_count"], "fingerprint": manifest["key_id"]}


def public_key_from_file(path: str | Path) -> bytes:
    raw = Path(path).read_bytes()
    if not raw or len(raw) > 16 * 1024:
        raise UpgradeError("Public key file is empty or oversized")
    if raw.startswith(b"-----BEGIN"):
        try:
            from cryptography.hazmat.primitives import serialization
            key = serialization.load_pem_public_key(raw)
            raw = key.public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        except Exception as exc:
            raise UpgradeError(f"Invalid Ed25519 public key file: {exc}") from exc
    elif len(raw) != 32:
        try:
            raw = base64.b64decode(raw.strip(), validate=True)
        except Exception as exc:
            raise UpgradeError("Public key must be raw Ed25519 bytes, base64, or PEM") from exc
    if len(raw) != 32:
        raise UpgradeError("Ed25519 public key must be exactly 32 bytes")
    Ed25519PublicKey, _ = _crypto()
    try:
        Ed25519PublicKey.from_public_bytes(raw)
    except Exception as exc:
        raise UpgradeError("Invalid Ed25519 public key") from exc
    return raw


def enroll_trusted_key(root: str | Path, public_key: bytes, fingerprint_confirmation: str) -> str:
    """Pin a public key only after the caller has shown/confirmed its fingerprint."""
    if len(public_key) != 32:
        raise UpgradeError("Ed25519 public key must be exactly 32 bytes")
    key_id = hashlib.sha256(public_key).hexdigest()
    if not isinstance(fingerprint_confirmation, str) or fingerprint_confirmation.strip().lower() != key_id:
        raise UpgradeError("Publisher fingerprint confirmation did not match")
    verifier = SignedUpdateVerifier(root)
    keys = verifier.trusted_keys()
    if key_id in keys:
        return key_id
    verifier.runtime.mkdir(parents=True, exist_ok=True)
    _assert_no_reparse(verifier.key_store)
    records = [{"key_id": key, "public_key": base64.b64encode(value).decode("ascii")} for key, value in sorted(keys.items())]
    records.append({"key_id": key_id, "public_key": base64.b64encode(public_key).decode("ascii")})
    data = json.dumps({"schema": 1, "keys": records}, sort_keys=True, indent=2) + "\n"
    fd, name = tempfile.mkstemp(prefix="trusted_update_keys_", suffix=".tmp", dir=verifier.runtime)
    try:
        with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name, verifier.key_store)
    finally:
        Path(name).unlink(missing_ok=True)
    return key_id


def record_signed_update_success(root: str | Path, manifest: dict) -> None:
    SignedUpdateVerifier(root).record_success(int(manifest["sequence"]), str(manifest["version"]))
