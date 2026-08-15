from src.ingest.base import Requirements
from src.match.fit import analyze_fit


def test_strong_match_recommends_apply():
    reqs = Requirements(
        must_have_skills=["Python", "AWS"],
        nice_to_have_skills=["React"],
    )
    fit = analyze_fit(reqs, ["python", "aws", "react"])
    assert fit.fit_score == 1.0
    assert fit.recommendation == "apply"
    assert fit.gaps == []
    assert fit.estimated is True


def test_missing_hard_requirement_caps_and_skips():
    reqs = Requirements(
        must_have_skills=["Python", "AWS"],
        hard_requirements=["work_authorization"],
    )
    fit = analyze_fit(reqs, ["python", "aws"])
    assert fit.fit_score <= 0.35
    assert fit.recommendation == "skip"
    assert "work_authorization" in fit.gaps


def test_partial_coverage_is_stretch_or_skip():
    reqs = Requirements(must_have_skills=["Python", "Go", "Kafka", "Spark"])
    fit = analyze_fit(reqs, ["python"])
    assert 0.0 < fit.fit_score < 0.7
    assert set(fit.gaps) == {"go", "kafka", "spark"}
    assert fit.recommendation in {"stretch", "skip"}
