"""Licensed aggregator source — PHASE C.

Replaces per-account LinkedIn (linkedin.py) for the multi-tenant customer
product. Provides LinkedIn/Indeed breadth under the aggregator's license terms
(CON-1/CON-6) without operating any customer's LinkedIn session.

Same JobSource interface — dropping this in for LinkedInSource requires no
change to stages 2-6.
"""
from __future__ import annotations

from typing import Iterable

from src.ingest.base import JobSource, Posting, SearchProfile


class AggregatorSource(JobSource):
    def __init__(self, provider: str) -> None:
        self.name = f"aggregator:{provider}"
        self.provider = provider

    def fetch(self, profile: SearchProfile) -> Iterable[Posting]:  # pragma: no cover
        raise NotImplementedError("Phase C: implement licensed aggregator fetch.")
