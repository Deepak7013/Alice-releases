import tempfile
import pytest
from alice.email import EmailStore, EmailService, ApprovalRequired, EmailStatus

def test_draft_persists_and_normalizes_addresses():
    with tempfile.TemporaryDirectory() as d:
        s=EmailStore(d)
        draft=s.create_draft([" Test@Example.com ","test@example.com"],"Hello","Body",cc=["CC@example.com"])
        assert draft.to == ["test@example.com"]
        assert draft.cc == ["cc@example.com"]
        s2=EmailStore(d)
        assert s2.get_draft(draft.draft_id).subject == "Hello"

def test_validation_blocks_bad_email_and_empty_content():
    with tempfile.TemporaryDirectory() as d:
        s=EmailStore(d)
        with pytest.raises(ValueError): s.create_draft(["not-an-email"],"x","y")
        with pytest.raises(ValueError): s.create_draft(["a@example.com"],"","y")
        with pytest.raises(ValueError): s.create_draft(["a@example.com"],"x","")

def test_send_requires_explicit_approval_and_does_not_fake_delivery():
    with tempfile.TemporaryDirectory() as d:
        s=EmailStore(d); draft=s.create_draft(["a@example.com"],"Hi","Body")
        with pytest.raises(ApprovalRequired): EmailService(s).send(draft.draft_id)
        msg=EmailService(s, approval=lambda _: True).send(draft.draft_id)
        assert msg.status == EmailStatus.QUEUED
        assert msg.sent_at is None

def test_provider_delivery_marks_sent_only_after_success():
    class Provider:
        def send(self, draft): return True
    with tempfile.TemporaryDirectory() as d:
        s=EmailStore(d); draft=s.create_draft(["a@example.com"],"Hi","Body")
        msg=EmailService(s, approval=lambda _: True, provider=Provider()).send(draft.draft_id)
        assert msg.status == EmailStatus.SENT and msg.sent_at is not None

def test_cancel_draft_removes_it():
    with tempfile.TemporaryDirectory() as d:
        s=EmailStore(d); draft=s.create_draft(["a@example.com"],"Hi","Body")
        s.cancel_draft(draft.draft_id)
        with pytest.raises(KeyError): s.get_draft(draft.draft_id)
