from __future__ import annotations
import platform,sys
from dataclasses import dataclass
@dataclass
class DeploymentProfile:
    os:str; python:str; mode:str='development'; writable:bool=True
class DeploymentManager:
    def __init__(self,profile=None): self.profile=profile or DeploymentProfile(platform.system(),sys.version.split()[0])
    def preflight(self):
        return {'ok':bool(self.profile.os and self.profile.python),'os':self.profile.os,'python':self.profile.python,'mode':self.profile.mode,'writable':self.profile.writable}
    def safe_for_autostart(self): return self.profile.mode in {'development','production'} and self.profile.writable
    def describe(self): return self.preflight()
