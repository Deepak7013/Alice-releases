from __future__ import annotations
import re
from pathlib import Path
from alice.knowledge.store import KnowledgeStore
from alice.knowledge.retriever import KnowledgeRetriever
from alice.knowledge.models import SourceEvidence, EvidenceKind
from alice.knowledge.security import sanitize
from alice.memory.manager import MemoryManager

class ChatLearningLibrary:
    """Local learning layer for chat. Conversation is retained separately; this
    layer extracts durable, user-provided knowledge and retrieves it locally.
    No external AI call is required for ingestion or retrieval.
    """
    DURABLE_PATTERNS = [
        ("preference", re.compile(r"(?i)\b(?:i|we) (?:prefer|like|love|hate|don't like|do not like|always|usually)\b(.{3,500})")),
        ("preference", re.compile(r"(?i)\bmy preference is\b(.{3,500})")),
        ("fact", re.compile(r"(?i)\b(?:my|our) (?:name|project|device|laptop|phone|goal|setup|system) (?:is|are|called)\b(.{2,500})")),
        ("instruction", re.compile(r"(?i)\b(?:remember|always remember|keep in mind|from now on|going forward|for future upgrades)\b[:,-]?\s*(.{3,800})")),
        ("instruction", re.compile(r"(?i)\b(?:make sure|ensure)\s+(?:alice|you)\s+(.{3,800})")),
    ]
    MEMORY_QUERY = re.compile(r"(?i)^(?:what do you remember|what do you know about me|what do you know about alice|show my memories|show alice memories|list memories|what is the active alice project rule|what is the current alice project rule|what project rule did i teach you|show active alice project rules)\b")

    def __init__(self, root=None):
        self.root=Path(root or Path(__file__).resolve().parents[2]).resolve()
        self.path=self.root/"alice_workspace"/"library"/"alice_knowledge.sqlite3"
        self.store=KnowledgeStore(self.path)
        self.retriever=KnowledgeRetriever(self.store)
        self.manager=MemoryManager(self.root)

    def learn_user_turn(self, text: str) -> int:
        cleaned, redacted, authority = sanitize(str(text))
        if redacted or authority:
            # Never turn credential-bearing or authority-escalation text into durable knowledge.
            return 0
        added=0
        for topic, pattern in self.DURABLE_PATTERNS:
            for m in pattern.finditer(cleaned):
                full=m.group(0).strip()[:2000]
                if len(full)<8: continue
                if self.store.duplicate_by_hash(__import__('hashlib').sha256(full.encode()).hexdigest()): continue
                self.store.create(topic, full, SourceEvidence(kind=EvidenceKind.USER_PROVIDED.value, title="ALICE chat", locator="chat"), tags=["chat","user_learned"], confidence=0.92, trusted=True)
                added+=1
        return added

    def learn_verified_outcome(self, request: str, outcome: str, version: str = ""):
        text=f"Task: {request}\nOutcome: {outcome}"[:5000]
        cleaned, redacted, authority=sanitize(text)
        if redacted or authority: return False
        h=__import__('hashlib').sha256(cleaned.encode()).hexdigest()
        if self.store.duplicate_by_hash(h): return False
        self.store.create("solution", cleaned, SourceEvidence(kind=EvidenceKind.USER_PROVIDED.value, title="ALICE verified chat outcome", locator=version or "runtime"), tags=["chat","verified_outcome"], confidence=0.80, trusted=False)
        return True

    def context_for(self, query: str, limit=6) -> str:
        return self.retriever.context(query, limit=limit)

    def local_memory_answer(self, query: str) -> str | None:
        if not self.MEMORY_QUERY.match(query.strip()): return None
        items=self.retriever.retrieve("user project preference instruction fact", limit=12)
        structured=[]
        try:
            # Structured memories are a separate durable layer. Include them
            # here with short stable IDs so edits and forgetting can target one
            # exact record rather than a fuzzy batch.
            structured=self.manager.list(limit=30)
        except Exception:
            structured=[]
        if not items and not structured: return "I don't have any durable memories yet."
        lines=["Here is what I currently remember locally:"]
        seen=set()
        for item in items:
            text=str(item.text).strip()
            if text and text.lower() not in seen:
                lines.append(f"- {text}"); seen.add(text.lower())
        if structured:
            lines.append("\nActive structured memories (use the ID to correct or forget one):")
            for rec in structured:
                text=f"[{rec.kind}] {rec.key}: {rec.value} (ID: {rec.id[:8]})".strip()
                if text.lower() not in seen:
                    lines.append(f"- {text}"); seen.add(text.lower())
        return "\n".join(lines)
