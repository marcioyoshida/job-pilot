"""Stage 4 — tailored resume highlights (FR-4.1/4.2, CON-4 no fabrication).

Selects/re-orders/rephrases bullets from the candidate's MASTER resume to
foreground what a posting values. Every produced highlight MUST map back to a
real master item via `bullet_provenance` — nothing is invented.
"""
from __future__ import annotations

from typing import Any

from src.ingest.base import FitAnalysis, MaterialsVersion, Requirements


def tailor_highlights(
    master_resume: dict[str, Any],
    reqs: Requirements,
    fit: FitAnalysis,
) -> MaterialsVersion:  # pragma: no cover
    # Phase P3: rank master bullets by relevance to reqs.must_have/nice_to_have +
    # fit.matched_skills; optionally rephrase to mirror JD language (Bedrock).
    # For each emitted highlight, record bullet_provenance[highlight] = master
    # item id. Reject any candidate highlight that can't be traced to a master
    # item (CON-4). Cover letter is produced by cover_letter.py.
    raise NotImplementedError("Phase P3: implement provenance-checked tailoring.")
