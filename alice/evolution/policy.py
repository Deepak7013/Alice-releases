from pathlib import Path

class EvolutionPolicy:
    """Safety policy for source evolution."""

    protected = {
        "__init__.py",
        "security",
        "permissions",
        "secrets",
        "credentials",
    }

    def validate_paths(self, root: str, files: list[str]) -> tuple[bool, str]:
        root_path = Path(root).resolve()
        for raw in files:
            p = (root_path / raw).resolve()
            if root_path not in p.parents and p != root_path:
                return False, f"path outside source root: {raw}"
            if p.name in self.protected or any(part in self.protected for part in p.parts):
                return False, f"protected path: {raw}"
        return True, "ok"

    def validate_scope(self, requested_permissions: list[str]) -> tuple[bool, str]:
        forbidden = {"credential_theft", "persistence", "evasion", "security_bypass"}
        hit = forbidden.intersection(requested_permissions)
        if hit:
            return False, f"forbidden scope: {sorted(hit)}"
        return True, "ok"
