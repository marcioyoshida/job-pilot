"""Shared helpers for source connectors: HTML→text, recency, profile matching.

Kept source-agnostic so every JobSource (Greenhouse, Lever, ...) filters
postings identically against a SearchProfile (FR-1.2). Pure + dependency-free.
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timedelta, timezone
from typing import Optional

from src.ingest.base import Posting, SearchProfile

_TAG = re.compile(r"<[^>]+>")
_WS = re.compile(r"\s+")


def html_to_text(raw: str) -> str:
    """Reduce (possibly HTML-escaped) HTML to readable text."""
    if not raw:
        return ""
    text = html.unescape(raw)      # &lt;p&gt; -> <p>
    text = _TAG.sub(" ", text)      # strip tags
    text = html.unescape(text)      # decode entities left behind (&amp; etc.)
    return _WS.sub(" ", text).strip()


def within_recency(posted_at: Optional[str], recency_days: int) -> bool:
    """True if posted_at (ISO 8601) is within recency_days. recency_days<=0 disables."""
    if not posted_at or recency_days <= 0:
        return True
    try:
        dt = datetime.fromisoformat(posted_at.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return True  # unparseable -> don't drop
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt >= datetime.now(timezone.utc) - timedelta(days=recency_days)


def matches(posting: Posting, profile: SearchProfile) -> bool:
    """Pure filter of a Posting against a SearchProfile. Case-insensitive."""
    title = posting.title.lower()
    haystack = f"{posting.title}\n{posting.description}".lower()
    loc = f"{posting.location} {posting.remote_policy}".lower()

    if profile.titles and not any(t.lower() in title for t in profile.titles):
        return False
    if profile.keywords and not any(k.lower() in haystack for k in profile.keywords):
        return False
    if profile.exclude_terms and any(x.lower() in haystack for x in profile.exclude_terms):
        return False
    if profile.exclude_companies and any(
        c.lower() in posting.company.lower() for c in profile.exclude_companies
    ):
        return False
    if profile.locations:
        loc_ok = any(l.lower() in loc for l in profile.locations)
        if profile.remote_ok and "remote" in loc:
            loc_ok = True
        if not loc_ok:
            return False
    if not within_recency(posting.posted_at, profile.recency_days):
        return False
    return True
