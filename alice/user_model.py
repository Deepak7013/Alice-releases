from __future__ import annotations
from dataclasses import dataclass, asdict
from pathlib import Path
import json, time

@dataclass
class UserFact:
    key: str
    value: str
    confidence: float = 1.0
    source: str = 'interaction'
    verified: bool = False
    updated_at: float = 0.0

class UserModel:
    """Persistent, provenance-aware user/project preference model.

    This layer stores durable facts separately from raw conversation history and
    never treats a newly written fact as verified unless evidence is supplied.
    """
    VERSION = 'v3.48.0'
    def __init__(self, path: str|Path):
        self.path = Path(path)
        self.facts: dict[str, UserFact] = {}
        self.load()

    def learn(self, key: str, value: str, *, confidence=1.0, source='interaction', verified=False):
        key, value = str(key).strip(), str(value).strip()
        if not key or not value:
            raise ValueError('key/value required')
        fact = UserFact(key, value, max(0.0, min(1.0, float(confidence))), str(source), bool(verified), time.time())
        self.facts[key] = fact
        self.save()
        return fact

    def verify(self, key: str, *, evidence: str = 'verified interaction'):
        fact = self.facts.get(key)
        if fact is None:
            return None
        fact.verified = True
        fact.source = f'{fact.source}; {evidence}'
        fact.updated_at = time.time()
        self.save()
        return fact

    def get(self, key: str, verified_only=False):
        fact = self.facts.get(key)
        if verified_only and (fact is None or not fact.verified):
            return None
        return fact

    def search(self, text: str, verified_only=False):
        q = str(text).lower()
        return [f for f in self.facts.values() if (not verified_only or f.verified) and (q in f.key.lower() or q in f.value.lower())]

    def save(self):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix('.tmp')
        tmp.write_text(json.dumps({k: asdict(v) for k,v in self.facts.items()}, indent=2, ensure_ascii=False), encoding='utf-8')
        tmp.replace(self.path)

    def load(self):
        if not self.path.exists():
            return
        try:
            raw = json.loads(self.path.read_text(encoding='utf-8'))
            self.facts = {k: UserFact(**v) for k,v in raw.items()}
        except (OSError, ValueError, TypeError):
            self.facts = {}

    def context(self, query: str, limit=8):
        hits = self.search(query, verified_only=True)[:max(1, int(limit))]
        return '\n'.join(f'- {f.key}: {f.value} (confidence={f.confidence:.2f})' for f in hits)
