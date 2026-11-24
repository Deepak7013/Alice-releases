"""Crash-resistant JSON persistence for small ALICE state files."""
from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import Any


def atomic_write_json(path: str | Path, payload: Any, *, indent: int = 2) -> None:
    """Write JSON to a sibling temp file and atomically replace the destination.

    The destination is not truncated until a complete, flushed JSON document
    exists. A sibling temp file keeps replacement on the same filesystem.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    temp_path: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", newline="\n", dir=target.parent,
            prefix=target.name + ".", suffix=".tmp", delete=False,
        ) as stream:
            temp_path = Path(stream.name)
            json.dump(payload, stream, indent=indent, ensure_ascii=False)
            stream.write("\n")
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temp_path, target)
        temp_path = None
        # Best-effort directory flush: supported on POSIX, not consistently on Windows.
        if os.name != "nt":
            try:
                fd = os.open(str(target.parent), os.O_RDONLY)
                try:
                    os.fsync(fd)
                finally:
                    os.close(fd)
            except OSError:
                pass
    finally:
        if temp_path is not None:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                pass
