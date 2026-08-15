from src.extract.requirements import HeuristicExtractor, extract_requirements
from src.ingest.base import Posting

JD = (
    "We are looking for a Senior Backend Engineer. "
    "Requirements: 5+ years with Python and AWS (Lambda, DynamoDB). "
    "Bachelor's degree in Computer Science. "
    "Must be authorized to work in the US. "
    "Nice to have: React and Kubernetes experience."
)


def _posting(desc=JD, title="Senior Backend Engineer", **kw):
    return Posting(source="greenhouse", source_url="https://x/jobs/1",
                   company="acme", title=title, description=desc, **kw)


def test_skills_split_into_must_and_nice():
    reqs = extract_requirements(_posting())
    assert "python" in reqs.must_have_skills
    assert "aws" in reqs.must_have_skills
    assert "lambda" in reqs.must_have_skills
    # after the "Nice to have" marker
    assert "react" in reqs.nice_to_have_skills
    assert "kubernetes" in reqs.nice_to_have_skills
    # a skill never appears in both buckets
    assert set(reqs.must_have_skills).isdisjoint(reqs.nice_to_have_skills)


def test_no_fabrication_absent_skills_not_reported():
    reqs = extract_requirements(_posting())
    for absent in ("rust", "spark", "azure", "terraform"):
        assert absent not in reqs.must_have_skills
        assert absent not in reqs.nice_to_have_skills


def test_every_skill_has_evidence():
    reqs = extract_requirements(_posting())
    for s in reqs.must_have_skills + reqs.nice_to_have_skills:
        assert s in reqs.evidence and reqs.evidence[s]


def test_years_education_workauth_seniority():
    reqs = extract_requirements(_posting())
    assert reqs.years_experience == 5
    assert reqs.education and "bachelor" in reqs.education.lower()
    assert reqs.work_authorization is not None
    assert "work_authorization" in reqs.hard_requirements
    assert reqs.seniority == "senior"
    assert reqs.application_method == "greenhouse:https://x/jobs/1"


def test_ambiguous_go_not_matched_from_prose():
    # bare "go" (verb) must not be picked up as the Go language
    reqs = extract_requirements(_posting(desc="You will go above and beyond. Python required."))
    assert "go" not in reqs.must_have_skills
    assert "python" in reqs.must_have_skills


def test_golang_synonym_is_matched():
    reqs = extract_requirements(_posting(desc="Requirements: Golang and Python."))
    assert "go" in reqs.must_have_skills


def test_remote_policy_prefers_posting_value():
    p = _posting(remote_policy="remote", desc="This is an on-site heavy role.")
    reqs = extract_requirements(p)
    assert reqs.remote_policy == "remote"
