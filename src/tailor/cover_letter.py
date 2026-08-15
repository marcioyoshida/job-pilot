"""Stage 4 — cover letter + screening answers (FR-4.3/4.4).

Company/role-specific, 2-3 concrete matched strengths, honest about gaps.
Screening answers only where truthfully derivable from the profile; everything
else is flagged for the user (salary, visa, demographic).
"""
from __future__ import annotations

from typing import Any

from src.ingest.base import FitAnalysis, MaterialsVersion, Requirements


def write_cover_letter(
    master_resume: dict[str, Any],
    reqs: Requirements,
    fit: FitAnalysis,
    *,
    tone: str = "professional",
    max_words: int = 300,
) -> str:  # pragma: no cover
    raise NotImplementedError("Phase P3: implement cover-letter synthesis (Bedrock).")


def draft_screening_answers(
    master_resume: dict[str, Any],
    reqs: Requirements,
) -> tuple[dict[str, str], list[str]]:  # pragma: no cover
    """Return (answered, unanswered). Defer salary/visa/demographic to the user."""
    raise NotImplementedError("Phase P3: implement truthful screening-answer drafting.")
