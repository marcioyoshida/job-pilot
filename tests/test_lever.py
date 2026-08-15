import time

from src.ingest.base import Posting, SearchProfile
from src.ingest.lever import LeverSource, _epoch_ms_to_iso, _posting_from

NOW_MS = int(time.time() * 1000)
OLD_MS = NOW_MS - 90 * 24 * 3600 * 1000


def _array():
    # Lever returns a bare JSON array; createdAt is epoch MILLISECONDS.
    return [
        {
            "id": "a1",
            "text": "Senior Backend Engineer",
            "hostedUrl": "https://jobs.lever.co/acme/a1",
            "categories": {"location": "Remote - Brazil", "team": "Eng"},
            "descriptionPlain": "Build Python services on AWS",
            "workplaceType": "remote",
            "createdAt": NOW_MS,
        },
        {
            "id": "a2",
            "text": "Account Executive",
            "hostedUrl": "https://jobs.lever.co/acme/a2",
            "categories": {"location": "New York"},
            "descriptionPlain": "Close deals",
            "createdAt": NOW_MS,
        },
        {
            "id": "a3",
            "text": "Staff Python Engineer",
            "hostedUrl": "https://jobs.lever.co/acme/a3",
            "categories": {"location": "Remote"},
            "descriptionPlain": "Python and AWS",
            "createdAt": OLD_MS,   # filtered by recency
        },
    ]


def test_epoch_ms_conversion_roundtrips():
    iso = _epoch_ms_to_iso(1_600_000_000_000)
    assert iso is not None and iso.startswith("2020-09-13")
    assert _epoch_ms_to_iso(None) is None
    assert _epoch_ms_to_iso("bad") is None


def test_posting_falls_back_to_html_description():
    item = {"text": "Eng", "hostedUrl": "u", "description": "&lt;p&gt;Go &amp; Rust&lt;/p&gt;"}
    p = _posting_from("acme", item)
    assert p.description == "Go & Rust"


def test_fetch_maps_and_filters():
    src = LeverSource(["acme"], http_get=lambda url: _array())
    profile = SearchProfile(
        titles=["engineer"], keywords=["python"], locations=["Brazil"],
        remote_ok=True, recency_days=30,
    )
    got = list(src.fetch(profile))
    assert len(got) == 1
    p = got[0]
    assert isinstance(p, Posting)
    assert p.source == "lever"
    assert p.company == "acme"
    assert p.title == "Senior Backend Engineer"
    assert p.remote_policy == "remote"
    assert p.source_url.endswith("/a1")
    assert "AWS" in p.description


def test_tolerates_wrapped_data_and_bad_company():
    wrapped = LeverSource(["acme"], http_get=lambda url: {"data": _array()})
    assert len(list(wrapped.fetch(SearchProfile(recency_days=0)))) == 3

    def boom(url):
        raise RuntimeError("boom")

    assert list(LeverSource(["x"], http_get=boom).fetch(SearchProfile(recency_days=0))) == []
