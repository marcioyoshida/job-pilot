import json

import pytest

from src.apply.records import ApplicationRecord, ApplicationStore
from src.submit.submitter import (
    ApprovalRequired,
    default_mailer_factory,
    submit_record,
)


def _materials_file(tmp_path, method_ok=True):
    payload = {
        "status": "draft_pending_approval",
        "posting": {"company": "Acme", "title": "Engineer"},
        "materials": {
            "resume_highlights": ["Built X on AWS."],
            "bullet_provenance": {"Built X on AWS.": "b1"},
            "cover_letter": "Dear Acme Hiring Team, ...",
            "screening_answers": {},
            "unanswered_questions": ["Expected salary?"],
        },
    }
    p = tmp_path / "m.json"
    p.write_text(json.dumps(payload))
    return str(p)


def _record(tmp_path, method="greenhouse:https://boards.greenhouse.io/acme/jobs/1"):
    return ApplicationRecord(
        key="k1", company="Acme", title="Engineer", source="greenhouse",
        source_url="https://boards.greenhouse.io/acme/jobs/1",
        application_method=method, materials_path=_materials_file(tmp_path),
    )


def test_store_roundtrip_and_no_progress_clobber(tmp_path):
    store = ApplicationStore(tmp_path / "recs.json")
    r = _record(tmp_path)
    store.upsert(r)
    store.approve("k1")
    assert store.get("k1").status == "approved"
    # re-drafting the same key must not downgrade an approved record
    r2 = _record(tmp_path)
    store.upsert(r2)
    assert store.get("k1").status == "approved"
    # reload from disk
    assert ApplicationStore(tmp_path / "recs.json").get("k1").status == "approved"


def test_submit_requires_approval(tmp_path):
    store = ApplicationStore(tmp_path / "recs.json")
    store.upsert(_record(tmp_path))  # status drafted
    with pytest.raises(ApprovalRequired):
        submit_record(store.get("k1"), store, package_dir=tmp_path / "pkg")


def test_one_click_package_written_for_ats_url(tmp_path):
    store = ApplicationStore(tmp_path / "recs.json")
    store.upsert(_record(tmp_path))
    store.approve("k1")
    receipt = submit_record(store.get("k1"), store, package_dir=tmp_path / "pkg")
    assert receipt.method == "one_click_package"
    # package file exists and references the apply URL
    path = receipt.confirmation.split(" | ")[0]
    body = open(path, encoding="utf-8").read()
    assert "Built X on AWS." in body
    assert "boards.greenhouse.io/acme/jobs/1" in body
    assert "Expected salary?" in body      # deferred question surfaced to the human
    assert store.get("k1").status == "submitted"


def test_idempotent_unless_forced(tmp_path):
    store = ApplicationStore(tmp_path / "recs.json")
    store.upsert(_record(tmp_path))
    store.approve("k1")
    submit_record(store.get("k1"), store, package_dir=tmp_path / "pkg")
    with pytest.raises(RuntimeError):
        submit_record(store.get("k1"), store, package_dir=tmp_path / "pkg")
    # force allows a resend
    r = submit_record(store.get("k1"), store, package_dir=tmp_path / "pkg", force=True)
    assert r.method == "one_click_package"


def test_email_method_uses_injected_mailer(tmp_path):
    store = ApplicationStore(tmp_path / "recs.json")
    store.upsert(_record(tmp_path, method="email:jobs@acme.com"))
    store.approve("k1")
    sent = {}

    def mailer(msg):
        sent["to"] = msg["To"]
        sent["subject"] = msg["Subject"]
        return "sent-123"

    receipt = submit_record(store.get("k1"), store, package_dir=tmp_path / "pkg", mailer=mailer)
    assert receipt.method == "email"
    assert receipt.confirmation == "sent-123"
    assert sent["to"] == "jobs@acme.com"


def test_email_default_mailer_writes_draft_and_sends_nothing(tmp_path):
    store = ApplicationStore(tmp_path / "recs.json")
    store.upsert(_record(tmp_path, method="email:jobs@acme.com"))
    store.approve("k1")
    receipt = submit_record(store.get("k1"), store, package_dir=tmp_path / "pkg")
    assert receipt.method == "email_draft"
    assert receipt.confirmation.startswith("draft:")
