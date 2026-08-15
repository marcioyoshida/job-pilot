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

from dataclasses import asdict
from typing import Iterable

from src.ingest.base import JobSource, Posting, SearchProfile
from src.ingest.filters import html_to_text, matches  # re-exported for callers/tests
from src.ingest.http import HttpGet, http_get_json

_API = "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true"


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


class GreenhouseSource(JobSource):
    def __init__(self, boards: list[str], http_get: HttpGet | None = None) -> None:
        self.name = "greenhouse"
        self.boards = boards
        self._http_get = http_get or http_get_json

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
    import json
    import sys

    board = sys.argv[1] if len(sys.argv) > 1 else "gitlab"
    got = list(GreenhouseSource([board]).fetch(SearchProfile()))  # empty = no filter
    print(f"{len(got)} postings from '{board}'")
    if got:
        print(json.dumps(asdict(got[0]) | {"raw": "<omitted>"}, default=str, indent=2))
