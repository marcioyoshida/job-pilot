"""Lever job-board source (Phase P0) — ToS-clean public postings API.

Endpoint (public, no auth):
    https://api.lever.co/v0/postings/{company}?mode=json

Response shape (per Lever's Postings API docs — stable, long-published):
    [ {"id", "text" (title), "hostedUrl", "applyUrl",
       "categories": {"location", "team", "commitment", "department"},
       "descriptionPlain", "description" (HTML), "workplaceType"
       (remote|hybrid|on-site), "createdAt" (epoch MILLISECONDS)}, ... ]

Note the response is a JSON ARRAY (not wrapped) and createdAt is epoch ms.

NOTE (verification): this session's egress policy blocks api.lever.co, so the
mapping follows the documented schema, not a live call. Run
`python -m src.ingest.lever <company>` on an open network once to confirm field
names (house rule). Mapping is defensive so an unexpected field won't crash.
"""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timezone
from typing import Iterable, Optional

from src.ingest.base import JobSource, Posting, SearchProfile
from src.ingest.filters import html_to_text, matches
from src.ingest.http import HttpGet, http_get_json

_API = "https://api.lever.co/v0/postings/{company}?mode=json"


def _epoch_ms_to_iso(ms: Optional[int]) -> Optional[str]:
    if not ms:
        return None
    try:
        return datetime.fromtimestamp(ms / 1000, tz=timezone.utc).isoformat()
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def _posting_from(company: str, item: dict) -> Posting:
    cats = item.get("categories") or {}
    # Prefer the already-plain description; fall back to stripping HTML.
    desc = item.get("descriptionPlain") or html_to_text(item.get("description", ""))
    return Posting(
        source="lever",
        source_url=item.get("hostedUrl", "") or item.get("applyUrl", ""),
        company=company,
        title=item.get("text", ""),
        location=cats.get("location", "") or "",
        remote_policy=(item.get("workplaceType", "") or "").lower(),
        description=desc,
        posted_at=_epoch_ms_to_iso(item.get("createdAt")),
        raw=item,
    )


class LeverSource(JobSource):
    def __init__(self, companies: list[str], http_get: HttpGet | None = None) -> None:
        self.name = "lever"
        self.companies = companies
        self._http_get = http_get or http_get_json

    def fetch(self, profile: SearchProfile) -> Iterable[Posting]:
        for company in self.companies:
            try:
                payload = self._http_get(_API.format(company=company))
            except Exception as exc:  # noqa: BLE001 - one bad company shouldn't sink the run
                print(f"lever: company '{company}' fetch failed: {exc}")
                continue
            # Lever returns a bare array; tolerate a wrapped {"data": [...]} too.
            items = payload if isinstance(payload, list) else (payload or {}).get("data", [])
            for item in items:
                posting = _posting_from(company, item)
                if matches(posting, profile):
                    yield posting


if __name__ == "__main__":  # pragma: no cover - manual live verification helper
    import json
    import sys

    company = sys.argv[1] if len(sys.argv) > 1 else "leverdemo"
    got = list(LeverSource([company]).fetch(SearchProfile()))
    print(f"{len(got)} postings from '{company}'")
    if got:
        print(json.dumps(asdict(got[0]) | {"raw": "<omitted>"}, default=str, indent=2))
