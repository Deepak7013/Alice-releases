"""Durable, atomic local provider configuration updates."""
from __future__ import annotations

import os
import re
import tempfile
from pathlib import Path


_KEY_RE = re.compile(r"^\s*(?:export\s+)?OPENROUTER_API_KEY\s*=")
_MODEL_RE = re.compile(r"^\s*(?:export\s+)?OPENROUTER_MODEL\s*=")
_FREE_ONLY_RE = re.compile(r"^\s*(?:export\s+)?OPENROUTER_FREE_ONLY\s*=")
_GROQ_KEY_RE = re.compile(r"^\s*(?:export\s+)?GROQ_API_KEY\s*=")
_GROQ_MODEL_RE = re.compile(r"^\s*(?:export\s+)?GROQ_MODEL\s*=")
_PRIMARY_RE = re.compile(r"^\s*(?:export\s+)?ALICE_PRIMARY_PROVIDER\s*=")
_RUNTIME_MODE_RE = re.compile(r"^\s*(?:export\s+)?ALICE_RUNTIME_MODE\s*=")
_LOCAL_FAST_MODEL_RE = re.compile(r"^\s*(?:export\s+)?ALICE_LOCAL_FAST_MODEL\s*=")
_GEMINI_KEY_RE = re.compile(r"^\s*(?:export\s+)?GEMINI_API_KEY\s*=")
_GEMINI_MODEL_RE = re.compile(r"^\s*(?:export\s+)?GEMINI_MODEL\s*=")
_PROVIDER_ENV = {
    "openai": ("OPENAI_API_KEY", "OPENAI_MODEL"),
    "anthropic": ("ANTHROPIC_API_KEY", "ANTHROPIC_MODEL"),
    "groq": ("GROQ_API_KEY", "GROQ_MODEL"),
    "openrouter": ("OPENROUTER_API_KEY", "OPENROUTER_MODEL"),
    "nvidia": ("NVIDIA_API_KEY", "NVIDIA_MODEL"),
}


def _env_value(lines, name):
    pattern = re.compile(r"^\s*(?:export\s+)?" + re.escape(name) + r"\s*=\s*(.*)$")
    for line in lines:
        match = pattern.match(line)
        if match:
            return match.group(1).strip().strip('"\'')
    return ""


def _atomic_update(path, updates, *, require_existing=()):
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        prior = target.read_text(encoding="utf-8-sig") if target.exists() else ""
    except UnicodeError as exc:
        raise ValueError("Existing provider config is not valid UTF-8; preserved unchanged") from exc
    lines = prior.splitlines()
    for name in require_existing:
        if not _env_value(lines, name):
            raise ValueError("A provider API key must first be configured in ALICE Provider Setup")
    patterns = {
        "GROQ_API_KEY": _GROQ_KEY_RE,
        "GROQ_MODEL": _GROQ_MODEL_RE,
        "ALICE_PRIMARY_PROVIDER": _PRIMARY_RE,
        "ALICE_RUNTIME_MODE": _RUNTIME_MODE_RE,
        "ALICE_LOCAL_FAST_MODEL": _LOCAL_FAST_MODEL_RE,
        "OPENROUTER_API_KEY": _KEY_RE,
        "OPENROUTER_MODEL": _MODEL_RE,
        "OPENROUTER_FREE_ONLY": _FREE_ONLY_RE,
        "GEMINI_API_KEY": _GEMINI_KEY_RE,
        "GEMINI_MODEL": _GEMINI_MODEL_RE,
        "OPENAI_API_KEY": re.compile(r"^\s*(?:export\s+)?OPENAI_API_KEY\s*="),
        "OPENAI_MODEL": re.compile(r"^\s*(?:export\s+)?OPENAI_MODEL\s*="),
        "ANTHROPIC_API_KEY": re.compile(r"^\s*(?:export\s+)?ANTHROPIC_API_KEY\s*="),
        "ANTHROPIC_MODEL": re.compile(r"^\s*(?:export\s+)?ANTHROPIC_MODEL\s*="),
        "NVIDIA_API_KEY": re.compile(r"^\s*(?:export\s+)?NVIDIA_API_KEY\s*="),
        "NVIDIA_MODEL": re.compile(r"^\s*(?:export\s+)?NVIDIA_MODEL\s*="),
    }
    output = []
    written = set()
    for line in lines:
        matched = next((name for name, pattern in patterns.items() if pattern.match(line)), None)
        if matched in updates:
            if matched not in written:
                output.append(matched + "=" + updates[matched])
                written.add(matched)
        else:
            output.append(line)
    for name, value in updates.items():
        if name not in written:
            output.append(name + "=" + value)
    payload = ("\n".join(output).rstrip() + "\n").encode("utf-8")
    fd, temporary = tempfile.mkstemp(prefix=target.name + ".", suffix=".tmp", dir=target.parent)
    try:
        if os.name != "nt":
            os.fchmod(fd, 0o600)
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, target)
    finally:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass


def save_gemini_config(path, api_key: str, model: str = "gemini-3.8-flash") -> None:
    """Save Gemini setup locally while preserving unrelated environment values.

    The secret is neither returned nor logged. UI callers should clear the input
    control after this function returns.
    """
    token = str(api_key or "").strip()
    if not token or "\n" in token or "\r" in token or len(token) < 12:
        raise ValueError("Enter a valid single-line Gemini API key.")
    selected = str(model or "gemini-3.8-flash").strip()
    if not selected or "\n" in selected or "\r" in selected or len(selected) > 120:
        raise ValueError("Enter a valid single-line Gemini model ID.")
    _atomic_update(path, {
        "GEMINI_API_KEY": token,
        "GEMINI_MODEL": selected,
        "ALICE_PRIMARY_PROVIDER": "gemini",
        "ALICE_RUNTIME_MODE": "gemini_primary",
    })
    os.environ["GEMINI_API_KEY"] = token
    os.environ["GEMINI_MODEL"] = selected
    os.environ["ALICE_PRIMARY_PROVIDER"] = "gemini"
    os.environ["ALICE_RUNTIME_MODE"] = "gemini_primary"


def save_gemini_model(path, model: str) -> None:
    """Change the Gemini model without reading or rewriting its API key."""
    selected=str(model or "").strip()
    if not selected or "\n" in selected or "\r" in selected or len(selected)>120:
        raise ValueError("Enter a valid single-line Gemini model ID.")
    _atomic_update(path,{"GEMINI_MODEL":selected,
                         "ALICE_PRIMARY_PROVIDER":"gemini",
                         "ALICE_RUNTIME_MODE":"gemini_primary"})
    os.environ["GEMINI_MODEL"]=selected
    os.environ["ALICE_PRIMARY_PROVIDER"]="gemini"
    os.environ["ALICE_RUNTIME_MODE"]="gemini_primary"


def save_hosted_provider_config(path, provider: str, api_key: str, model: str) -> None:
    """Save an explicitly selected BYOK provider to ALICE's local .env file.

    This accepts only provider names with built-in HTTPS endpoints. Values are
    never returned or logged. It does not enable automatic fallback.
    """
    name = str(provider or "").strip().lower()
    if name not in _PROVIDER_ENV:
        raise ValueError("Choose a supported hosted provider.")
    key_name, model_name = _PROVIDER_ENV[name]
    token = str(api_key or "").strip()
    selected = str(model or "").strip()
    if not token or len(token) > 4096 or "\n" in token or "\r" in token:
        raise ValueError("Enter a valid single-line API key.")
    if not selected or len(selected) > 160 or "\n" in selected or "\r" in selected:
        raise ValueError("Enter a valid model ID.")
    mode = name + "_primary"
    _atomic_update(path, {key_name: token, model_name: selected,
                          "ALICE_PRIMARY_PROVIDER": name,
                          "ALICE_RUNTIME_MODE": mode})
    os.environ[key_name] = token
    os.environ[model_name] = selected
    os.environ["ALICE_PRIMARY_PROVIDER"] = name
    os.environ["ALICE_RUNTIME_MODE"] = mode


def save_openrouter_config(path, api_key: str, model: str = "openrouter/auto", *, free_only: bool | None = None) -> None:
    """Atomically persist the key/model while retaining unrelated .env entries."""
    api_key = str(api_key or "").strip()
    if not api_key or "\n" in api_key or "\r" in api_key:
        raise ValueError("A single-line OpenRouter API key is required")
    model = str(model or "openrouter/auto").strip() or "openrouter/auto"
    if "\n" in model or "\r" in model:
        raise ValueError("Model must be a single line")
    updates = {"OPENROUTER_API_KEY": api_key, "OPENROUTER_MODEL": "openrouter/free" if free_only else model,
               "ALICE_PRIMARY_PROVIDER": "openrouter", "ALICE_RUNTIME_MODE": "openrouter_primary"}
    if free_only is not None:
        updates["OPENROUTER_FREE_ONLY"] = "true" if free_only else "false"
    _atomic_update(path, updates)
    os.environ["OPENROUTER_API_KEY"] = api_key
    os.environ["OPENROUTER_MODEL"] = updates["OPENROUTER_MODEL"]
    os.environ["ALICE_PRIMARY_PROVIDER"] = "openrouter"
    os.environ["ALICE_RUNTIME_MODE"] = "openrouter_primary"
    if free_only is not None:
        os.environ["OPENROUTER_FREE_ONLY"] = updates["OPENROUTER_FREE_ONLY"]


def save_runtime_mode(path, mode: str) -> None:
    """Persist the local-only brain policy without touching any API keys."""
    mode = str(mode or "").strip().lower()
    if mode not in {"local_required", "local-only", "local_only", "local", "offline"}:
        mode=mode.removesuffix("_primary")
        if mode not in {"gemini","openai","anthropic","groq","openrouter","nvidia"}:
            raise ValueError("Choose local-only or a supported explicit provider mode.")
        _atomic_update(path,{"ALICE_RUNTIME_MODE":mode+"_primary","ALICE_PRIMARY_PROVIDER":mode})
        os.environ["ALICE_RUNTIME_MODE"]=mode+"_primary"
        os.environ["ALICE_PRIMARY_PROVIDER"]=mode
        return
    _atomic_update(path, {"ALICE_RUNTIME_MODE": "local_required"})
    os.environ["ALICE_RUNTIME_MODE"] = "local_required"


def save_local_fast_model(path, model: str, installed_models) -> None:
    """Select an already-installed small local model for short, simple chat."""
    model = str(model or "").strip()
    if not model or "\n" in model or "\r" in model:
        raise ValueError("Choose an installed local quick-chat model")
    available = {str(name).strip() for name in installed_models or [] if str(name).strip()}
    if model not in available:
        raise ValueError("The selected quick-chat model is not installed in Ollama")
    _atomic_update(path, {"ALICE_LOCAL_FAST_MODEL": model})
    os.environ["ALICE_LOCAL_FAST_MODEL"] = model


def save_groq_config(path, api_key: str, model: str = "openai/gpt-oss-120b") -> None:
    """Atomically persist a Groq key and model without touching other providers."""
    api_key = str(api_key or "").strip()
    if not api_key or "\n" in api_key or "\r" in api_key:
        raise ValueError("A single-line Groq API key is required")
    model = str(model or "openai/gpt-oss-120b").strip()
    if not model or "\n" in model or "\r" in model:
        raise ValueError("Model must be a single line")
    _atomic_update(path, {"GROQ_API_KEY": api_key, "GROQ_MODEL": model,
                          "ALICE_PRIMARY_PROVIDER": "groq", "ALICE_RUNTIME_MODE":"groq_primary", "OPENROUTER_FREE_ONLY": "false"})
    os.environ["GROQ_API_KEY"]=api_key; os.environ["GROQ_MODEL"]=model
    os.environ["ALICE_PRIMARY_PROVIDER"]="groq"; os.environ["ALICE_RUNTIME_MODE"]="groq_primary"


def save_groq_preferences(path, model: str) -> None:
    """Persist a Groq model without reading or rewriting its API key."""
    model = str(model or "openai/gpt-oss-120b").strip()
    if not model or "\n" in model or "\r" in model:
        raise ValueError("Model must be a single line")
    _atomic_update(path, {"GROQ_MODEL": model, "ALICE_PRIMARY_PROVIDER": "groq", "ALICE_RUNTIME_MODE":"groq_primary",
                          "OPENROUTER_FREE_ONLY": "false"}, require_existing=("GROQ_API_KEY",))


def migrate_misfiled_groq_key(path) -> bool:
    """Move a Groq-format key accidentally saved in the OpenRouter slot.

    Only a value with Groq's documented ``gsk_`` prefix is moved, and an
    existing Groq key always wins. The key is never returned or logged.
    """
    target=Path(path)
    if not target.is_file():
        return False
    lines=target.read_text(encoding="utf-8-sig").splitlines()
    openrouter_idx=next((i for i,line in enumerate(lines) if _KEY_RE.match(line)),None)
    if openrouter_idx is None:
        return False
    value=_env_value(lines,"OPENROUTER_API_KEY")
    if not value.startswith("gsk_"):
        return False
    groq_idx=next((i for i,line in enumerate(lines) if _GROQ_KEY_RE.match(line)),None)
    if groq_idx is None:
        lines[openrouter_idx]="GROQ_API_KEY="+value
    else:
        # If the old field now contains a Groq-format key, it was likely just
        # re-entered there through the legacy UI; prefer that latest value.
        lines[groq_idx]="GROQ_API_KEY="+value
        lines.pop(openrouter_idx)
    if not any(_GROQ_MODEL_RE.match(line) for line in lines):
        lines.append("GROQ_MODEL=openai/gpt-oss-120b")
    replaced_primary=False
    replaced_free=False
    for index,line in enumerate(lines):
        if _PRIMARY_RE.match(line):
            lines[index]="ALICE_PRIMARY_PROVIDER=groq"; replaced_primary=True
        elif _FREE_ONLY_RE.match(line):
            lines[index]="OPENROUTER_FREE_ONLY=false"; replaced_free=True
    if not replaced_primary: lines.append("ALICE_PRIMARY_PROVIDER=groq")
    if not replaced_free: lines.append("OPENROUTER_FREE_ONLY=false")
    payload=("\n".join(lines).rstrip()+"\n").encode("utf-8")
    fd,temporary=tempfile.mkstemp(prefix=target.name+".",suffix=".tmp",dir=target.parent)
    try:
        if os.name!="nt": os.fchmod(fd,0o600)
        with os.fdopen(fd,"wb") as stream:
            stream.write(payload); stream.flush(); os.fsync(stream.fileno())
        os.replace(temporary,target)
    finally:
        try: os.unlink(temporary)
        except FileNotFoundError: pass
    return True


def save_openrouter_preferences(path, model: str, *, free_only: bool) -> None:
    """Persist model preferences without reading, returning, or rewriting the API key."""
    model = str(model or "openrouter/auto").strip() or "openrouter/auto"
    if "\n" in model or "\r" in model:
        raise ValueError("Model must be a single line")
    if free_only:
        model = "openrouter/free"
    _atomic_update(path, {
        "OPENROUTER_MODEL": model,
        "OPENROUTER_FREE_ONLY": "true" if free_only else "false",
        "ALICE_PRIMARY_PROVIDER": "openrouter",
        "ALICE_RUNTIME_MODE":"openrouter_primary",
    }, require_existing=("OPENROUTER_API_KEY",))
    os.environ["OPENROUTER_MODEL"] = model
    os.environ["OPENROUTER_FREE_ONLY"] = "true" if free_only else "false"
    os.environ["ALICE_PRIMARY_PROVIDER"] = "openrouter"
    os.environ["ALICE_RUNTIME_MODE"] = "openrouter_primary"
