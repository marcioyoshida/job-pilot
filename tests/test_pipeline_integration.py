"""End-to-end (offline): source -> diff -> extract -> fit, no network."""
from src.diff.engine import new_postings
from src.extract.requirements import extract_requirements
from src.ingest.base import SearchProfile
from src.ingest.greenhouse import GreenhouseSource
from src.match.fit import analyze_fit
from src.profile.candidate import CandidateProfile
from src.state.store import JsonState


def _payload():
    return {
        "jobs": [
            {
                "id": 1, "title": "Senior Python Engineer",
                "updated_at": "2999-01-01T00:00:00Z",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                "location": {"name": "Remote"},
                "content": "Requirements: Python, AWS, Lambda. Nice to have: React.",
            },
            {
                "id": 2, "title": "Rust Systems Engineer",
                "updated_at": "2999-01-01T00:00:00Z",
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/2",
                "location": {"name": "Remote"},
                "content": "Requirements: Rust, Kafka, Kubernetes.",
            },
        ],
        "meta": {"total": 2},
    }


def test_full_chain_ranks_by_fit(tmp_path):
    src = GreenhouseSource(["acme"], http_get=lambda url: _payload())
    profile = SearchProfile(recency_days=0)  # no recency filter
    state = JsonState(tmp_path / "s.json")

    postings = new_postings(list(src.fetch(profile)), state)
    assert len(postings) == 2

    candidate = CandidateProfile(skills=["Python", "AWS", "Lambda"])
    cand_skills = candidate.normalized_skills()

    ranked = sorted(
        ((p, analyze_fit(extract_requirements(p), cand_skills)) for p in postings),
        key=lambda r: r[1].fit_score, reverse=True,
    )

    top, top_fit = ranked[0]
    assert top.title == "Senior Python Engineer"
    assert top_fit.fit_score > ranked[1][1].fit_score
    assert top_fit.recommendation == "apply"
    # the Rust role should surface real gaps the candidate lacks
    assert "rust" in ranked[1][1].gaps
