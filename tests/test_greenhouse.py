from datetime import datetime, timedelta, timezone

from src.ingest.base import Posting, SearchProfile
from src.ingest.greenhouse import (
    GreenhouseSource,
    html_to_text,
    matches,
)

RECENT = datetime.now(timezone.utc).isoformat()
OLD = (datetime.now(timezone.utc) - timedelta(days=90)).isoformat()


def _payload():
    # Mirrors the documented Greenhouse Job Board API shape.
    return {
        "jobs": [
            {
                "id": 1,
                "title": "Senior Backend Engineer",
                "updated_at": RECENT,
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/1",
                "location": {"name": "Remote - Brazil"},
                "content": "&lt;p&gt;Build &lt;b&gt;Python&lt;/b&gt; services on AWS&lt;/p&gt;",
            },
            {
                "id": 2,
                "title": "Sales Manager",
                "updated_at": RECENT,
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/2",
                "location": {"name": "New York"},
                "content": "&lt;p&gt;Lead the sales team&lt;/p&gt;",
            },
            {
                "id": 3,
                "title": "Staff Python Engineer",
                "updated_at": OLD,   # too old -> filtered by recency
                "absolute_url": "https://boards.greenhouse.io/acme/jobs/3",
                "location": {"name": "Remote"},
                "content": "&lt;p&gt;Python and AWS&lt;/p&gt;",
            },
        ],
        "meta": {"total": 3},
    }


def test_html_to_text_unescapes_and_strips():
    out = html_to_text("&lt;p&gt;Build &lt;b&gt;Python&lt;/b&gt; on AWS&lt;/p&gt;")
    assert out == "Build Python on AWS"


def test_fetch_maps_and_filters():
    src = GreenhouseSource(["acme"], http_get=lambda url: _payload())
    profile = SearchProfile(
        titles=["engineer"],
        keywords=["python"],
        locations=["Brazil"],
        remote_ok=True,
        recency_days=30,
    )
    got = list(src.fetch(profile))
    # job 1 matches; job 2 wrong title/keyword; job 3 filtered by recency
    assert len(got) == 1
    p = got[0]
    assert isinstance(p, Posting)
    assert p.company == "acme"
    assert p.source == "greenhouse"
    assert p.title == "Senior Backend Engineer"
    assert p.source_url.endswith("/jobs/1")
    assert "Python" in p.description and "AWS" in p.description
    assert p.location == "Remote - Brazil"


def test_exclude_terms_and_companies():
    payload = _payload()
    src = GreenhouseSource(["acme"], http_get=lambda url: payload)

    excl_term = SearchProfile(keywords=["python"], recency_days=0, exclude_terms=["aws"])
    assert list(src.fetch(excl_term)) == []

    excl_co = SearchProfile(keywords=["python"], recency_days=0, exclude_companies=["acme"])
    assert list(src.fetch(excl_co)) == []


def test_empty_profile_matches_all_recent():
    payload = _payload()
    src = GreenhouseSource(["acme"], http_get=lambda url: payload)
    # recency_days=0 disables the recency filter -> all 3 pass an empty profile
    got = list(src.fetch(SearchProfile(recency_days=0)))
    assert len(got) == 3


def test_bad_board_is_skipped_not_fatal():
    def boom(url):
        raise RuntimeError("boom")

    src = GreenhouseSource(["broken"], http_get=boom)
    assert list(src.fetch(SearchProfile(recency_days=0))) == []


def test_remote_ok_allows_remote_when_location_restricted():
    p = Posting(source="greenhouse", source_url="u", company="acme",
                title="Engineer", location="Remote", description="python")
    prof = SearchProfile(locations=["São Paulo"], remote_ok=True, recency_days=0)
    assert matches(p, prof) is True
    prof_strict = SearchProfile(locations=["São Paulo"], remote_ok=False, recency_days=0)
    assert matches(p, prof_strict) is False
