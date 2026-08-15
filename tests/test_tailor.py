import pytest

from src.ingest.base import FitAnalysis, MaterialsVersion, Posting, Requirements
from src.profile.candidate import CandidateProfile, MasterBullet
from src.tailor.build import build_materials, write_materials
from src.tailor.cover_letter import (
    draft_screening_answers,
    is_deferred_question,
    write_cover_letter,
)
from src.tailor.resume import rank_bullets, tailor_highlights, verify_provenance


def _candidate():
    return CandidateProfile(
        name="Alex Doe",
        headline="Staff Backend Engineer",
        skills=["Python", "AWS"],
        master_bullets=[
            MasterBullet("b1", "Built serverless pipelines on AWS Lambda.", ["aws", "lambda"]),
            MasterBullet("b2", "Tuned PostgreSQL for a fintech ledger.", ["postgres", "sql"]),
            MasterBullet("b3", "Wrote Python services with FastAPI.", ["python", "fastapi"]),
        ],
    )


def _reqs():
    return Requirements(must_have_skills=["python", "aws", "lambda"],
                        nice_to_have_skills=["react"])


def _fit(gaps=None):
    return FitAnalysis(fit_score=0.8, matched_skills=["python", "aws", "lambda"],
                       gaps=gaps or ["react"], recommendation="apply")


def test_rank_prefers_relevant_bullets():
    ranked = rank_bullets(_candidate(), _reqs())
    ids = [bid for bid, _t, _s in ranked]
    # b1 (aws+lambda) and b3 (python) are relevant; b2 (postgres) is not
    assert ids[0] in {"b1", "b3"}
    assert "b2" not in ids


def test_highlights_have_valid_provenance():
    cand = _candidate()
    highlights, prov = tailor_highlights(cand, _reqs(), _fit())
    assert highlights
    real_texts = {b.text for b in cand.master_bullets}
    for h in highlights:
        assert h in real_texts               # verbatim from a real bullet
        assert prov[h] in {b.id for b in cand.master_bullets}


def test_verify_provenance_rejects_fabrication():
    cand = _candidate()
    bad = MaterialsVersion(
        resume_highlights=["Led a 200-person org (fabricated)."],
        bullet_provenance={"Led a 200-person org (fabricated).": "b1"},
    )
    assert verify_provenance(bad, cand) is False


def test_build_materials_ok_and_cover_letter_is_honest():
    cand = _candidate()
    m = build_materials(cand, Posting(source="greenhouse", source_url="u",
                                      company="Acme", title="Senior Backend Engineer"),
                        _reqs(), _fit(gaps=["react", "work_authorization"]))
    assert verify_provenance(m, cand)
    assert "Acme" in m.cover_letter and "Senior Backend Engineer" in m.cover_letter
    # honest about a soft gap, but never surfaces work authorization as a talking point
    assert "react" in m.cover_letter.lower()
    assert "authoriz" not in m.cover_letter.lower()
    assert "Alex Doe" in m.cover_letter


def test_screening_defers_sensitive_questions():
    assert is_deferred_question("What is your expected salary?")
    assert is_deferred_question("Do you require visa sponsorship?")
    assert not is_deferred_question("Describe a system you designed.")
    reqs = Requirements(screening_questions=["Expected salary?", "Why this role?"])
    answered, unanswered = draft_screening_answers(_candidate(), reqs)
    assert answered == {}
    assert set(unanswered) == {"Expected salary?", "Why this role?"}


def test_write_materials_marks_draft(tmp_path):
    cand = _candidate()
    posting = Posting(source="lever", source_url="u", company="Acme", title="Eng")
    m = build_materials(cand, posting, _reqs(), _fit())
    path = write_materials(m, posting, tmp_path)
    assert path.exists()
    import json
    payload = json.loads(path.read_text())
    assert payload["status"] == "draft_pending_approval"
