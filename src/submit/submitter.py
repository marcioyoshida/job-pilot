"""Stage 5 — submission with a mandatory human-approval gate (NFR-1, CON-3).

Nothing is submitted without explicit approval. Submission is idempotent and
records an immutable receipt tied to the exact MaterialsVersion sent.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.ingest.base import MaterialsVersion, Posting


@dataclass
class SubmissionReceipt:
    application_key: str            # posting.dedupe_key()
    method: str                     # "ats:greenhouse" | "email" | "one_click_package"
    submitted_at: str
    confirmation: Optional[str] = None   # id / screenshot ref
    materials_fingerprint: str = ""
    raw: dict[str, Any] = field(default_factory=dict)


class ApprovalRequired(Exception):
    """Raised if submission is attempted without a recorded approval."""


def submit(
    posting: Posting,
    materials: MaterialsVersion,
    *,
    approved: bool,
    already_submitted: bool,
) -> SubmissionReceipt:  # pragma: no cover
    if not approved:
        raise ApprovalRequired(f"{posting.company} — {posting.title} not approved")
    if already_submitted:
        raise RuntimeError("idempotency: application already submitted (FR-5.2)")
    # Phase P4: dispatch by application_method — ATS API > email > one-click
    # package (default for form-only). Record and persist a SubmissionReceipt.
    raise NotImplementedError("Phase P4: implement submission dispatch + receipts.")
