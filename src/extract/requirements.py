"""Stage 2 — extract structured Requirements from a JD (FR-2.1/2.2/2.3).

LLM-assisted (Bedrock cheap model, e.g. Nova/Haiku) with a strict rule: NEVER
invent a field that isn't in the JD (unstated -> None/empty), and keep the JD
span each requirement came from in `evidence` (NFR-3).
"""
from __future__ import annotations

from src.ingest.base import Posting, Requirements


def extract_requirements(posting: Posting) -> Requirements:  # pragma: no cover
    # Phase P2: prompt a cheap Bedrock model with the JD; parse into Requirements;
    # populate `evidence[field] = <verbatim JD span>`; set `hard_requirements`
    # from the disqualifying subset (e.g. work_authorization, must-have degree).
    # Validate that no field was fabricated (drop anything without an evidence
    # span). Batch-friendly; prompt-cache the shared instruction preamble.
    raise NotImplementedError("Phase P2: implement Bedrock requirements extraction.")
