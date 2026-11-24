"""Postconditions for workspace file tools."""
from __future__ import annotations

import hashlib

from ..execution.postconditions import PostconditionResult


def verify_workspace_file_write_postcondition(args, result):
    """Re-open the requested workspace file and compare its exact contents."""
    from . import files

    try:
        requested = str(args["path"])
        expected = str(args["content"])
        target = files.safe_path(requested)
        observed = target.is_file()
        if not observed:
            return PostconditionResult(False, {"observed": False}, "workspace_file_missing_after_write")
        actual = target.read_text(encoding="utf-8")
        path_matches = str(result) == str(target.relative_to(files.ROOT))
        matches = path_matches and actual == expected
        evidence = {
            "observed": True,
            "path_matches": path_matches,
            "content_matches": actual == expected,
            "sha256": hashlib.sha256(actual.encode("utf-8")).hexdigest(),
        }
        return PostconditionResult(
            matches,
            evidence,
            "workspace content re-read and matched" if matches else "workspace_write_postcondition_mismatch",
        )
    except Exception as exc:
        return PostconditionResult(False, {"observed": False}, f"workspace_observation_error:{type(exc).__name__}")
