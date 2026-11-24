import json
import os
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Optional

from .models import ActionRecord, ActionStatus


class ActionStore:
    def __init__(self, root=None):
        self.root = Path(root or Path("data") / "actions")
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, action_id: str) -> Path:
        if not action_id or Path(action_id).name != action_id or action_id in {".", ".."}:
            raise ValueError("invalid action id")
        return self.root / f"{action_id}.json"

    def save(self, record: ActionRecord) -> ActionRecord:
        path = self._path(record.action_id)
        payload = asdict(record)
        payload["status"] = record.status.value
        fd, tmp = tempfile.mkstemp(prefix=f".{record.action_id}.", suffix=".tmp", dir=self.root)
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(payload, fh, ensure_ascii=False, indent=2)
                fh.flush()
                os.fsync(fh.fileno())
            os.replace(tmp, path)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return record

    def get(self, action_id: str) -> Optional[ActionRecord]:
        path = self._path(action_id)
        if not path.exists():
            return None
        data = json.loads(path.read_text(encoding="utf-8"))
        data["status"] = ActionStatus(data["status"])
        return ActionRecord(**data)

    def list(self):
        records = []
        for path in sorted(self.root.glob("*.json")):
            record = self.get(path.stem)
            if record:
                records.append(record)
        return records
