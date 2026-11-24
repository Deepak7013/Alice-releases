"""Canonical response assembly for chunked provider output."""
from __future__ import annotations
from dataclasses import dataclass

@dataclass(frozen=True)
class StreamedResponse:
    text: str
    complete: bool
    chunks: int
    reason: str

class ResponseStreamAssembler:
    """Buffer text chunks and expose content only through an explicit final result.

    This class does not call providers or UI/voice side effects. Callers should render
    the returned canonical text and synchronize speech only after finish().
    """
    def __init__(self, *, max_chars: int = 1_000_000) -> None:
        if isinstance(max_chars, bool) or int(max_chars) < 1:
            raise ValueError("max_chars_must_be_positive")
        self.max_chars=int(max_chars); self._parts: list[str]=[]; self._chars=0; self._closed=False

    def add(self, chunk: object) -> bool:
        if self._closed: return False
        text=str(chunk if chunk is not None else "")
        if not text: return True
        if self._chars+len(text)>self.max_chars:
            self._closed=True; self._parts.clear(); self._chars=0
            return False
        self._parts.append(text); self._chars+=len(text); return True

    def finish(self) -> StreamedResponse:
        if self._closed:
            return StreamedResponse("The response could not be completed because the stream exceeded its safety limit.",False,0,"stream_limit_exceeded")
        self._closed=True; text="".join(self._parts).strip()
        if not text:
            return StreamedResponse("I received an empty response and could not produce a usable answer.",False,len(self._parts),"empty_stream")
        return StreamedResponse(text,True,len(self._parts),"response_complete")

    def abort(self, reason: str = "provider_stream_failed") -> StreamedResponse:
        self._closed=True; self._parts.clear(); self._chars=0
        clean=str(reason or "provider_stream_failed").strip()[:120]
        return StreamedResponse("The response was interrupted before completion. Please try again.",False,0,clean)
