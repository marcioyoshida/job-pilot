"""Stage 6 — application status lifecycle + signals (FR-6.1/6.2).

Status is updated from ATS APIs (where available), inbox parsing of
confirmation/rejection/interview email, and manual override.
"""
from __future__ import annotations

from dataclasses import dataclass, field

# Ordered lifecycle (FR-6.1)
STATUSES = [
    "discovered", "drafted", "approved", "submitted", "acknowledged",
    "screening", "interview", "offer", "rejected", "withdrawn", "expired",
]
_TERMINAL = {"offer", "rejected", "withdrawn", "expired"}


@dataclass
class StatusEvent:
    status: str
    at: str
    source: str            # "ats" | "inbox" | "manual"
    detail: str = ""


@dataclass
class ApplicationStatus:
    application_key: str
    current: str = "discovered"
    history: list[StatusEvent] = field(default_factory=list)

    def advance(self, event: StatusEvent) -> None:
        if event.status not in STATUSES:
            raise ValueError(f"unknown status: {event.status}")
        self.history.append(event)
        self.current = event.status

    @property
    def is_terminal(self) -> bool:
        return self.current in _TERMINAL


def classify_inbox_message(subject: str, body: str) -> str | None:  # pragma: no cover
    """Map a recruiting email to a lifecycle status, or None if not recognized."""
    # Phase P5: lightweight classifier (keywords + cheap LLM fallback) ->
    # "acknowledged" | "screening" | "interview" | "offer" | "rejected".
    raise NotImplementedError("Phase P5: implement inbox message classification.")
