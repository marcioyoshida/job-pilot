"""Core data types and the JobSource interface shared across all stages.

Keep these dataclasses dependency-free and Lambda-portable. Every source
connector (LinkedIn, Greenhouse, Lever, a licensed aggregator) implements
`JobSource`, so stages 2-6 never know which source a posting came from.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime
from typing import Any, Iterable, Optional, Protocol, runtime_checkable


def _norm(s: str) -> str:
    return " ".join(s.lower().split())


@dataclass
class Posting:
    """A raw + lightly-normalized job posting from a source (Stage 1)."""

    source: str                      # "greenhouse" | "lever" | "linkedin:acct1" | ...
    source_url: str
    company: str
    title: str
    location: str = ""
    remote_policy: str = ""          # "remote" | "hybrid" | "onsite" | ""
    description: str = ""            # raw JD text
    posted_at: Optional[str] = None  # ISO date if known
    first_seen: Optional[str] = None
    last_seen: Optional[str] = None
    raw: dict[str, Any] = field(default_factory=dict)

    def dedupe_key(self) -> str:
        """Stable identity across sources and across LinkedIn accounts."""
        basis = "|".join(
            [_norm(self.company), _norm(self.title), _norm(self.location),
             hashlib.sha1(_norm(self.description).encode()).hexdigest()[:12]]
        )
        return hashlib.sha1(basis.encode()).hexdigest()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Requirements:
    """Structured requirements extracted from a JD (Stage 2).

    Unstated fields stay None/empty — never guessed. `evidence` maps each
    field/skill to the JD span it came from (NFR-3 traceability).
    """

    must_have_skills: list[str] = field(default_factory=list)
    nice_to_have_skills: list[str] = field(default_factory=list)
    years_experience: Optional[int] = None
    education: Optional[str] = None
    certifications: list[str] = field(default_factory=list)
    responsibilities: list[str] = field(default_factory=list)
    domain: Optional[str] = None
    location: Optional[str] = None
    remote_policy: Optional[str] = None
    work_authorization: Optional[str] = None
    languages: list[str] = field(default_factory=list)
    comp: Optional[str] = None
    seniority: Optional[str] = None
    application_method: Optional[str] = None   # "greenhouse:<url>" | "email:<addr>" | ...
    screening_questions: list[str] = field(default_factory=list)
    hard_requirements: list[str] = field(default_factory=list)   # subset that is disqualifying
    evidence: dict[str, str] = field(default_factory=dict)       # field/skill -> JD span


@dataclass
class FitAnalysis:
    """Candidate-vs-posting fit (Stage 3). `fit_score` is ESTIMATED (house rule)."""

    fit_score: float                       # 0.0-1.0, estimated
    matched_skills: list[str] = field(default_factory=list)
    gaps: list[str] = field(default_factory=list)
    recommendation: str = "review"         # "apply" | "stretch" | "skip"
    estimated: bool = True
    notes: str = ""


@dataclass
class MaterialsVersion:
    """A tailored, immutable-once-submitted application package (Stage 4)."""

    resume_highlights: list[str] = field(default_factory=list)   # each maps to a real master bullet
    bullet_provenance: dict[str, str] = field(default_factory=dict)  # highlight -> master item id
    cover_letter: str = ""
    screening_answers: dict[str, str] = field(default_factory=dict)
    unanswered_questions: list[str] = field(default_factory=list)
    created_at: str = ""


@runtime_checkable
class JobSource(Protocol):
    """A source of postings. Everything source-specific lives behind this.

    Phase C swaps LinkedIn-by-personal-account for a licensed aggregator by
    providing a different JobSource — stages 2-6 are untouched.
    """

    name: str

    def fetch(self, profile: "SearchProfile") -> Iterable[Posting]:
        """Yield postings matching the profile. Pure-ish; no persistence here."""
        ...


@dataclass
class SearchProfile:
    """Drives Stage 1 gathering (FR-1.2)."""

    titles: list[str] = field(default_factory=list)
    keywords: list[str] = field(default_factory=list)
    seniority: list[str] = field(default_factory=list)
    locations: list[str] = field(default_factory=list)
    remote_ok: bool = True
    industries: list[str] = field(default_factory=list)
    exclude_terms: list[str] = field(default_factory=list)
    exclude_companies: list[str] = field(default_factory=list)
    recency_days: int = 14
    # Greenhouse board tokens to poll (e.g. "gitlab", "coinbase") — Phase P0
    greenhouse_boards: list[str] = field(default_factory=list)
    # LinkedIn: per-account saved-search filter names/urls (Phase P only)
    linkedin_accounts: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "SearchProfile":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)
