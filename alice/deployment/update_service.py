"""Signed-only update discovery and staging for ALICE.

The service never installs code. It accepts only an Ed25519-signed release
manifest from a pinned publisher, downloads into a fresh private staging
directory, checks the signed package digest and inventory, then returns the
verified ZIP to the trusted updater helper.
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import tempfile
import urllib.request
from pathlib import Path

from .signed_updates import (
    MAX_MANIFEST_BYTES,
    MAX_PACKAGE_BYTES,
    SignedUpdateVerifier,
    UpdateJournal,
    _assert_no_reparse,
    strict_json_loads,
    verify_signed_package,
)
from .updater import InPlaceUpdater, UpgradeError, read_version, version_tuple, _secure_temp_dir


class UpdateService:
    def __init__(self, root=None):
        requested = Path(root or Path(__file__).resolve().parents[2]).expanduser().absolute()
        _assert_no_reparse(requested)
        self.root = requested.resolve()
        self.state_path = self.root / "alice_workspace" / "runtime" / "update.json"
        self.download_dir = self.root / "alice_workspace" / "updates"
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.download_dir.mkdir(parents=True, exist_ok=True)
        _assert_no_reparse(self.state_path.parent)
        _assert_no_reparse(self.download_dir)
        self._state = self._load()
        self.journal = UpdateJournal(self.root)

    def _load(self):
        try:
            data = strict_json_loads(self.state_path.read_bytes())
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def _save(self):
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self._state, indent=2, ensure_ascii=False)
        fd, name = tempfile.mkstemp(prefix="update_state_", suffix=".tmp", dir=self.state_path.parent)
        try:
            with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as stream:
                stream.write(data)
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(name, self.state_path)
        finally:
            Path(name).unlink(missing_ok=True)

    def configure(self, feed_url=None, repo=None, local_zip=None, auto_check=False, auto_install=False, auto_install_local=False):
        if feed_url is not None:
            self._state["feed_url"] = str(feed_url).strip()
        if repo is not None:
            self._state["repo"] = str(repo).strip()
        if local_zip is not None:
            self._state["local_zip"] = str(local_zip).strip()
        self._state["auto_check"] = bool(auto_check)
        # An explicit user opt-in is required; both defaults remain disabled.
        self._state["auto_install"] = bool(auto_install)
        self._state["auto_install_local"] = bool(auto_install_local)
        self._state.setdefault("channel", "stable")
        self._save()
        return self.status()

    def status(self):
        try:
            key_count = len(SignedUpdateVerifier(self.root).trusted_keys())
            key_error = ""
        except Exception as exc:
            key_count = 0
            key_error = type(exc).__name__
        try:
            journal = self.journal.read()
            journal_error = ""
        except Exception as exc:
            journal = {"state": "FAILED"}
            journal_error = type(exc).__name__
        return {
            "current_version": read_version(self.root),
            "feed_url": self._state.get("feed_url") or os.getenv("ALICE_UPDATE_FEED_URL", ""),
            "repo": self._state.get("repo") or os.getenv("ALICE_UPDATE_REPO", ""),
            "local_zip": self._state.get("local_zip", ""),
            "channel": self._state.get("channel", "stable"),
            "auto_check": bool(self._state.get("auto_check", False)),
            "auto_install": bool(self._state.get("auto_install", False)),
            "auto_install_local": bool(self._state.get("auto_install_local", False)),
            "trusted_key_count": key_count,
            "trusted_key_error": key_error,
            "update_state": journal.get("state", "IDLE"),
            "update_state_updated_at": journal.get("updated_at"),
            "update_target": journal.get("version", ""),
            "rollback_available": bool(journal.get("backup") and Path(str(journal["backup"])).is_dir()),
            "update_state_error": journal_error,
        }

    @staticmethod
    def _pid_is_running(pid):
        if not pid:
            return False
        try:
            os.kill(int(pid), 0)
            return True
        except PermissionError:
            return True
        except (OSError, ValueError, TypeError):
            return False

    def recover_interrupted(self):
        """Finish a proven healthy update or roll back an interrupted transaction."""
        state = self.journal.read()
        name = state.get("state", "IDLE")
        if name not in {"BACKED_UP", "APPLYING", "HEALTH_CHECK", "ROLLING_BACK", "CHECKING", "AVAILABLE", "DOWNLOADING", "STAGED", "VERIFIED"}:
            return {"ok": True, "state": name, "recovered": False}
        if self._pid_is_running(state.get("helper_pid")):
            return {"ok": True, "state": name, "recovered": False, "helper_active": True}
        runtime = self.state_path.parent
        if name == "HEALTH_CHECK":
            try:
                health = strict_json_loads((runtime / "health.json").read_bytes())
            except Exception:
                health = {}
            if isinstance(health, dict) and health.get("ok") is True and health.get("version") == state.get("version"):
                verifier = SignedUpdateVerifier(self.root)
                verifier.record_success(int(state["sequence"]), str(state["version"]))
                self.journal.transition("ACCEPTED", version=state["version"], sequence=state["sequence"], package_sha256=state.get("package_sha256"))
                return {"ok": True, "state": "ACCEPTED", "recovered": True}
        if name in {"BACKED_UP", "APPLYING", "HEALTH_CHECK", "ROLLING_BACK"}:
            backup = state.get("backup")
            if not backup:
                raise UpgradeError("Interrupted update has no recorded recovery backup")
            _assert_no_reparse(Path(backup).expanduser().absolute())
            self.journal.transition("ROLLING_BACK", version=state.get("version"), sequence=state.get("sequence"), package_sha256=state.get("package_sha256"), backup=backup)
            result = InPlaceUpdater(self.root).rollback(backup)
            self.journal.transition("ROLLED_BACK", version=result["version"], sequence=state.get("sequence"), package_sha256=state.get("package_sha256"), backup=backup)
            return {"ok": True, "state": "ROLLED_BACK", "recovered": True, "backup": backup}
        self.journal.transition("FAILED", error="interrupted_before_apply")
        return {"ok": True, "state": "FAILED", "recovered": True, "reason": "interrupted_before_apply"}

    def startup_allowed(self):
        """Prevent a second ALICE process from racing an active updater swap."""
        state = self.journal.read()
        name = state.get("state", "IDLE")
        pid = state.get("helper_pid")
        if not self._pid_is_running(pid):
            return True
        if name == "HEALTH_CHECK" and int(pid) == os.getppid():
            return True
        return name not in {"CHECKING", "VERIFIED", "BACKED_UP", "APPLYING", "HEALTH_CHECK", "ROLLING_BACK"}

    @staticmethod
    def _get_json(url):
        if not str(url).lower().startswith("https://"):
            raise UpgradeError("Update metadata must use HTTPS")
        req = urllib.request.Request(url, headers={"User-Agent": "ALICE-UpdateClient/4.106", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=20) as response:
                if not response.geturl().lower().startswith("https://"):
                    raise UpgradeError("Update metadata redirected away from HTTPS")
                raw = response.read(MAX_MANIFEST_BYTES + 1)
        except UpgradeError:
            raise
        except Exception as exc:
            raise UpgradeError(f"Could not fetch signed update metadata: {exc}") from exc
        return strict_json_loads(raw)

    def _github_release(self, repo):
        import re
        if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repo):
            raise UpgradeError("Invalid GitHub repository; use owner/name")
        data = self._get_json(f"https://api.github.com/repos/{repo}/releases/latest")
        assets = data.get("assets") or []
        verifier = SignedUpdateVerifier(self.root)
        for asset in assets:
            name = str(asset.get("name", ""))
            if not name.lower().endswith(".zip"):
                continue
            signed_name = name + ".update.json"
            signed_asset = next((row for row in assets if str(row.get("name", "")) == signed_name), None)
            if not signed_asset:
                continue
            envelope = self._get_json(str(signed_asset.get("browser_download_url", "")))
            manifest = verifier.verify_envelope(envelope, expected_channel=self._state.get("channel", "stable"))
            if manifest["package"]["url"] != str(asset.get("browser_download_url", "")):
                raise UpgradeError("Signed manifest package URL does not match its GitHub release asset")
            return envelope, manifest, str(data.get("html_url", ""))
        raise UpgradeError("GitHub release has no matching signed .update.json manifest; refusing unsigned release")

    def check_local(self, package):
        """Verify a selected local package and adjacent <package>.update.json."""
        path = Path(package).expanduser().absolute()
        result = verify_signed_package(self.root, path, expected_channel=self._state.get("channel", "stable"))
        manifest = result["manifest"]
        current = read_version(self.root)
        available = version_tuple(manifest["version"]) > version_tuple(current)
        return {
            "ok": True, "configured": True, "local": True, "package": str(path),
            "current_version": current, "latest_version": manifest["version"],
            "available": available, "file_count": result["file_count"],
            "sha256": manifest["package"]["sha256"], "sequence": manifest["sequence"],
            "fingerprint": manifest["key_id"], "signed": True,
        }

    def check(self):
        self.journal.transition("CHECKING")
        try:
            feed = str(self._state.get("feed_url") or os.getenv("ALICE_UPDATE_FEED_URL", "")).strip()
            repo = str(self._state.get("repo") or os.getenv("ALICE_UPDATE_REPO", "")).strip()
            verifier = SignedUpdateVerifier(self.root)
            if feed:
                envelope = self._get_json(feed)
                manifest = verifier.verify_envelope(envelope, expected_channel=self._state.get("channel", "stable"))
                release_url = ""
            elif repo:
                envelope, manifest, release_url = self._github_release(repo)
            else:
                self.journal.transition("IDLE")
                return {"ok": False, "configured": False, "current_version": read_version(self.root),
                        "message": "No signed update feed configured. Pin the publisher public key, then set an HTTPS feed URL."}
            package_url = manifest["package"]["url"]
            if not package_url:
                raise UpgradeError("Signed remote update manifest has no package URL")
            current = read_version(self.root)
            available = version_tuple(manifest["version"]) > version_tuple(current)
            result = {
                "ok": True, "configured": True, "signed": True,
                "current_version": current, "latest_version": manifest["version"],
                "available": available, "package_url": package_url,
                "sha256": manifest["package"]["sha256"], "size": manifest["package"]["size"],
                "sequence": manifest["sequence"], "fingerprint": manifest["key_id"],
                "channel": manifest["channel"], "release_url": release_url,
                "notes": manifest["release_notes"], "signed_envelope": envelope,
            }
            self._state["last_check"] = {key: value for key, value in result.items() if key != "signed_envelope"}
            self._save()
            self.journal.transition("AVAILABLE" if available else "IDLE", version=manifest["version"], sequence=manifest["sequence"], package_sha256=manifest["package"]["sha256"])
            return result
        except Exception as exc:
            self.journal.transition("FAILED", error=type(exc).__name__)
            raise

    def download(self, info):
        if not info.get("available"):
            return {"ok": True, "downloaded": False, "message": "Already up to date.", **info}
        envelope = info.get("signed_envelope")
        verifier = SignedUpdateVerifier(self.root)
        manifest = verifier.verify_envelope(envelope, expected_channel=self._state.get("channel", "stable"))
        package_meta = manifest["package"]
        url = package_meta["url"]
        if not url.lower().startswith("https://"):
            raise UpgradeError("Signed update package URL must use HTTPS")
        _assert_no_reparse(self.download_dir)
        stage = _secure_temp_dir(self.download_dir, f"stage_{manifest['sequence']}_")
        _assert_no_reparse(stage)
        self.journal.transition("DOWNLOADING", version=manifest["version"], sequence=manifest["sequence"], package_sha256=package_meta["sha256"])
        name = f"ALICE_{manifest['version'].replace(' ', '_')}_{package_meta['sha256'][:12]}.zip"
        final = stage / name
        partial = stage / (name + ".part")
        sidecar = Path(str(final) + ".update.json")
        req = urllib.request.Request(url, headers={"User-Agent": "ALICE-UpdateClient/4.106", "Accept": "application/octet-stream"})
        size = 0
        digest = hashlib.sha256()
        try:
            with urllib.request.urlopen(req, timeout=60) as response:
                if not response.geturl().lower().startswith("https://"):
                    raise UpgradeError("Update download redirected away from HTTPS")
                content_length = response.headers.get("Content-Length")
                if content_length and (not content_length.isdigit() or int(content_length) != package_meta["size"]):
                    raise UpgradeError("Update server Content-Length does not match the signed size")
                with partial.open("xb") as output:
                    while True:
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        size += len(chunk)
                        if size > package_meta["size"] or size > MAX_PACKAGE_BYTES:
                            raise UpgradeError("Downloaded update exceeded its signed size limit")
                        digest.update(chunk)
                        output.write(chunk)
                    output.flush()
                    os.fsync(output.fileno())
            if size != package_meta["size"] or digest.hexdigest() != package_meta["sha256"]:
                raise UpgradeError("Downloaded update size or SHA-256 does not match its signed manifest")
            os.replace(partial, final)
            sidecar_tmp = sidecar.with_suffix(sidecar.suffix + ".tmp")
            with sidecar_tmp.open("x", encoding="utf-8", newline="\n") as stream:
                stream.write(json.dumps(envelope, sort_keys=True, indent=2))
                stream.flush()
                os.fsync(stream.fileno())
            os.replace(sidecar_tmp, sidecar)
            checked = verify_signed_package(self.root, final, sidecar, expected_channel=self._state.get("channel", "stable"))
            self.journal.transition("STAGED", version=manifest["version"], sequence=manifest["sequence"], package_sha256=package_meta["sha256"])
            self.journal.transition("VERIFIED", version=manifest["version"], sequence=manifest["sequence"], package_sha256=package_meta["sha256"])
            self._state["downloaded_package"] = str(final)
            self._state["downloaded_sidecar"] = str(sidecar)
            self._state["downloaded_version"] = manifest["version"]
            self._save()
            return {"ok": True, "downloaded": True, "package": str(final), "sidecar": str(sidecar),
                    "file_count": checked["file_count"], "signed": True, **{k: v for k, v in info.items() if k != "signed_envelope"}}
        except Exception:
            shutil.rmtree(stage, ignore_errors=True)
            self.journal.transition("FAILED", version=manifest["version"], sequence=manifest["sequence"], package_sha256=package_meta["sha256"], error="download_or_verification_failed")
            raise

    def check_and_download(self):
        info = self.check()
        return self.download(info) if info.get("available") else info

    def latest_download(self):
        package = self._state.get("downloaded_package")
        sidecar = self._state.get("downloaded_sidecar")
        if package and sidecar and Path(package).is_file() and Path(sidecar).is_file():
            verify_signed_package(self.root, package, sidecar, expected_channel=self._state.get("channel", "stable"))
            return package
        return None
