"""Stage 4 — cover letter + screening answers (FR-4.3/4.4).

Offline path: a deterministic, honest template — concrete matched strengths from
the fit analysis and the candidate's top bullet, and it does NOT overclaim on
gaps. The LLM path (guarded seam) produces nicer prose from the same facts; it
must not introduce any claim not backed by the candidate profile (CON-4).

Screening answers are only produced where truthfully derivable; salary, visa,
work-authorization and demographic questions are always deferred to the user.
"""
from __future__ import annotations

import re

from src.ingest.base import FitAnalysis, Requirements
from src.profile.candidate import CandidateProfile

# Questions we never auto-answer — legal/comp/personal (FR-4.4).
_DEFER = re.compile(
    r"salary|compensation|expected pay|desired pay|visa|sponsor|authoriz|"
    r"citizen|work permit|gender|race|ethnic|disab|veteran|age\b|demographic",
    re.I,
)


def _strengths(fit: FitAnalysis, reqs: Requirements, k: int = 3) -> list[str]:
    # Prefer skills that are BOTH matched and required, preserving JD order.
    required = reqs.must_have_skills + reqs.nice_to_have_skills
    ordered = [s for s in required if s in set(fit.matched_skills)]
    for s in fit.matched_skills:            # then any other matched skill
        if s not in ordered:
            ordered.append(s)
    return ordered[:k]


def write_cover_letter(
    candidate: CandidateProfile,
    company: str,
    title: str,
    reqs: Requirements,
    fit: FitAnalysis,
    *,
    top_bullet: str | None = None,
    max_words: int = 300,
) -> str:
    name = candidate.name or "the candidate"
    strengths = _strengths(fit, reqs)
    strengths_str = ", ".join(strengths) if strengths else "the core of what this role needs"

    lines = [f"Dear {company} Hiring Team,", ""]
    opener = f"I'm writing to apply for the {title} role"
    if candidate.headline:
        opener += f". As {candidate.headline.rstrip('.')}, I bring directly relevant experience"
    lines.append(opener + ".")
    lines.append("")
    lines.append(f"My background maps closely to your requirements — {strengths_str}.")
    if top_bullet:
        lines.append(f"For example: {top_bullet}")

    # Honest, non-overclaiming note about a soft gap (never work_authorization).
    soft_gaps = [g for g in fit.gaps if g != "work_authorization"]
    if soft_gaps:
        g = soft_gaps[0]
        lines.append(
            f"I have less hands-on depth with {g}, but I ramp quickly and would "
            f"treat it as an early priority."
        )

    lines.append("")
    lines.append("I'd welcome the chance to discuss how I can contribute.")
    lines.append("")
    lines.append(f"Sincerely,\n{name}")

    text = "\n".join(lines)
    return _cap_words(text, max_words)


def _cap_words(text: str, max_words: int) -> str:
    words = text.split()
    if len(words) <= max_words:
        return text
    return " ".join(words[:max_words]).rstrip(",.;") + " …"


def draft_screening_answers(
    candidate: CandidateProfile,
    reqs: Requirements,
) -> tuple[dict[str, str], list[str]]:
    """Return (answered, unanswered). Heuristic path defers everything it can't
    answer truthfully; salary/visa/auth/demographic are always deferred."""
    answered: dict[str, str] = {}
    unanswered: list[str] = []
    for q in reqs.screening_questions:
        # No LLM here: we can't truthfully compose free-form answers, so defer
        # to the user. The Bedrock path answers what the profile supports.
        unanswered.append(q)
    return answered, unanswered


def is_deferred_question(question: str) -> bool:
    """True if a screening question must be left to the user (comp/visa/etc.)."""
    return bool(_DEFER.search(question))
