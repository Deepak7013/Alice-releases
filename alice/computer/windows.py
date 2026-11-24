from alice.alice.computer.windows import *


def open_app(command: str):
    """Backward-compatible desktop launcher used by the Alice UI/tool registry."""
    if not isinstance(command, str) or not command.strip():
        return {"ok": False, "error": "empty application command"}
    try:
        import subprocess
        import ntpath
        # Use Windows path semantics even when this module is inspected or
        # tested from a non-Windows host. Passing one absolute EXE as an argv
        # item preserves spaces in its filename and avoids command-line splits.
        is_absolute_windows_path = ntpath.isabs(command)
        launch=[command] if is_absolute_windows_path and ntpath.splitext(command)[1].casefold()=='.exe' else command
        process = subprocess.Popen(launch, shell=False)
        return {"ok": True, "action": "open_app", "target": command, "pid": int(process.pid)}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "action": "open_app", "target": command}


def open_url(url: str):
    """Open an HTTP(S) URL using the user's default browser."""
    if not isinstance(url, str) or not url.strip():
        return {"ok": False, "error": "empty URL"}
    from urllib.parse import urlparse
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"ok": False, "error": "only valid HTTP/HTTPS URLs are allowed"}
    try:
        import webbrowser
        opened = webbrowser.open(url)
        return {"ok": bool(opened), "action": "open_url", "url": url}
    except Exception as exc:
        return {"ok": False, "error": str(exc), "action": "open_url", "url": url}
