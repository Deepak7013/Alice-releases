"""Thread-safe bounded in-memory cache for local speech payloads."""
from __future__ import annotations
from collections import OrderedDict
from dataclasses import dataclass
import re
from threading import RLock
from time import monotonic

_KEY = re.compile(r"^[0-9a-f]{64}$")
@dataclass(frozen=True)
class CacheIntegrity:
    consistent: bool
    entries: int
    bytes_used: int
    bounds_ok: bool
    keys_valid: bool
    payloads_valid: bool
    reason: str

@dataclass(frozen=True)
class CacheStats:
    entries: int
    bytes_used: int
    max_entries: int
    max_bytes: int
    hits: int = 0
    misses: int = 0
    evictions: int = 0

class LocalSpeechCache:
    """Thread-safe process-local LRU cache. Payloads are never persisted or uploaded."""
    def __init__(self, *, max_entries: int = 128, max_bytes: int = 32 * 1024 * 1024,
                 ttl_seconds: float | None = None, clock=None) -> None:
        if isinstance(max_entries, bool) or int(max_entries) < 1: raise ValueError("max_entries_must_be_positive")
        if isinstance(max_bytes, bool) or int(max_bytes) < 1: raise ValueError("max_bytes_must_be_positive")
        if ttl_seconds is not None and (isinstance(ttl_seconds, bool) or float(ttl_seconds) <= 0): raise ValueError("ttl_seconds_must_be_positive")
        self.max_entries=int(max_entries); self.max_bytes=int(max_bytes)
        self.ttl_seconds=None if ttl_seconds is None else float(ttl_seconds); self._clock=clock or monotonic
        self._expires: dict[str, float] = {}
        self._items: OrderedDict[str, bytes]=OrderedDict(); self._bytes=0; self._lock=RLock()
        self._hits=0; self._misses=0; self._evictions=0
    def get(self,key: object)->bytes|None:
        k=str(key or "")
        if not _KEY.fullmatch(k):
            with self._lock: self._misses += 1
            return None
        with self._lock:
            self._purge_expired_locked()
            value=self._items.get(k)
            if value is not None:
                self._hits += 1; self._items.move_to_end(k)
            else:
                self._misses += 1
            return value
    def put(self,key: object,payload: object)->bool:
        k=str(key or "")
        if not _KEY.fullmatch(k) or not isinstance(payload,(bytes,bytearray,memoryview)):return False
        value=bytes(payload)
        if not value or len(value)>self.max_bytes:return False
        with self._lock:
            self._purge_expired_locked()
            old=self._items.pop(k,None)
            self._expires.pop(k,None)
            if old is not None:self._bytes-=len(old)
            while self._items and (len(self._items)>=self.max_entries or self._bytes+len(value)>self.max_bytes):
                evicted_key,evicted=self._items.popitem(last=False);self._bytes-=len(evicted);self._expires.pop(evicted_key,None);self._evictions += 1
            self._items[k]=value;self._bytes+=len(value)
            if self.ttl_seconds is not None: self._expires[k]=self._clock()+self.ttl_seconds
            return True
    def clear(self)->None:
        with self._lock:self._items.clear();self._expires.clear();self._bytes=0

    def _purge_expired_locked(self)->None:
        now=self._clock()
        expired=[key for key,deadline in self._expires.items() if deadline <= now]
        for key in expired:
            value=self._items.pop(key,None)
            self._expires.pop(key,None)
            if value is not None: self._bytes-=len(value)

    def purge_expired(self)->int:
        """Remove expired entries and return the number removed."""
        with self._lock:
            before=len(self._items); self._purge_expired_locked(); return before-len(self._items)
    def stats(self)->CacheStats:
        with self._lock:return CacheStats(len(self._items),self._bytes,self.max_entries,self.max_bytes,self._hits,self._misses,self._evictions)

    def audit(self) -> CacheIntegrity:
        """Check cache invariants without mutating or repairing state."""
        with self._lock:
            entries = len(self._items)
            measured = sum(len(value) for value in self._items.values())
            bounds_ok = entries <= self.max_entries and measured <= self.max_bytes
            keys_valid = all(bool(_KEY.fullmatch(key)) for key in self._items)
            payloads_valid = all(isinstance(value, bytes) and bool(value) for value in self._items.values())
            expiry_valid = set(self._expires).issubset(self._items) and (self.ttl_seconds is None or set(self._expires) == set(self._items))
            consistent = bounds_ok and keys_valid and payloads_valid and measured == self._bytes and expiry_valid
            reason = "cache_integrity_ok" if consistent else "cache_integrity_failed"
            return CacheIntegrity(consistent, entries, measured, bounds_ok, keys_valid, payloads_valid, reason)
