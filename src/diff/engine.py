"""Diff engine — surface only new-since-last-run postings (FR-1.5).

Mirrors the Signals/Onça diff engine: a State-backed seen-set keyed by a stable
dedupe key. Pure and Lambda-portable.
"""
from __future__ import annotations

from typing import Iterable

from src.ingest.base import Posting
from src.state.store import State


def new_postings(
    postings: Iterable[Posting],
    state: State,
    *,
    mark: bool = True,
) -> list[Posting]:
    """Return postings whose dedupe_key has not been seen before.

    Dedupes within this batch too (same role cross-listed across sources or the
    two LinkedIn accounts collapses to one). When `mark` is True, newly returned
    keys are recorded so the next run won't resurface them.
    """
    seen_this_batch: set[str] = set()
    fresh: list[Posting] = []
    for p in postings:
        key = p.dedupe_key()
        if key in seen_this_batch or state.seen(key):
            continue
        seen_this_batch.add(key)
        fresh.append(p)
    if mark:
        for p in fresh:
            state.mark_seen(p.dedupe_key())
    return fresh
