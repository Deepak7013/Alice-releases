from __future__ import annotations
import hashlib
from ..execution.postconditions import PostconditionResult
from ..android_intelligence.postconditions import (
    capture_android_text_baseline,
    type_android_text_with_baseline,
    verify_android_text_postcondition,
)


class WhatsAppAccessError(RuntimeError): pass
class WhatsAppReader:
    """Authorized-interface adapter. It never reads private app databases or bypasses security."""
    package='com.whatsapp'
    def __init__(self, notification_mirror=None, ui_adapter=None): self.notifications=notification_mirror; self.ui=ui_adapter
    def recent_notifications(self,limit=20):
        if not self.notifications: return []
        return self.notifications.list(self.package)[-limit:]
    def open(self,device):
        if not self.ui: raise WhatsAppAccessError('No authorized Android UI adapter connected')
        return self.ui.launch(device,self.package)
    def read_visible_chat(self,device,chat):
        if not self.ui: raise WhatsAppAccessError('No authorized Android UI adapter connected')
        return self.ui.read_visible_chat(device,chat)
    def draft_reply(self,device,chat,text):
        if not self.ui: raise WhatsAppAccessError('No authorized Android UI adapter connected')
        return self.ui.draft_reply(device,chat,text)


class VisibleChatDeliveryVerifier:
    """Verify a newly visible outgoing message through an authorized UI adapter.

    The adapter must return ``{"chat": name, "messages": [{"id": stable_id,
    "direction": "outgoing", "text": body}, ...]}`` from ``read_visible_chat``.
    Stable message IDs are required so an old matching message cannot be mistaken
    for delivery of the current send.
    """

    def __init__(self, ui_adapter):
        self.ui = ui_adapter

    def snapshot(self, device, chat):
        if not self.ui:
            return None
        try:
            view = self.ui.read_visible_chat(device, chat)
            messages = view.get("messages") if isinstance(view, dict) else None
            actual_chat = str(view.get("chat", "")).strip().casefold() if isinstance(view, dict) else ""
            if actual_chat != str(chat).strip().casefold() or not isinstance(messages, list):
                return None
            return frozenset(
                str(row["id"]) for row in messages
                if isinstance(row, dict) and row.get("id") not in (None, "")
            )
        except Exception:
            return None

    def verify(self, device, chat, text, baseline_ids):
        evidence = {
            "observed": False,
            "conversation_matches": False,
            "outgoing": False,
            "content_matches": False,
            "newly_observed": False,
        }
        if baseline_ids is None or not self.ui:
            return evidence
        try:
            view = self.ui.read_visible_chat(device, chat)
        except Exception:
            return evidence
        if not isinstance(view, dict):
            return evidence
        evidence["observed"] = True
        actual_chat = str(view.get("chat", "")).strip().casefold()
        evidence["conversation_matches"] = bool(actual_chat and actual_chat == str(chat).strip().casefold())
        messages = view.get("messages")
        if not evidence["conversation_matches"] or not isinstance(messages, list):
            return evidence
        prior_ids = set(baseline_ids)
        for row in messages:
            if not isinstance(row, dict) or row.get("id") in (None, ""):
                continue
            message_id = str(row["id"])
            if message_id in prior_ids:
                continue
            evidence["newly_observed"] = True
            direction = str(row.get("direction", "")).strip().casefold()
            body = str(row.get("text", ""))
            if direction != "outgoing" or body != str(text):
                continue
            evidence.update(outgoing=True, content_matches=True, message_id=message_id[:160])
            return evidence
        return evidence


def verify_whatsapp_send_postcondition(delivery_verifier, args, result):
    """Independently re-read the authorized UI after a send."""
    context = result.get("_postcondition_context") if isinstance(result, dict) else None
    baseline = context.get("baseline_message_ids") if isinstance(context, dict) else None
    device = args.get("device_id")
    chat = args.get("chat")
    text = args.get("text")
    if not isinstance(baseline, list) or not device or not chat or text is None:
        return PostconditionResult(False, {"observed": False}, "pre_send_baseline_or_target_missing")
    observation = delivery_verifier.verify(device, chat, text, frozenset(str(x) for x in baseline))
    required = ("observed", "conversation_matches", "outgoing", "content_matches", "newly_observed")
    evidence = {key: observation.get(key) is True for key in required}
    message_id = observation.get("message_id")
    if isinstance(message_id, (str, int)) and str(message_id):
        evidence["message_id"] = str(message_id)[:160]
    ok = all(evidence.get(key) is True for key in required)
    return PostconditionResult(
        ok,
        evidence,
        "new outgoing message observed in requested chat" if ok else "whatsapp_delivery_postcondition_not_observed",
    )


class AndroidWhatsAppUIObserver:
    """Read only the currently visible WhatsApp chat through authorized ADB UI.

    It deliberately fails closed when the foreground app, chat title, or
    explicit outgoing accessibility label cannot be identified. Android's
    accessibility tree does not expose stable message IDs, so IDs are local
    fingerprints of visible message semantics, not provider IDs. Identical
    repeated bodies can conservatively fail verification rather than risk a
    false delivery claim.
    """

    PACKAGE = "com.whatsapp"
    _CHAT_TITLE_IDS = {
        "conversation_contact_name",
        "conversation_contact_name_title",
        "toolbar_title",
    }

    def __init__(self, controller):
        self.controller = controller

    @staticmethod
    def _normalized_text(value):
        return " ".join(str(value or "").split())

    @staticmethod
    def _outgoing_body(element):
        description = AndroidWhatsAppUIObserver._normalized_text(element.content_desc)
        text = AndroidWhatsAppUIObserver._normalized_text(element.text)
        # Only explicit sender labels count. Screen position alone is not enough
        # to infer who sent a message.
        for prefix in ("You: ", "You sent: ", "You sent "):
            if description.startswith(prefix):
                body = description[len(prefix):]
                # Some WhatsApp versions append timestamp/delivery metadata.
                # Prefer an exact visible text node when one is available.
                if text and text in body:
                    return text
                return body
        return None

    def read_visible_chat(self, device, chat):
        state = self.controller.observe(str(device))
        if str(state.package).casefold() != self.PACKAGE:
            raise WhatsAppAccessError("WhatsApp is not the foreground app")

        expected = self._normalized_text(chat).casefold()
        title_nodes = [
            element for element in state.elements
            if element.resource_id.rsplit("/", 1)[-1].casefold() in self._CHAT_TITLE_IDS
        ]
        titles = [self._normalized_text(node.text or node.content_desc) for node in title_nodes]
        actual = next((title for title in titles if title.casefold() == expected), "")
        if not actual:
            raise WhatsAppAccessError("the requested chat is not identified in the visible WhatsApp UI")

        messages = []
        for element in state.elements:
            body = self._outgoing_body(element)
            if not body:
                continue
            semantic = "\0".join((
                body,
                element.resource_id,
                element.class_name,
            ))
            message_id = hashlib.sha256(semantic.encode("utf-8")).hexdigest()[:24]
            messages.append({"id": message_id, "direction": "outgoing", "text": body})
        return {"chat": actual, "messages": messages}


class VerifiedWhatsAppComposer:
    """Prepare a reply only in the observed chat's unique focused composer.

    It checks the requested chat before typing, verifies the focused Android
    edit field belongs to WhatsApp, independently reads back the exact append
    in the same screen/field, and rechecks the requested chat before allowing
    the caller to issue the send key.
    """

    def __init__(self, controller, screen_observer, chat_observer):
        self.controller = controller
        self.screen_observer = screen_observer
        self.chat_observer = chat_observer

    @staticmethod
    def _matches_chat(observation, chat):
        if not isinstance(observation, dict):
            return False
        actual = " ".join(str(observation.get("chat", "")).split()).casefold()
        expected = " ".join(str(chat or "").split()).casefold()
        return bool(expected and actual == expected and isinstance(observation.get("messages"), list))

    def prepare(self, device, chat, text):
        device = str(device or "").strip()
        text = str(text or "")
        if not device or not str(chat or "").strip() or not text:
            return {"ok": False, "verified": False, "verification_reason": "message_target_or_text_missing"}
        try:
            before = self.chat_observer.read_visible_chat(device, chat)
        except Exception as exc:
            return {
                "ok": False, "verified": False,
                "verification_reason": f"requested_chat_observation_failed:{type(exc).__name__}",
            }
        if not self._matches_chat(before, chat):
            return {"ok": False, "verified": False, "verification_reason": "requested_chat_not_confirmed_before_composition"}
        try:
            current_screen = self.screen_observer.observe(device)
        except Exception as exc:
            return {
                "ok": False, "verified": False,
                "verification_reason": f"focused_composer_observation_failed:{type(exc).__name__}",
            }
        if str(getattr(current_screen, "package", "")).casefold() != AndroidWhatsAppUIObserver.PACKAGE:
            return {"ok": False, "verified": False, "verification_reason": "focused_composer_not_in_whatsapp"}
        try:
            baseline = capture_android_text_baseline(self.screen_observer, device)
        except Exception as exc:
            return {
                "ok": False, "verified": False,
                "verification_reason": f"focused_composer_observation_failed:{type(exc).__name__}",
            }
        if str(baseline.get("package", "")).casefold() != AndroidWhatsAppUIObserver.PACKAGE:
            return {"ok": False, "verified": False, "verification_reason": "focused_composer_not_in_whatsapp"}
        try:
            typed = type_android_text_with_baseline(
                self.controller, self.screen_observer, device, text, baseline=baseline,
            )
        except Exception as exc:
            return {
                "ok": False, "verified": False, "draft_may_remain": True,
                "verification_reason": f"composer_input_failed:{type(exc).__name__}",
            }
        if not isinstance(typed, dict) or typed.get("ok") is not True:
            return {
                "ok": False, "verified": False, "draft_may_remain": True,
                "verification_reason": "composer_input_command_failed",
            }
        text_check = verify_android_text_postcondition(
            self.screen_observer, {"serial": device, "text": text}, typed,
        )
        if not text_check.ok:
            return {
                "ok": False, "verified": False, "draft_may_remain": True,
                "verification_reason": "composer_text_readback_failed",
                "text_postcondition": text_check.evidence,
            }
        try:
            after = self.chat_observer.read_visible_chat(device, chat)
        except Exception as exc:
            return {
                "ok": False, "verified": False, "draft_may_remain": True,
                "verification_reason": f"requested_chat_recheck_failed:{type(exc).__name__}",
            }
        if not self._matches_chat(after, chat):
            return {
                "ok": False, "verified": False, "draft_may_remain": True,
                "verification_reason": "requested_chat_changed_after_composition",
            }
        return {
            "ok": True,
            "verified": True,
            "evidence": {
                "observed": True,
                "requested_chat_confirmed_before_and_after": True,
                "focused_composer_in_whatsapp": True,
                "composer_text_readback": text_check.evidence,
            },
        }
