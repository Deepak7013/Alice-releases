"""Safe capability/plugin registry for Alice.

Plugins are metadata-first. A plugin must pass validation before it can be
activated. Activation never grants permissions; tools remain subject to
Alice's central policy and the host permission manager.
"""
from __future__ import annotations
import hashlib, json, re, time
from dataclasses import asdict, dataclass, field
from pathlib import Path

_NAME = re.compile(r'^[a-z][a-z0-9_-]{1,63}$')
_VERSION = re.compile(r'^\d+\.\d+\.\d+(?:[-+][0-9A-Za-z.-]+)?$')

class PluginValidationError(ValueError):
    pass

@dataclass
class PluginManifest:
    name: str
    version: str
    description: str
    entrypoint: str
    capabilities: list[str] = field(default_factory=list)
    permissions: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    enabled: bool = False
    installed_at: float = 0.0
    content_hash: str = ''

class PluginRegistry:
    def __init__(self, root=None):
        self.root = Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.plugins_dir = self.root / 'plugins'
        self.state_path = self.root / 'alice_workspace' / 'plugins.json'
        self.plugins_dir.mkdir(parents=True, exist_ok=True)
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.plugins: dict[str, PluginManifest] = {}
        self._load()

    def _load(self):
        if not self.state_path.exists(): return
        try:
            raw=json.loads(self.state_path.read_text(encoding='utf-8'))
            self.plugins={k:PluginManifest(**v) for k,v in raw.items()}
        except Exception:
            self.plugins={}

    def _save(self):
        self.state_path.write_text(json.dumps({k:asdict(v) for k,v in self.plugins.items()}, indent=2), encoding='utf-8')

    @staticmethod
    def _validate_name(name):
        if not _NAME.fullmatch(name): raise PluginValidationError('Invalid plugin name')
    @staticmethod
    def _validate_version(version):
        if not _VERSION.fullmatch(version): raise PluginValidationError('Version must be MAJOR.MINOR.PATCH')

    def validate_manifest(self, manifest: PluginManifest):
        self._validate_name(manifest.name)
        self._validate_version(manifest.version)
        if not manifest.description or len(manifest.description)>2000: raise PluginValidationError('Invalid description')
        if not re.fullmatch(r'[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_.]*', manifest.entrypoint):
            raise PluginValidationError('Entrypoint must be module:function')
        if len(manifest.capabilities)>32 or len(manifest.permissions)>32 or len(manifest.dependencies)>64:
            raise PluginValidationError('Manifest list too large')
        for value in manifest.capabilities + manifest.permissions + manifest.dependencies:
            if not re.fullmatch(r'[A-Za-z0-9_.:/=<>~+*-]{1,160}', value):
                raise PluginValidationError('Invalid manifest value')
        forbidden={'credential_access','security_bypass','persistence_evasion','self_core_write'}
        if forbidden.intersection(manifest.permissions):
            raise PluginValidationError('Forbidden plugin permission')
        return True

    def content_hash(self, path):
        h=hashlib.sha256()
        for p in sorted(Path(path).rglob('*')):
            if p.is_file() and '__pycache__' not in p.parts:
                h.update(str(p.relative_to(path)).encode()); h.update(p.read_bytes())
        return h.hexdigest()

    def register(self, manifest: PluginManifest, source_path=None):
        self.validate_manifest(manifest)
        if source_path:
            src=Path(source_path).resolve()
            if not src.is_relative_to(self.plugins_dir.resolve()):
                raise PluginValidationError('Plugin source must be inside plugins directory')
            manifest.content_hash=self.content_hash(src)
        manifest.installed_at=manifest.installed_at or time.time()
        self.plugins[manifest.name]=manifest
        self._save()
        return asdict(manifest)

    def enable(self, name):
        p=self.plugins.get(name)
        if not p: raise KeyError(name)
        p.enabled=True; self._save(); return asdict(p)

    def disable(self, name):
        p=self.plugins.get(name)
        if not p: raise KeyError(name)
        p.enabled=False; self._save(); return asdict(p)

    def get(self,name): return self.plugins.get(name)
    def enabled(self): return [asdict(p) for p in self.plugins.values() if p.enabled]
    def inventory(self): return [asdict(p) for p in sorted(self.plugins.values(), key=lambda x:x.name)]
