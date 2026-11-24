import secrets
from typing import Callable, Optional

from .models import ActionRecord, ActionStatus
from .store import ActionStore


class ActionEngine:
    """Tracks consequential actions without claiming success before verification."""

    def __init__(self, store: Optional[ActionStore] = None):
        self.store = store or ActionStore()

    def plan(self, action: str) -> ActionRecord:
        if not action or not action.strip():
            raise ValueError("action is required")
        record = ActionRecord(action_id=secrets.token_hex(12), action=action.strip())
        return self.store.save(record)

    def approve(self, action_id: str) -> ActionRecord:
        record = self._required(action_id)
        if record.status not in {ActionStatus.PLANNED, ActionStatus.FAILED}:
            raise ValueError("action cannot be approved from its current state")
        record.approved = True
        record.status = ActionStatus.APPROVED
        record.error = None
        record.touch()
        return self.store.save(record)

    def execute(self, action_id: str, executor: Callable[[], object]) -> ActionRecord:
        record = self._required(action_id)
        if not record.approved or record.status != ActionStatus.APPROVED:
            raise PermissionError("explicit approval required")
        try:
            result = executor()
            record.result = result
            record.status = ActionStatus.EXECUTED
            record.error = None
        except Exception as exc:
            record.error = str(exc)
            record.status = ActionStatus.FAILED
        record.touch()
        return self.store.save(record)

    def verify(self, action_id: str, verifier: Callable[[object], bool], note: str = "") -> ActionRecord:
        record = self._required(action_id)
        if record.status != ActionStatus.EXECUTED:
            raise ValueError("only executed actions can be verified")
        try:
            passed = bool(verifier(record.result))
        except Exception as exc:
            record.error = str(exc)
            record.status = ActionStatus.FAILED
            record.verification = "verification_error"
        else:
            record.verification = note or ("verified" if passed else "verification_failed")
            record.status = ActionStatus.VERIFIED if passed else ActionStatus.FAILED
            if passed:
                record.error = None
        record.touch()
        return self.store.save(record)

    def rollback(self, action_id: str, rollbacker: Callable[[object], object]) -> ActionRecord:
        record = self._required(action_id)
        if record.status not in {ActionStatus.EXECUTED, ActionStatus.VERIFIED, ActionStatus.FAILED}:
            raise ValueError("action cannot be rolled back from its current state")
        try:
            rollbacker(record.result)
            record.status = ActionStatus.ROLLED_BACK
            record.error = None
        except Exception as exc:
            record.error = str(exc)
            record.status = ActionStatus.FAILED
        record.touch()
        return self.store.save(record)

    def _required(self, action_id: str) -> ActionRecord:
        record = self.store.get(action_id)
        if record is None:
            raise KeyError(action_id)
        return record
