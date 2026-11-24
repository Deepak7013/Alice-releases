"""Thread-safe speech cancellation with best-effort active-engine stop callbacks."""
from __future__ import annotations
from dataclasses import dataclass
from threading import Event, RLock
from collections.abc import Callable

@dataclass(frozen=True)
class CancellationResult:
    cancelled: bool
    callbacks_invoked: int
    callback_failures: int
    reason: str

class SpeechCancellation:
    """Idempotent cancellation signal; callbacks should stop active audio if supported."""
    def __init__(self) -> None:
        self._event=Event(); self._lock=RLock(); self._callbacks: list[Callable[[], object]]=[]
        self._reason=""
    @property
    def cancelled(self) -> bool: return self._event.is_set()
    @property
    def reason(self) -> str:
        with self._lock: return self._reason
    def register_stop(self, callback: Callable[[], object]) -> bool:
        if not callable(callback): return False
        call_now=False
        with self._lock:
            if self._event.is_set(): call_now=True
            else: self._callbacks.append(callback)
        if call_now:
            try: callback()
            except Exception: pass
        return True
    def unregister_stop(self, callback: Callable[[], object]) -> bool:
        """Remove a registered stop callback after its speech run ends."""
        with self._lock:
            for index, registered in enumerate(self._callbacks):
                if registered is callback:
                    del self._callbacks[index]
                    return True
        return False

    def cancel(self, reason: str = "user_requested") -> CancellationResult:
        with self._lock:
            if self._event.is_set(): return CancellationResult(True,0,0,self._reason)
            self._reason=str(reason or "user_requested").strip()[:120] or "user_requested"
            self._event.set(); callbacks=tuple(self._callbacks); self._callbacks.clear()
        failures=0
        for callback in callbacks:
            try: callback()
            except Exception: failures+=1
        return CancellationResult(True,len(callbacks),failures,self._reason)
