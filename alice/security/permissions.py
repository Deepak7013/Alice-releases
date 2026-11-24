from __future__ import annotations

import re
from enum import Enum


class Risk(Enum):
    READ = "read"
    WRITE = "write"
    EXECUTE = "execute"
    EXTERNAL = "external"
    FINANCIAL = "financial"
    SYSTEM = "system"


class PermissionManager:
    """Command permission gate.

    A command is considered automatically safe only when it is a narrowly
    matched read-only command. Shell metacharacters are never allowed through
    the automatic path, preventing strings such as ``python --version & ...``
    from being mistaken for a harmless command. Everything else requires an
    explicit user approval prompt.
    """

    SAFE_EXACT = {
        "dir", "ls", "pwd", "where", "whoami", "hostname", "ver",
        "python --version", "py --version", "pip --version", "git --version",
        "node --version", "npm --version",
    }
    SAFE_PREFIXES = ("dir ", "ls ", "where ")
    SHELL_META = re.compile(r"[&|<>^\n\r]")
    CONSEQUENTIAL = re.compile(
        r"(?i)\b(buy|purchase|checkout|pay|transfer|send\s+money|delete|format|"
        r"shutdown|publish|post|send\s+email|submit|accept\s+terms|"
        r"change\s+password|create\s+account|grant|share\s+secret)\b"
    )

    def is_safe_command(self, command):
        if not isinstance(command, str):
            return False
        c = command.strip().lower()
        if not c or self.SHELL_META.search(c):
            return False
        if c in self.SAFE_EXACT:
            return True
        return any(c.startswith(prefix) for prefix in self.SAFE_PREFIXES)

    def request(self, action, details=""):
        print(f"\n[ALICE PERMISSION]\n{action}\n{details}\nType YES to allow, anything else to deny.")
        return input("> ").strip().upper() == "YES"

    def request_command(self, command):
        return self.request(
            "Alice wants to execute a Windows command",
            f"Command: {command}",
        )

    def needs_confirmation(self, tool_name, args=None):
        text = tool_name + " " + str(args or {})
        if self.CONSEQUENTIAL.search(text):
            return True
        return tool_name in {
            "run_windows_command", "self_update_git", "self_apply_patch",
            "self_repair", "self_snapshot", "install_dependency",
        }
