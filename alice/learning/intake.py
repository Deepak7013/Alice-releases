from __future__ import annotations
from dataclasses import dataclass, asdict
import hashlib, re

@dataclass(frozen=True)
class LearningDecision:
    accepted: bool
    reason: str
    topic: str
    text: str
    fingerprint: str
    confidence: float
    def as_dict(self): return asdict(self)

class LearningIntake:
    """Deterministic gate for turning chat into durable local knowledge.

    Explicit user teaching is accepted; credentials, authority escalation,
    and vague chatter are rejected before storage. The gate is advisory and
    never grants permissions.
    """
    SECRET = re.compile(r"(?i)(api[_ -]?key|password|passwd|secret|token|private[_ -]?key|seed phrase|mnemonic)\s*[:=]", re.I)
    AUTH = re.compile(r"(?i)\b(ignore|bypass|disable|remove|override)\b.*\b(permission|approval|security|safety|guard|gate)\b")
    EXPLICIT = re.compile(r"(?i)^(remember|from now on|going forward|for future|my preference is|i prefer|i like|my goal is|my project is)\b[:\s-]*(.+)$")
    def decide(self, text: str) -> LearningDecision:
        s=' '.join(str(text or '').split())[:2000]
        if not s: return LearningDecision(False,'empty','', '', '',0.0)
        if self.SECRET.search(s): return LearningDecision(False,'secret_like','', '', '',0.0)
        if self.AUTH.search(s): return LearningDecision(False,'authority_escalation','', '', '',0.0)
        m=self.EXPLICIT.match(s)
        if not m or len(m.group(2).strip())<3: return LearningDecision(False,'not_explicit','', '', '',0.0)
        lead=m.group(1).lower(); topic='instruction' if lead in {'remember','from now on','going forward','for future'} else 'preference' if 'preference' in lead or lead in {'i prefer','i like'} else 'goal' if 'goal' in lead else 'project' if 'project' in lead else 'fact'
        fp=hashlib.sha256(s.lower().encode()).hexdigest()[:24]
        return LearningDecision(True,'explicit_user_teaching',topic,s,fp,0.95)
