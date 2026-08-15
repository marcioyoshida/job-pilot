import json

from src.apply.records import ApplicationRecord, ApplicationStore
from src.monitor.inbox import FileInbox, InboxMessage
from src.monitor.tracker import (
    classify_inbox_message,
    match_to_application,
    monitor_messages,
)


def _store(tmp_path):
    s = ApplicationStore(tmp_path / "recs.json")
    s.upsert(ApplicationRecord(key="k1", company="Acme Pay", title="Senior Backend Engineer",
                               source="greenhouse", source_url="u", status="submitted"))
    s.upsert(ApplicationRecord(key="k2", company="Globex", title="Data Engineer",
                               source="lever", source_url="u2", status="submitted"))
    return s


def test_classifier_buckets():
    assert classify_inbox_message("Your application", "Thank you for applying to Acme.") == "acknowledged"
    assert classify_inbox_message("Next steps", "We'd like to schedule an interview.") == "interview"
    assert classify_inbox_message("Take-home", "Please complete this coding challenge.") == "screening"
    assert classify_inbox_message("Great news", "We are pleased to offer you the role.") == "offer"
    assert classify_inbox_message("Update", "Unfortunately we are not moving forward.") == "rejected"
    assert classify_inbox_message("Newsletter", "Weekly product updates.") is None


def test_rejection_after_interview_reads_as_rejected():
    msg = "Thank you for taking the time to interview. Unfortunately we are not moving forward."
    assert classify_inbox_message("Update", msg) == "rejected"


def test_matcher_requires_company_signal(tmp_path):
    store = _store(tmp_path)
    m = InboxMessage(subject="Acme Pay — interview", body="schedule an interview",
                     from_addr="recruiter@acmepay.com")
    assert match_to_application(m, store.all()).key == "k1"
    # no company signal -> no match
    none = InboxMessage(subject="Hello", body="generic message", from_addr="x@y.com")
    assert match_to_application(none, store.all()) is None


def test_monitor_advances_and_is_forward_only(tmp_path):
    store = _store(tmp_path)
    notified = []
    messages = [
        InboxMessage(subject="Acme Pay application", body="Thank you for applying.",
                     from_addr="no-reply@acmepay.com"),                       # acknowledged
        InboxMessage(subject="Acme Pay next steps", body="Let's schedule an interview.",
                     from_addr="recruiter@acmepay.com"),                      # interview
    ]
    tr = monitor_messages(messages, store, notify=lambda l, s: notified.append((l, s)))
    # ends at the furthest-forward status (interview), not acknowledged
    assert store.get("k1").status == "interview"
    assert ("Acme Pay — Senior Backend Engineer", "interview") in notified
    # history recorded both events in order
    hist = [h["status"] for h in store.get("k1").history]
    assert hist == ["acknowledged", "interview"]

    # a later acknowledged email must NOT regress an interview
    back = [InboxMessage(subject="Acme Pay", body="application received",
                         from_addr="no-reply@acmepay.com")]
    monitor_messages(back, store)
    assert store.get("k1").status == "interview"


def test_file_inbox_roundtrip(tmp_path):
    p = tmp_path / "inbox.json"
    p.write_text(json.dumps([{"subject": "Hi", "snippet": "body text", "from": "a@b.com"}]))
    msgs = list(FileInbox(p).fetch())
    assert msgs[0].subject == "Hi" and msgs[0].body == "body text" and msgs[0].from_addr == "a@b.com"


def test_manual_override_can_regress(tmp_path):
    store = _store(tmp_path)
    store.advance_status("k1", "interview", source="inbox")
    # forward_only=False allows correcting a mistake
    assert store.advance_status("k1", "submitted", source="manual", forward_only=False)
    assert store.get("k1").status == "submitted"
