"""Assemble a draft MaterialsVersion from a posting + fit (Stage 4 orchestration).

Output is a DRAFT — Stage 5 (submit) requires explicit human approval (NFR-1).
Nothing here submits anything.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from pathlib import Path

from src.ingest.base import FitAnalysis, MaterialsVersion, Posting, Requirements
from src.profile.candidate import CandidateProfile
from src.tailor.cover_letter import draft_screening_answers, write_cover_letter
from src.tailor.resume import tailor_highlights, verify_provenance


def build_materials(
    candidate: CandidateProfile,
    posting: Posting,
    reqs: Requirements,
    fit: FitAnalysis,
    llm: "object | None" = None,
) -> MaterialsVersion:
    highlights, provenance = tailor_highlights(candidate, reqs, fit)
    top_bullet = highlights[0] if highlights else None
    if llm is not None:
        from src.tailor.cover_letter import write_cover_letter_llm

        cover = write_cover_letter_llm(
            candidate, posting.company, posting.title, reqs, fit, llm,
            top_bullet=top_bullet,
        )
    else:
        cover = write_cover_letter(
            candidate, posting.company, posting.title, reqs, fit, top_bullet=top_bullet
        )
    answered, unanswered = draft_screening_answers(candidate, reqs)

    materials = MaterialsVersion(
        resume_highlights=highlights,
        bullet_provenance=provenance,
        cover_letter=cover,
        screening_answers=answered,
        unanswered_questions=unanswered,
        created_at=datetime.now(timezone.utc).isoformat(),
    )
    # Hard guard (CON-4): refuse to emit materials that don't fully trace back.
    if not verify_provenance(materials, candidate):
        raise ValueError("provenance check failed — a highlight is not backed by a master bullet")
    return materials


def write_materials(materials: MaterialsVersion, posting: Posting, out_dir: str | Path) -> Path:
    """Persist a DRAFT materials package to out_dir/{date}/{key}.json (gitignored)."""
    date = datetime.now(timezone.utc).date().isoformat()
    folder = Path(out_dir) / date
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{posting.dedupe_key()}.json"
    payload = {
        "status": "draft_pending_approval",   # NFR-1: never auto-submitted
        "posting": {"company": posting.company, "title": posting.title,
                    "source": posting.source, "source_url": posting.source_url},
        "materials": asdict(materials),
    }
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False))
    return path
