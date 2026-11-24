"""Persistent advisory graph of registered ALICE devices.

Graph relationships describe declared topology only. They never pair a
device, grant consent, or authorize a control operation.
"""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from ..execution.postconditions import PostconditionResult
from .registry import DeviceRegistry


class DeviceGraphError(ValueError):
    pass


class DeviceGraph:
    RELATIONS = frozenset({"connected_via", "associated_with", "mirrors"})
    MAX_FILE_BYTES = 2 * 1024 * 1024
    MAX_NODES = 2048
    MAX_EDGES = 8192

    def __init__(self, root=None, registry=None):
        self.root = Path(root or Path.cwd()).expanduser().resolve()
        self.registry = registry or DeviceRegistry(self.root)
        self.path = self.root / "alice_workspace" / "devices" / "graph.json"
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._data = self._load()

    @staticmethod
    def _now():
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _edge_id(source_id, target_id, relation):
        value = "\0".join((str(source_id), str(target_id), str(relation)))
        return hashlib.sha256(value.encode("utf-8")).hexdigest()[:24]

    def _load(self):
        if not self.path.exists():
            return {"format": 1, "nodes": {}, "edges": []}
        if self.path.stat().st_size > self.MAX_FILE_BYTES:
            raise DeviceGraphError("Device graph file exceeds the size limit")
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
        except Exception as exc:
            raise DeviceGraphError("Device graph file is invalid") from exc
        if not isinstance(data, dict) or data.get("format") != 1:
            raise DeviceGraphError("Unsupported device graph format")
        if not isinstance(data.get("nodes"), dict) or not isinstance(data.get("edges"), list):
            raise DeviceGraphError("Device graph structure is invalid")
        if len(data["nodes"]) > self.MAX_NODES or len(data["edges"]) > self.MAX_EDGES:
            raise DeviceGraphError("Device graph exceeds its record limit")
        for edge in data["edges"]:
            if (
                not isinstance(edge, dict)
                or edge.get("relation") not in self.RELATIONS
                or edge.get("evidence") != "user_declared"
                or edge.get("grants_authority") is not False
                or not isinstance(edge.get("source"), str)
                or not isinstance(edge.get("target"), str)
                or edge.get("id") != self._edge_id(edge.get("source"), edge.get("target"), edge.get("relation"))
            ):
                raise DeviceGraphError("Device graph contains an invalid or authority-bearing edge")
        return data

    def _registry_nodes(self):
        records = getattr(self.registry, "data", {})
        if not isinstance(records, dict) or len(records) > self.MAX_NODES:
            raise DeviceGraphError("Device registry is invalid or exceeds the graph node limit")
        nodes = {}
        for device_id, row in records.items():
            if not isinstance(row, dict):
                continue
            did = str(device_id)
            capabilities = row.get("capabilities", [])
            nodes[did] = {
                "id": did,
                "name": str(row.get("name", did))[:160],
                "kind": str(row.get("kind", "unknown"))[:80],
                "capabilities": sorted({str(x)[:80] for x in capabilities if isinstance(x, str)})[:128],
                "online": row.get("online") is True,
                "paired": row.get("paired") is True,
                "last_seen": row.get("last_seen"),
            }
        return nodes

    def _save(self):
        payload = json.dumps(self._data, ensure_ascii=False, indent=2) + "\n"
        encoded = payload.encode("utf-8")
        if len(encoded) > self.MAX_FILE_BYTES:
            raise DeviceGraphError("Device graph file exceeds the size limit")
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                "wb", dir=self.path.parent, prefix="graph.json.", suffix=".tmp", delete=False
            ) as output:
                temporary = Path(output.name)
                output.write(encoded)
                output.flush()
                os.fsync(output.fileno())
            os.replace(temporary, self.path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()

    def snapshot(self):
        """Return current registered nodes and persisted advisory relationships."""
        nodes = self._registry_nodes()
        edges = [
            dict(edge) for edge in self._data["edges"]
            if edge.get("source") in nodes and edge.get("target") in nodes
        ]
        return {
            "nodes": [nodes[key] for key in sorted(nodes)],
            "edges": sorted(edges, key=lambda row: row["id"]),
            "authority_granted": False,
            "requires_device_consent": True,
        }

    def link(self, source_id, target_id, relation):
        source, target = str(source_id), str(target_id)
        relation = str(relation).strip().casefold()
        nodes = self._registry_nodes()
        if source not in nodes or target not in nodes:
            raise DeviceGraphError("Both graph endpoints must exist in DeviceRegistry")
        if source == target:
            raise DeviceGraphError("A device cannot be linked to itself")
        if relation not in self.RELATIONS:
            raise DeviceGraphError("Unsupported advisory device relationship")
        edge_id = self._edge_id(source, target, relation)
        existing = next((row for row in self._data["edges"] if row.get("id") == edge_id), None)
        if existing is None:
            self._data["nodes"] = nodes
            self._data["edges"].append({
                "id": edge_id,
                "source": source,
                "target": target,
                "relation": relation,
                "evidence": "user_declared",
                "created_at": self._now(),
                "grants_authority": False,
            })
            self._save()
        return {"ok": True, "edge_id": edge_id, "status": "recorded", "authority_granted": False}

    def route(self, source_id, target_id):
        source, target = str(source_id), str(target_id)
        nodes = self._registry_nodes()
        if source not in nodes or target not in nodes:
            raise DeviceGraphError("Both route endpoints must exist in DeviceRegistry")
        adjacency = {node_id: set() for node_id in nodes}
        for edge in self._data["edges"]:
            if edge.get("relation") == "connected_via" and edge.get("source") in nodes and edge.get("target") in nodes:
                adjacency[edge["source"]].add(edge["target"])
                adjacency[edge["target"]].add(edge["source"])
        queue = deque([(source, [source])])
        visited = {source}
        while queue:
            current, path = queue.popleft()
            if current == target:
                return {"found": True, "path": path, "basis": "user_declared_graph",
                        "executable": False, "requires_device_consent": True}
            for neighbor in sorted(adjacency[current]):
                if neighbor not in visited:
                    visited.add(neighbor)
                    queue.append((neighbor, path + [neighbor]))
        return {"found": False, "path": [], "basis": "user_declared_graph",
                "executable": False, "requires_device_consent": True}

    def verify_link_postcondition(self, args, result):
        """Independently reread the persisted edge after a link operation."""
        try:
            source = str(args["source_id"])
            target = str(args["target_id"])
            relation = str(args["relation"]).strip().casefold()
            edge_id = self._edge_id(source, target, relation)
            persisted = json.loads(self.path.read_text(encoding="utf-8"))
            present = any(
                isinstance(edge, dict)
                and edge.get("id") == edge_id
                and edge.get("source") == source
                and edge.get("target") == target
                and edge.get("relation") == relation
                and edge.get("evidence") == "user_declared"
                and edge.get("grants_authority") is False
                for edge in persisted.get("edges", [])
            )
            output_matches = isinstance(result, dict) and result.get("edge_id") == edge_id
            ok = present and output_matches
            return PostconditionResult(
                ok,
                {"observed": True, "edge_present": present, "result_matches": output_matches,
                 "authority_granted": False},
                "device relationship reread from disk" if ok else "device_graph_link_not_observed",
            )
        except Exception as exc:
            return PostconditionResult(False, {"observed": False}, f"device_graph_observation_error:{type(exc).__name__}")
