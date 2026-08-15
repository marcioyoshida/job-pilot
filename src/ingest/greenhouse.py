"""Greenhouse job-board source (Phase P0) — ToS-clean public boards API.

Endpoint (public, no auth):
    https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true

Response shape (per Greenhouse's Job Board API docs — this is a stable,
long-published schema):
    {"jobs": [ {"id", "title", "updated_at", "absolute_url",
                "location": {"name"}, "content" (HTML-escaped, when
                ?content=true), "departments":[...], "offices":[...],
                "metadata":[...]} , ... ],
     "meta": {"total"}}

NOTE (verification): this session's egress policy blocks
boards-api.greenhouse.io, so the mapping below was written against the
documented schema, not a live call. Run `python -m src.ingest.greenhouse <board>`
on an unrestricted network once to confirm field names before trusting it in
production (house rule: verify schemas live). The mapping is defensive (.get
everywhere) so an unexpected field won't crash the pipeline.
"""
from __future__ import annotations

import html
import json
import re
import urllib.request
from datetime import datetime, timedelta, timezone
from typing import Callable, Iterable, Optional

from src.ingest.base import JobSource, Posting, SearchProfile

_API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"
_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")

# An injected HTTP getter: url -> parsed JSON dict. Defaults to urllib.
HttpGet = Callable[[str], dict]


def _default_http_get(url: str, timeout: float = 20.0) -> dict:  # pragma: no cover - network
    req = urllib.request.Request(url, headers={"User-Agent": "job-pilot/0.1"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def html_to_text(raw: str) -> str:
    """Greenhouse `content` is HTML-escaped HTML; reduce it to readable text."""
    if not raw:
        return ""
    text = html.unescape(raw)          # &lt;p&gt; -> <p>
    text = _TAG.sub(" ", text)          # strip tags
    text = html.unescape(text)          # decode entities left in text (&amp; etc.)
    return _WS.sub(" ", text).strip()


def _job_to_posting(board: str, job: dict) -> Posting:
    return Posting(
        source="greenhouse",
        source_url=job.get("absolute_url", ""),
        company=board,                                  # board token == company id
        title=job.get("title", ""),
        location=(job.get("location") or {}).get("name", "") or "",
        description=html_to_text(job.get("content", "")),
        posted_at=job.get("updated_at"),
        raw=job,
    )


def _within_recency(posted_at: Optional[str], recency_days: int) -> bool:
    if not posted_at or recency_days <= 0:
        return True
    try:
        dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return True  # unparseable -> don't drop
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= datetime.now(timezone.utc) - timedelta(days=recency_days)


def matches(posting: Posting, profile: SearchProfile) -> bool:
    """Pure filter against the SearchProfile (FR-1.2). Case-insensitive."""
    title = posting.title.lower()
    haystack = f"{posting.title}\n{posting.description}".lower()
    loc = f"{posting.location} {posting.remote_policy}".lower()

    if profile.titles and not any(t.lower() in title for t in profile.titles):
        return False
    if profile.keywords and not any(k.lower() in haystack for k in profile.keywords):
        return False
    if profile.exclude_terms and any(x.lower() in haystack for x in profile.exclude_terms):
        return False
    if profile.exclude_companies and any(
        c.lower() in posting.company.lower() for c in profile.exclude_companies
    ):
        return False
    if profile.locations:
        loc_ok = any(l.lower() in loc for l in profile.locations)
        if profile.remote_ok and "remote" in loc:
            loc_ok = True
        if not loc_ok:
            return False
    if not _within_recency(posting.posted_at, profile.recency_days):
        return False
    return True


class GreenhouseSource(JobSource):
    def __init__(self, boards: list[str], http_get: HttpGet | None = None) -> None:
        self.name = "greenhouse"
        self.boards = boards
        self._http_get = http_get or _default_http_get

    def fetch(self, profile: SearchProfile) -> Iterable[Posting]:
        for board in self.boards:
            try:
                payload = self._http_get(_API.format(board=board))
            except Exception as exc:  # noqa: BLE001 - one bad board shouldn't sink the run
                print(f"greenhouse: board '{board}' fetch failed: {exc}")
                continue
            for job in payload.get("jobs", []):
                posting = _job_to_posting(board, job)
                if matches(posting, profile):
                    yield posting


if __name__ == "__main__":  # pragma: no cover - manual live verification helper
    import sys
    from dataclasses import asdict

    board = sys.argv[1] if len(sys.argv) > 1 else "gitlab"
    src = GreenhouseSource([board])
    prof = SearchProfile()  # empty profile = no filtering
    got = list(src.fetch(prof))
    print(f"{len(got)} postings from '{board}'")
    if got:
        print(json.dumps(asdict(got[0]) | {"raw": "<omitted>"}, default=str, indent=2))
