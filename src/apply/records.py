"""ApplicationRecord + a small JSON-file store (Stage 4/5 state).

Ties a posting to its draft materials, approval, submission receipt, and status.
Persisted under applications/ (gitignored — it references PII/materials). This
is the source of truth the review/approve/submit CLI and the monitor stage read.
"""
from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class ApplicationRecord:
    key: str                              # posting.dedupe_key()
    company: str
    title: str
    source: str
    source_url: str
    application_method: Optional[str] = None
    materials_path: Optional[str] = None
    status: str = "drafted"               # drafted -> approved -> submitted (+ monitor statuses)
    approved_at: Optional[str] = None
    receipt: Optional[dict[str, Any]] = None
    history: list[dict[str, Any]] = field(default_factory=list)   # status events (Stage 6)
    created_at: str = field(default_factory=_now)
    updated_at: str = field(default_factory=_now)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "ApplicationRecord":
        known = {k: v for k, v in d.items() if k in cls.__dataclass_fields__}
        return cls(**known)


class ApplicationStore:
    def __init__(self, path: str | Path) -> None:
        self._path = Path(path)
        self._records: dict[str, ApplicationRecord] = {}
        if self._path.exists():
            blob = json.loads(self._path.read_text() or "{}")
            self._records = {
                k: ApplicationRecord.from_dict(v) for k, v in blob.items()
            }

    def all(self) -> list[ApplicationRecord]:
        return sorted(self._records.values(), key=lambda r: r.created_at)

    def get(self, key: str) -> Optional[ApplicationRecord]:
        return self._records.get(key)

    def upsert(self, record: ApplicationRecord) -> ApplicationRecord:
        """Insert or update. Preserves created_at/approval/receipt of an existing
        record so re-running the pipeline doesn't clobber progress."""
        existing = self._records.get(record.key)
        if existing:
            record.created_at = existing.created_at
            # don't downgrade progress on a re-draft
            if existing.status in ("approved", "submitted") and record.status == "drafted":
                record.status = existing.status
                record.approved_at = existing.approved_at
                record.receipt = existing.receipt
        record.updated_at = _now()
        self._records[record.key] = record
        self._flush()
        return record

    def set_status(self, key: str, status: str) -> None:
        self._records[key].status = status
        self._records[key].updated_at = _now()
        self._flush()

    def approve(self, key: str) -> None:
        r = self._records[key]
        r.status = "approved"
        r.approved_at = _now()
        r.updated_at = _now()
        self._flush()

    def advance_status(self, key: str, status: str, *, source: str = "monitor",
                       detail: str = "", forward_only: bool = True) -> bool:
        """Move a record to `status`, logging an event. Forward-only by default
        (never regress along the lifecycle). Returns True if the status changed."""
        from src.monitor.tracker import STATUSES

        r = self._records[key]
        if forward_only and status in STATUSES and r.status in STATUSES:
            if STATUSES.index(status) <= STATUSES.index(r.status):
                return False
        r.history.append({"status": status, "at": _now(), "source": source, "detail": detail})
        r.status = status
        r.updated_at = _now()
        self._flush()
        return True

    def set_receipt(self, key: str, receipt: dict[str, Any]) -> None:
        r = self._records[key]
        r.receipt = receipt
        r.status = "submitted"
        r.updated_at = _now()
        self._flush()

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(
            json.dumps({k: v.to_dict() for k, v in self._records.items()},
                       indent=2, ensure_ascii=False)
        )
