"""LinkedIn jobs via saved-search ALERT EMAILS — Phase P1 (ToS-clean).

Chosen over direct session scraping (see docs/2026-08-15-phase-plan.md): reading
your own LinkedIn job-alert emails is not scraping and carries no ToS/account-ban
risk, and it reuses the Stage 6 inbox adapters. You set up saved-search alerts
inside LinkedIn (one per account / per search); LinkedIn emails you matching
jobs; this source parses those emails into Postings.

Limitation: alert emails carry title + company + location + the job URL, but not
the full job description. So downstream extraction runs on the title (open the
URL for the full JD). That's the trade-off for the safe path.

The direct-session connector was intentionally NOT built — if it's ever needed,
it must stay isolated here behind JobSource, session-based, human-paced, and
Phase-C must replace it with a licensed aggregator (CLAUDE.md).
"""
from __future__ import annotations

import re
from typing import Iterable

from src.ingest.base import JobSource, Posting, SearchProfile
from src.ingest.filters import html_to_text, matches
from src.monitor.inbox import InboxMessage, InboxSource

# Senders LinkedIn uses for job alerts / job digests.
_ALERT_SENDERS = (
    "jobalerts-noreply@linkedin.com",
    "jobs-listings@linkedin.com",
    "jobs-noreply@linkedin.com",
    "jobalerts@linkedin.com",
)

# <a href="...(/comm)?/jobs/view/<id>...">Title</a>  (title may contain nested tags)
_JOB_ANCHOR = re.compile(
    r'<a[^>]+href="(?P<url>[^"]*?/jobs/view/(?P<id>\d+)[^"]*)"[^>]*>(?P<title>.*?)</a>',
    re.I | re.S,
)
# noise phrases LinkedIn appends after "Company · Location"
_LOC_NOISE = ("Actively", "Be an early", "Promoted", "Easy Apply", "View job",
              "See job", "Your job alert", "jobs")


def _canonical_url(job_id: str) -> str:
    return f"https://www.linkedin.com/jobs/view/{job_id}"


def _company_location(tail_html: str) -> tuple[str, str]:
    """Best-effort company + location from the text right after a job title."""
    text = html_to_text(tail_html)[:180]
    if "·" not in text:
        return "", ""
    parts = [p.strip() for p in text.split("·")]
    company = parts[0]
    location = parts[1] if len(parts) > 1 else ""
    for noise in _LOC_NOISE:
        idx = location.find(noise)
        if idx > 0:
            location = location[:idx].strip()
    return company, location


def parse_linkedin_alert(subject: str, body: str) -> list[Posting]:
    """Parse a LinkedIn job-alert email body into Postings (deduped by job id)."""
    by_id: dict[str, Posting] = {}
    for m in _JOB_ANCHOR.finditer(body):
        jid = m.group("id")
        title = html_to_text(m.group("title"))
        if not title:
            continue  # logo/image anchor for the same job — skip
        company, location = _company_location(body[m.end(): m.end() + 500])
        # first non-empty title for an id wins; don't overwrite a good one
        if jid not in by_id or not by_id[jid].title:
            by_id[jid] = Posting(
                source="linkedin", source_url=_canonical_url(jid),
                company=company, title=title, location=location,
                raw={"job_id": jid, "via": "alert_email"},
            )
    return [p for p in by_id.values() if p.title]


class LinkedInAlertsSource(JobSource):
    """A JobSource backed by LinkedIn alert emails from an inbox."""

    def __init__(self, inbox: InboxSource) -> None:
        self.name = "linkedin"
        self.inbox = inbox

    @staticmethod
    def _is_alert(msg: InboxMessage) -> bool:
        frm = (msg.from_addr or "").lower()
        if any(s in frm for s in _ALERT_SENDERS):
            return True
        # fall back: any linkedin sender whose subject looks like a job alert
        return "linkedin.com" in frm and any(
            k in (msg.subject or "").lower() for k in ("job", "jobs", "hiring", "opportunit")
        )

    def fetch(self, profile: SearchProfile) -> Iterable[Posting]:
        seen: set[str] = set()
        for msg in self.inbox.fetch():
            if not self._is_alert(msg):
                continue
            for posting in parse_linkedin_alert(msg.subject, msg.body):
                if posting.source_url in seen:
                    continue
                seen.add(posting.source_url)
                if matches(posting, profile):
                    yield posting
