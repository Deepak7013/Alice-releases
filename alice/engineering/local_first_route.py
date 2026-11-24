from __future__ import annotations
from dataclasses import dataclass, asdict
@dataclass(frozen=True)
class LocalFirstRoute:
    capability: str; local_available: bool; local_verified: bool; external_allowed: bool; route: str
    def as_dict(self): return asdict(self)
def choose_route(capability, local_available, local_verified, external_allowed=False):
    a,v,e=bool(local_available),bool(local_verified),bool(external_allowed)
    route='local' if a and v else ('external' if e else 'blocked_unverified')
    return LocalFirstRoute(str(capability),a,v,e,route)
