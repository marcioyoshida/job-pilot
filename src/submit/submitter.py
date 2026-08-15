"""Stage 5 — submission with a mandatory human-approval gate (NFR-1, CON-3).

Nothing is submitted without an approved ApplicationRecord. Submission is
idempotent and records an immutable receipt tied to the exact materials sent.

Dispatch by application_method:
- "email:<addr>"  -> build an application email. A mailer is INJECTED; the
  default mailer writes a ready-to-send .eml draft and sends nothing, so no
  application leaves without the caller wiring a real sender.
- anything else (ATS web URL) -> write a one-click package (materials + the
  apply URL) for the human to finish in the browser. No unattended form
  automation (CON-3).
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any, Callable, Optional

from src.apply.records import ApplicationRecord, ApplicationStore

# A mailer sends an EmailMessage and returns a confirmation string.
Mailer = Callable[[EmailMessage], str]


class ApprovalRequired(Exception):
    """Raised if submission is attempted without an approved record."""


@dataclass
class SubmissionReceipt:
    application_key: str
    method: str                    # "email" | "email_draft" | "one_click_package"
    submitted_at: str
    confirmation: Optional[str] = None       # message id / file path / apply url
    materials_fingerprint: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        from dataclasses import asdict
        return asdict(self)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _fingerprint(materials: dict) -> str:
    basis = (materials.get("cover_letter", "") + "".join(materials.get("resume_highlights", [])))
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def _method_of(application_method: Optional[str], fallback_url: str) -> tuple[str, str]:
    """Return (kind, target) where kind is 'email' or 'one_click'."""
    if application_method and application_method.lower().startswith("email:"):
        return "email", application_method.split(":", 1)[1]
    # "greenhouse:https://..." / "lever:https://..." / None -> web apply
    if application_method and ":" in application_method:
        return "one_click", application_method.split(":", 1)[1]
    return "one_click", fallback_url


def _package_markdown(record: ApplicationRecord, materials: dict, apply_target: str,
                      via: str) -> str:
    lines = [
        f"# Application — {record.company}: {record.title}",
        "",
        f"**{via}:** {apply_target}",
        "**Status:** READY TO SUBMIT (you approved this). Nothing was auto-sent.",
        "",
        "## Resume highlights",
    ]
    lines += [f"- {h}" for h in materials.get("resume_highlights", [])] or ["- (none)"]
    lines += ["", "## Cover letter", "", materials.get("cover_letter", "")]
    answers = materials.get("screening_answers", {})
    if answers:
        lines += ["", "## Screening answers (to paste)"]
        lines += [f"- **{q}** {a}" for q, a in answers.items()]
    unanswered = materials.get("unanswered_questions", [])
    if unanswered:
        lines += ["", "## Questions needing YOUR input"]
        lines += [f"- {q}" for q in unanswered]
    return "\n".join(lines) + "\n"


def _build_email(record: ApplicationRecord, materials: dict, to_addr: str) -> EmailMessage:
    msg = EmailMessage()
    msg["To"] = to_addr
    msg["Subject"] = f"Application: {record.title}"
    body = materials.get("cover_letter", "")
    highlights = materials.get("resume_highlights", [])
    if highlights:
        body += "\n\nSelected highlights:\n" + "\n".join(f"- {h}" for h in highlights)
    msg.set_content(body)
    return msg


def default_mailer_factory(out_dir: str | Path) -> Mailer:
    """A mailer that writes an .eml draft and sends nothing (safe default)."""
    def _mailer(msg: EmailMessage) -> str:
        folder = Path(out_dir) / datetime.now(timezone.utc).date().isoformat()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / (hashlib.sha1(msg["Subject"].encode()).hexdigest()[:12] + ".eml")
        path.write_bytes(bytes(msg))
        return f"draft:{path}"
    return _mailer


def submit_record(
    record: ApplicationRecord,
    store: ApplicationStore,
    *,
    package_dir: str | Path = "packages",
    mailer: Optional[Mailer] = None,
    force: bool = False,
) -> SubmissionReceipt:
    """Submit one approved record. Idempotent unless force=True."""
    if record.status not in ("approved", "submitted"):
        raise ApprovalRequired(
            f"{record.company} — {record.title}: not approved (status={record.status})"
        )
    if record.status == "submitted" and not force:
        raise RuntimeError("idempotency: already submitted (FR-5.2); pass force to resend")
    if not record.materials_path or not Path(record.materials_path).exists():
        raise FileNotFoundError(f"materials not found for {record.key}: {record.materials_path}")

    payload = json.loads(Path(record.materials_path).read_text())
    materials = payload.get("materials", {})
    fp = _fingerprint(materials)
    kind, target = _method_of(record.application_method, record.source_url)

    Path(package_dir).mkdir(parents=True, exist_ok=True)
    if kind == "email":
        msg = _build_email(record, materials, target)
        send = mailer or default_mailer_factory(Path(package_dir) / "email")
        confirmation = send(msg)
        method = "email" if mailer else "email_draft"
    else:
        folder = Path(package_dir) / datetime.now(timezone.utc).date().isoformat()
        folder.mkdir(parents=True, exist_ok=True)
        path = folder / f"{record.key}.md"
        path.write_text(_package_markdown(record, materials, target, via="Apply at"),
                        encoding="utf-8")
        confirmation = f"{path} | apply: {target}"
        method = "one_click_package"

    receipt = SubmissionReceipt(
        application_key=record.key,
        method=method,
        submitted_at=_now(),
        confirmation=confirmation,
        materials_fingerprint=fp,
    )
    store.set_receipt(record.key, receipt.to_dict())
    return receipt
