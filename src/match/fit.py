"""Fit scoring (FR-3.2/3.4). Estimated score, honest gaps.

Weights must-have coverage heavily; a missing HARD requirement caps the score.
Pure function so it's trivially testable and Lambda-portable.
"""
from __future__ import annotations

from src.ingest.base import FitAnalysis, Requirements
from src.match.taxonomy import normalize_skills

_MUST_WEIGHT = 0.75
_NICE_WEIGHT = 0.25
_HARD_MISS_CAP = 0.35   # a missing hard requirement caps fit_score here


def analyze_fit(reqs: Requirements, candidate_skills: list[str]) -> FitAnalysis:
    cand = set(normalize_skills(candidate_skills))
    must = normalize_skills(reqs.must_have_skills)
    nice = normalize_skills(reqs.nice_to_have_skills)
    hard = set(normalize_skills(reqs.hard_requirements))

    must_hit = [s for s in must if s in cand]
    nice_hit = [s for s in nice if s in cand]
    matched = sorted(set(must_hit) | set(nice_hit))

    must_cov = (len(must_hit) / len(must)) if must else 1.0
    nice_cov = (len(nice_hit) / len(nice)) if nice else 1.0
    score = _MUST_WEIGHT * must_cov + _NICE_WEIGHT * nice_cov

    hard_missing = sorted(hard - cand)
    # gaps = anything the posting wants (skills + hard requirements) not covered
    gaps = sorted(((set(must) | set(nice) | hard) - cand))
    if hard_missing:
        score = min(score, _HARD_MISS_CAP)

    if hard_missing:
        rec = "skip"
    elif score >= 0.7:
        rec = "apply"
    elif score >= 0.45:
        rec = "stretch"
    else:
        rec = "skip"

    note = f"must {len(must_hit)}/{len(must)}, nice {len(nice_hit)}/{len(nice)}"
    if hard_missing:
        note += f"; missing hard: {', '.join(hard_missing)}"

    return FitAnalysis(
        fit_score=round(score, 3),
        matched_skills=matched,
        gaps=gaps,
        recommendation=rec,
        estimated=True,
        notes=note,
    )
