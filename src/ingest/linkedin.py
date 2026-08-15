"""LinkedIn source — PHASE P ONLY, the owner's OWN accounts.

READ CLAUDE.md "LinkedIn rules" and spec CON-1 before implementing.

- Automating even your own LinkedIn account violates LinkedIn's User Agreement
  and risks THOSE accounts being restricted/banned. This connector is
  deliberately isolated so Phase C can drop it entirely and use a licensed
  aggregator instead (same JobSource interface).
- Credentials come from the environment / a secret store at runtime — NEVER
  committed. Two accounts are supported via SearchProfile.linkedin_accounts.
- Human-paced: jitter between requests + a hard daily cap. Treat as fragile.
"""
from __future__ import annotations

import os
from typing import Iterable

from src.ingest.base import JobSource, Posting, SearchProfile

DAILY_CAP = int(os.environ.get("JOBPILOT_LINKEDIN_DAILY_CAP", "40"))
MIN_DELAY_S = float(os.environ.get("JOBPILOT_LINKEDIN_MIN_DELAY_S", "6"))


class LinkedInSource(JobSource):
    """One owner-controlled LinkedIn account (instantiate one per account)."""

    def __init__(self, account_label: str) -> None:
        self.name = f"linkedin:{account_label}"
        self.account_label = account_label
        # Credentials resolved at fetch time from env/secret — never stored here.

    def fetch(self, profile: SearchProfile) -> Iterable[Posting]:  # pragma: no cover
        # Phase P1: session login (env creds) -> run this account's saved-search
        # filters -> paginate with jitter, honoring MIN_DELAY_S and DAILY_CAP ->
        # yield Posting(source=self.name, source_url=..., company=..., title=...,
        # description=<full JD>, ...). Isolate all LinkedIn HTML/session quirks
        # here; emit only clean Posting objects.
        raise NotImplementedError(
            "Phase P1: implement owner-account LinkedIn fetch (see CON-1). "
            "Human-paced, credentials from env, hard daily cap."
        )
