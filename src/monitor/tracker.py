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


KEY_TRANSITIONS = {"interview", "offer", "rejected"}   # worth notifying on

# Checked in order; the first bucket that matches wins. Rejection is checked
# before offer/interview so a "unfortunately... after your interview" reads as a
# rejection, not an interview.
_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("rejected", ("unfortunately", "not moving forward", "won't be moving",
                  "will not be moving", "decided not to", "regret to inform",
                  "not selected", "other candidates", "won't be proceeding",
                  "unable to offer", "not to proceed", "position has been filled")),
    ("offer", ("pleased to offer", "offer letter", "extend an offer",
               "job offer", "excited to offer", "we are offering")),
    ("interview", ("schedule an interview", "interview", "phone screen",
                   "meet with", "your availability", "book a time",
                   "set up a call", "video call", "hiring manager")),
    ("screening", ("assessment", "coding challenge", "take-home", "take home",
                   "online test", "screening", "questionnaire")),
    ("acknowledged", ("received your application", "thank you for applying",
                      "application received", "thanks for your interest",
                      "we have received", "successfully submitted")),
]


def classify_inbox_message(subject: str, body: str) -> str | None:
    """Map a recruiting email to a lifecycle status, or None if not recognized."""
    text = f"{subject}\n{body}".lower()
    for status, phrases in _RULES:
        if any(p in text for p in phrases):
            return status
    return None


def _norm_company(name: str) -> str:
    n = name.lower()
    for suffix in (" inc", " inc.", " llc", " ltd", " ltda", " s.a.", " sa", " co", " corp"):
        if n.endswith(suffix):
            n = n[: -len(suffix)]
    return n.strip()


def match_to_application(msg, records) -> "object | None":
    """Best-matching ApplicationRecord for an InboxMessage, or None.

    Requires a company signal (name in the from-address or the text); the title
    overlap is a tie-breaker. Deliberately conservative — better to miss than to
    advance the wrong application.
    """
    hay = f"{getattr(msg, 'subject', '')}\n{getattr(msg, 'body', '')}\n" \
          f"{getattr(msg, 'from_addr', '')}".lower()
    best, best_score = None, 0
    for r in records:
        company = _norm_company(r.company)
        score = 0
        if company and company in hay:
            score += 3
        # company token appearing in the sender domain is a strong signal too
        if company and company.replace(" ", "") in hay.replace(" ", ""):
            score += 1
        title_words = [w for w in r.title.lower().split() if len(w) > 3]
        score += sum(1 for w in title_words if w in hay)
        if score > best_score and score >= 3:   # company match is required
            best, best_score = r, score
    return best


def monitor_messages(messages, store, notify=None) -> list[tuple[str, str, str]]:
    """Classify + match + forward-advance each message against the store.

    Returns a list of (application_key, company_title, new_status) for the
    transitions that actually happened. `notify` (optional) is called for the
    key transitions (interview/offer/rejected).
    """
    transitions: list[tuple[str, str, str]] = []
    for msg in messages:
        status = classify_inbox_message(getattr(msg, "subject", ""), getattr(msg, "body", ""))
        if not status:
            continue
        record = match_to_application(msg, store.all())
        if not record:
            continue
        changed = store.advance_status(record.key, status, source="inbox",
                                       detail=getattr(msg, "subject", ""))
        if changed:
            label = f"{record.company} — {record.title}"
            transitions.append((record.key, label, status))
            if notify and status in KEY_TRANSITIONS:
                notify(label, status)
    return transitions
