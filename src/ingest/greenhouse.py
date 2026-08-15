"""Greenhouse job-board source (ToS-clean public boards API).

Phase P0 target: implement this first — structured, stable, no ToS risk.
Public endpoint shape (verify against a live call before trusting — house rule
"no invented schemas"):
    https://boards-api.greenhouse.io/v1/boards/{company}/jobs?content=true
"""
from __future__ import annotations

from typing import Iterable

from src.ingest.base import JobSource, Posting, SearchProfile


class GreenhouseSource(JobSource):
    def __init__(self, boards: list[str]) -> None:
        self.name = "greenhouse"
        self.boards = boards   # company board tokens to poll

    def fetch(self, profile: SearchProfile) -> Iterable[Posting]:  # pragma: no cover
        # Phase P0: GET each board, map jobs -> Posting, filter by profile
        # (titles/keywords/locations/recency/exclude*). Keep source_url = absolute
        # posting URL. Verify the live JSON schema before mapping fields.
        raise NotImplementedError("Phase P0: implement Greenhouse boards fetch.")
