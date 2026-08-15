"""Stage 4 — tailored resume highlights (FR-4.1/4.2, CON-4 no fabrication).

Selects and orders bullets from the candidate's MASTER resume to foreground what
a posting values. Every emitted highlight is drawn verbatim from a real master
bullet and mapped back to its id via `bullet_provenance` — nothing is invented.
An optional LLM rephrase step (guarded seam) may mirror JD language, but must
preserve the factual claim of the source bullet.
"""
from __future__ import annotations

from src.ingest.base import FitAnalysis, MaterialsVersion, Requirements
from src.match.taxonomy import normalize_skills
from src.profile.candidate import CandidateProfile

_MUST_W = 2.0
_NICE_W = 1.0
_TEXT_W = 0.5   # weak signal: skill name appears in the bullet text


def _bullet_score(bullet_skills: set[str], text_low: str,
                  must: set[str], nice: set[str]) -> float:
    score = _MUST_W * len(bullet_skills & must) + _NICE_W * len(bullet_skills & nice)
    for s in must | nice:
        if s not in bullet_skills and s in text_low:
            score += _TEXT_W
    return score


def rank_bullets(candidate: CandidateProfile, reqs: Requirements) -> list[tuple[str, str, float]]:
    """Return (bullet_id, text, score) for relevant bullets, best first.

    Bullets with zero relevance are dropped (we never pad with irrelevant
    experience). Stable order preserved for ties.
    """
    must = set(normalize_skills(reqs.must_have_skills))
    nice = set(normalize_skills(reqs.nice_to_have_skills))
    scored: list[tuple[str, str, float]] = []
    for b in candidate.master_bullets:
        bskills = set(normalize_skills(b.skills))
        score = _bullet_score(bskills, b.text.lower(), must, nice)
        if score > 0:
            scored.append((b.id, b.text, score))
    scored.sort(key=lambda t: t[2], reverse=True)
    return scored


def tailor_highlights(
    candidate: CandidateProfile,
    reqs: Requirements,
    fit: FitAnalysis,
    *,
    limit: int = 5,
) -> tuple[list[str], dict[str, str]]:
    """Return (highlights, provenance). Each highlight maps to a real bullet id."""
    ranked = rank_bullets(candidate, reqs)[:limit]
    highlights = [text for _id, text, _s in ranked]
    provenance = {text: _id for _id, text, _s in ranked}
    return highlights, provenance


def verify_provenance(materials: MaterialsVersion, candidate: CandidateProfile) -> bool:
    """Guard (CON-4): every highlight must trace to a real master bullet.

    Checks that each provenance id exists and that the highlight text matches
    that bullet verbatim (the offline path emits bullets unchanged).
    """
    by_id = {b.id: b.text for b in candidate.master_bullets}
    for highlight in materials.resume_highlights:
        bid = materials.bullet_provenance.get(highlight)
        if bid is None or bid not in by_id or by_id[bid] != highlight:
            return False
    return True
