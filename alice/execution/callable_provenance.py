"""Derive bounded, local provenance for a callable registered as an ALICE tool."""
from __future__ import annotations

import hashlib
import inspect
import marshal
from pathlib import Path


def normalize_entry_point(value: object) -> str | None:
    """Accept only an explicit ALICE Python entry point in ``module:qualname`` form."""
    text = str(value or "").strip()
    if not text or len(text) > 240 or text.count(":") != 1:
        return None
    module, qualname = text.split(":", 1)
    module_parts = module.split(".")
    qualname_parts = qualname.split(".")
    if (not module.startswith("alice.") or not module_parts or not qualname_parts
            or any(not part.isidentifier() for part in module_parts + qualname_parts)):
        return None
    return f"{module}:{qualname}"


def callable_provenance(function: object, root: str | Path) -> dict | None:
    """Describe a Python callable only when its source is an ALICE-owned file.

    Candidate/quarantine content is never imported by this helper. It inspects the
    already-registered callable and binds its module file and code object to hashes.
    """
    target = function.__func__ if inspect.ismethod(function) else function
    if not inspect.isfunction(target):
        return None
    module = str(getattr(target, "__module__", "") or "")
    qualname = str(getattr(target, "__qualname__", "") or "")
    code = getattr(target, "__code__", None)
    if not module.startswith("alice.") or not qualname or code is None:
        return None
    try:
        source_name = inspect.getsourcefile(target)
        if not source_name:
            return None
        source = Path(source_name).resolve(strict=True)
        base = Path(root).resolve(strict=True)
        relative = source.relative_to(base).as_posix()
        if not relative.startswith("alice/"):
            return None
        parts = {part.casefold() for part in relative.split("/")}
        if parts.intersection({"quarantine", "quarantined", "third_party_candidates"}):
            return None
        content = source.read_bytes()
        code_bytes = marshal.dumps(code)
    except (OSError, TypeError, ValueError):
        return None
    return {
        "module": module[:200],
        "qualname": qualname[:300],
        "source_path": relative[:500],
        "source_size": len(content),
        "source_sha256": hashlib.sha256(content).hexdigest(),
        "code_sha256": hashlib.sha256(code_bytes).hexdigest(),
    }
