"""Gate streamed response delivery so incomplete output is never spoken as complete."""
from __future__ import annotations
from dataclasses import dataclass
from alice.ui.response_delivery import canonicalize_response, ResponseDelivery
from alice.voice.delivery_sync import synchronize_response, DeliverySyncDecision
from alice.ui.response_stream import ResponseStreamAssembler, StreamedResponse

@dataclass(frozen=True)
class StreamDelivery:
    response: StreamedResponse
    delivery: ResponseDelivery
    sync: DeliverySyncDecision
    complete: bool
    reason: str

class ResponseStreamDeliveryGate:
    """Only completed assembled text is eligible for synchronized voice output."""
    def deliver(self, stream: ResponseStreamAssembler, *, voice_enabled: bool = True) -> StreamDelivery:
        result=stream.finish()
        if not result.complete:
            canonical=canonicalize_response({"status":"failed","error":result.text})
            sync=synchronize_response(canonical.text,voice_enabled=False)
            return StreamDelivery(result,canonical,sync,False,result.reason)
        canonical=canonicalize_response({"status":"completed","result":result.text})
        sync=synchronize_response(canonical.text,voice_enabled=voice_enabled)
        return StreamDelivery(result,canonical,sync,True,"stream_delivery_complete" if sync.speak or not voice_enabled else "stream_delivery_text_only")
