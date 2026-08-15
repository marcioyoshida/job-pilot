"""Lever job-board source (ToS-clean public postings API).

Public endpoint shape (verify live before trusting):
    https://api.lever.co/v0/postings/{company}?mode=json
"""
from __future__ import annotations

from typing import Iterable

from src.ingest.base import JobSource, Posting, SearchProfile


class LeverSource(JobSource):
    def __init__(self, companies: list[str]) -> None:
        self.name = "lever"
        self.companies = companies

    def fetch(self, profile: SearchProfile) -> Iterable[Posting]:  # pragma: no cover
        raise NotImplementedError("Phase P0: implement Lever postings fetch.")
