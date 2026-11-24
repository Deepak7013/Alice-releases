from __future__ import annotations
import shlex


def android_text_command(text):
    """Build one safely quoted Android `input text` shell command."""
    safe = str(text).replace("%", "%25").replace(" ", "%s").replace("&", "%26").replace(";", "%3B")
    return "input text " + shlex.quote(safe)


class WhatsAppInterface:
    PACKAGE="com.whatsapp"
    def __init__(self, control, notifications, consent, receipt_verifier=None):
        self.control,self.notifications,self.consent=control,notifications,consent
        self.receipt_verifier=receipt_verifier
    def recent(self, device_id):
        if not self.consent.allowed(device_id,"messages.read"): raise PermissionError("consent required: messages.read")
        return self.notifications.list(package=self.PACKAGE)
    def open(self, device_id):
        if not self.consent.allowed(device_id,"messages.open"): raise PermissionError("consent required: messages.open")
        return self.control.adb.launch(self.control._target(device_id),self.PACKAGE)
    def draft_reply(self, device_id, text):
        if not self.consent.allowed(device_id,"messages.draft"): raise PermissionError("consent required: messages.draft")
        self.open(device_id)
        return self.control.text(device_id,text)
    def send_reply(self, device_id, text, chat=None):
        if not self.consent.allowed(device_id,"messages.send"): raise PermissionError("consent required: messages.send")
        # Never type into whichever conversation happens to be open. A
        # pre-send UI observation must identify the requested chat and provide
        # a message baseline before ALICE performs any side effect.
        if not chat or not self.receipt_verifier:
            return {
                "status": "not_sent", "verified": False,
                "verification_reason": "chat_or_receipt_observer_unavailable",
            }
        try:
            baseline_ids = self.receipt_verifier.snapshot(device_id, chat)
        except Exception:
            baseline_ids = None
        if baseline_ids is None:
            return {
                "status": "not_sent", "verified": False,
                "verification_reason": "requested_chat_not_confirmed_before_send",
            }
        prepare_message = getattr(self.control, "prepare_message", None)
        if not callable(prepare_message):
            return {
                "status": "not_sent", "verified": False,
                "verification_reason": "verified_message_composer_unavailable",
            }
        try:
            prepared = prepare_message(device_id, chat, text)
        except Exception as exc:
            return {
                "status": "not_sent", "verified": False,
                "verification_reason": f"message_composition_failed:{type(exc).__name__}",
                "draft_may_remain": True,
            }
        if not isinstance(prepared, dict) or prepared.get("verified") is not True:
            result = {
                "status": "not_sent", "verified": False,
                "verification_reason": (
                    str(prepared.get("verification_reason", "message_composition_not_verified"))[:120]
                    if isinstance(prepared, dict) else "message_composition_not_verified"
                ),
            }
            if isinstance(prepared, dict) and prepared.get("draft_may_remain") is True:
                result["draft_may_remain"] = True
            return result
        command_result = self.control.adb.shell(self.control._target(device_id),"input keyevent 66")
        # A successful ADB command only proves that Enter was issued. Without
        # observing the resulting chat state, delivery must remain unverified.
        result = {
            "status": "attempted",
            "verified": False,
            "evidence": "send_key_command_returned",
            "command_result": command_result,
            # The active executor consumes this before returning the tool result.
            # These are local message fingerprints, not message contents.
            "_postcondition_context": {"baseline_message_ids": sorted(str(x) for x in baseline_ids)},
        }
        try:
            observation = self.receipt_verifier.verify(device_id, chat, text, baseline_ids)
        except Exception:
            result["verification_reason"] = "receipt_observer_failed"
            return result
        required = ("observed", "conversation_matches", "outgoing", "content_matches", "newly_observed")
        if not isinstance(observation, dict) or any(observation.get(key) is not True for key in required):
            result["verification_reason"] = "observable_delivery_evidence_incomplete"
            return result
        result.update(
            status="verified",
            verified=True,
            evidence={key: True for key in required},
        )
        # Keep any provider message identifier for audit correlation, but never
        # copy the message body or arbitrary observer data into the receipt.
        message_id = observation.get("message_id")
        if isinstance(message_id, (str, int)) and str(message_id):
            result["evidence"]["message_id"] = str(message_id)[:160]
        return result
