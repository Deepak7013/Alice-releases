from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Iterable, Mapping, Optional, Sequence
import re
import subprocess

from .registry import DeviceRegistry


@dataclass(frozen=True)
class DeviceCandidate:
    """A discovered device. Discovery never authorizes or pairs a device."""
    id: str
    name: str
    kind: str
    capabilities: tuple[str, ...] = ()
    source: str = "unknown"
    online: bool = False
    metadata: Mapping[str, str] = field(default_factory=dict)

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "kind": self.kind,
            "capabilities": list(self.capabilities),
            "source": self.source,
            "online": self.online,
            "metadata": dict(self.metadata),
        }


class DiscoveryError(RuntimeError):
    pass


def _adb_properties(parts: Sequence[str]) -> dict[str, str]:
    props: dict[str, str] = {}
    for item in parts:
        if ":" in item:
            key, value = item.split(":", 1)
            if key and value:
                props[key] = value
    return props


def parse_adb_devices(output: str) -> list[DeviceCandidate]:
    """Parse `adb devices -l` output without assuming a particular Android model."""
    found: list[DeviceCandidate] = []
    for raw in output.splitlines():
        line = raw.strip()
        if not line or line.startswith("List of devices attached"):
            continue
        fields = line.split()
        if len(fields) < 2 or fields[1] not in {"device", "offline", "unauthorized"}:
            continue

        serial = fields[0]
        if not re.fullmatch(r"[A-Za-z0-9._:-]+", serial):
            continue

        props = _adb_properties(fields[2:])
        model = props.get("model", "").replace("_", " ").strip()
        product = props.get("product", "").replace("_", " ").strip()
        state = fields[1]
        name = model or product or serial

        found.append(DeviceCandidate(
            id=serial,
            name=name,
            kind="android",
            capabilities=("adb",),
            source="adb",
            online=state == "device",
            metadata={"state": state, **({"product": product} if product else {})},
        ))
    return found


class DeviceDiscovery:
    """Provider-neutral device discovery.

    Sources are read-only. No source can mark a device paired/authorized.
    """

    def __init__(
        self,
        registry: Optional[DeviceRegistry] = None,
        adb_command: str = "adb",
        runner: Optional[Callable[..., subprocess.CompletedProcess]] = None,
    ):
        self.registry = registry
        self.adb_command = adb_command
        self._runner = runner or subprocess.run

    def from_registry(self, online_only: bool = False) -> list[DeviceCandidate]:
        if self.registry is None:
            return []
        # Registry is treated as a source of known devices, not authorization.
        result: list[DeviceCandidate] = []
        for item in self.registry.data.values():
            if online_only and not item.get("online", False):
                continue
            result.append(DeviceCandidate(
                id=item["id"],
                name=item["name"],
                kind=item["kind"],
                capabilities=tuple(sorted(item.get("capabilities", []))),
                source="registry",
                online=bool(item.get("online", False)),
                metadata={"paired": str(bool(item.get("paired", False))).lower()},
            ))
        return result

    def from_adb(self, timeout: float = 3.0) -> list[DeviceCandidate]:
        try:
            completed = self._runner(
                [self.adb_command, "devices", "-l"],
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )
        except (FileNotFoundError, OSError) as exc:
            raise DiscoveryError(f"ADB discovery unavailable: {exc}") from exc
        except subprocess.TimeoutExpired as exc:
            raise DiscoveryError("ADB discovery timed out") from exc

        if completed.returncode != 0:
            detail = (completed.stderr or completed.stdout or "").strip()
            raise DiscoveryError(
                f"ADB discovery failed with exit code {completed.returncode}"
                + (f": {detail}" if detail else "")
            )
        return parse_adb_devices(completed.stdout or "")

    @staticmethod
    def merge(candidates: Iterable[DeviceCandidate]) -> list[DeviceCandidate]:
        """Deduplicate by device id, preferring a live ADB observation."""
        merged: dict[str, DeviceCandidate] = {}
        for candidate in candidates:
            previous = merged.get(candidate.id)
            if previous is None:
                merged[candidate.id] = candidate
                continue
            if candidate.online and not previous.online:
                merged[candidate.id] = candidate
            elif previous.source != "adb" and candidate.source == "adb":
                merged[candidate.id] = candidate
        return sorted(merged.values(), key=lambda x: (x.kind, x.name.lower(), x.id))

    def discover(self, *, include_registry: bool = True, include_adb: bool = True,
                 online_only: bool = False, strict: bool = False) -> list[DeviceCandidate]:
        candidates: list[DeviceCandidate] = []
        errors: list[str] = []

        if include_registry:
            candidates.extend(self.from_registry(online_only=online_only))

        if include_adb:
            try:
                candidates.extend(self.from_adb())
            except DiscoveryError as exc:
                errors.append(str(exc))

        result = self.merge(candidates)
        if online_only:
            result = [item for item in result if item.online]

        if strict and errors:
            raise DiscoveryError("; ".join(errors))
        return result
