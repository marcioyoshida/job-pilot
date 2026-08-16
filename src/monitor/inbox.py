"""Inbox adapters for Stage 6 monitoring (FR-6.2).

One interface, two adapters:
- FileInbox: reads messages from a JSON file — the local/testable path, and how
  you feed exported mail without granting live access.
- GmailImapInbox: reads recent mail over IMAP using an app password from the
  environment (stdlib imaplib, no extra deps). The connection is injectable so
  tests never hit the network. Credentials come from env, never the repo.

An InboxMessage is deliberately minimal: enough to classify a status and match
it to an application.
"""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional, Protocol


@dataclass
class InboxMessage:
    subject: str = ""
    body: str = ""
    from_addr: str = ""
    date: Optional[str] = None
    message_id: Optional[str] = None

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "InboxMessage":
        return cls(
            subject=d.get("subject", ""),
            body=d.get("body", "") or d.get("snippet", ""),
            from_addr=d.get("from_addr", "") or d.get("from", ""),
            date=d.get("date"),
            message_id=d.get("message_id") or d.get("id"),
        )


class InboxSource(Protocol):
    def fetch(self) -> Iterable[InboxMessage]: ...


class FileInbox(InboxSource):
    """Read messages from a JSON file: a list of {subject, body, from, date, id}."""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    def fetch(self) -> Iterable[InboxMessage]:
        raw = json.loads(self.path.read_text() or "[]")
        return [InboxMessage.from_dict(m) for m in raw]


class GmailImapInbox(InboxSource):
    """Recent Gmail over IMAP (imaplib). App password + address from env:

        GMAIL_ADDRESS, GMAIL_APP_PASSWORD   (create at myaccount.google.com)

    `connect` is injectable for tests; the default opens a real TLS IMAP session.
    Reads only recent messages and only the fields we need.
    """

    def __init__(self, address: str | None = None, app_password: str | None = None,
                 *, folder: str = "INBOX", limit: int = 50,
                 connect: "object | None" = None) -> None:
        import os

        self.address = address or os.environ.get("GMAIL_ADDRESS", "")
        self._password = app_password or os.environ.get("GMAIL_APP_PASSWORD", "")
        self.folder = folder
        self.limit = limit
        self._connect = connect  # callable() -> imap-like client, for tests

    def _open(self):  # pragma: no cover - real network
        if self._connect is not None:
            return self._connect()
        import imaplib

        if not self.address or not self._password:
            raise RuntimeError("set GMAIL_ADDRESS and GMAIL_APP_PASSWORD in the environment")
        imap = imaplib.IMAP4_SSL("imap.gmail.com")
        try:
            imap.login(self.address, self._password)
        except imaplib.IMAP4.error as exc:
            raise RuntimeError(
                "Gmail IMAP login failed — use a Google APP PASSWORD, not your normal "
                "password (enable 2-Step Verification, then create one at "
                "https://myaccount.google.com/apppasswords), and make sure IMAP is on in "
                "Gmail settings. Set GMAIL_ADDRESS + GMAIL_APP_PASSWORD. Detail: "
                f"{exc}"
            ) from exc
        return imap

    def fetch(self) -> Iterable[InboxMessage]:
        import email
        from email.header import decode_header, make_header

        imap = self._open()
        out: list[InboxMessage] = []
        try:
            imap.select(self.folder)
            typ, data = imap.search(None, "ALL")
            ids = (data[0].split() if data and data[0] else [])[-self.limit:]
            for mid in reversed(ids):
                typ, msg_data = imap.fetch(mid, "(RFC822)")
                if not msg_data or not msg_data[0]:
                    continue
                msg = email.message_from_bytes(msg_data[0][1])
                out.append(InboxMessage(
                    subject=str(make_header(decode_header(msg.get("Subject", "")))),
                    body=_plain_body(msg),
                    from_addr=str(make_header(decode_header(msg.get("From", "")))),
                    date=msg.get("Date"),
                    message_id=msg.get("Message-ID"),
                ))
        finally:
            try:
                imap.logout()
            except Exception:  # noqa: BLE001
                pass
        return out


def _plain_body(msg) -> str:  # pragma: no cover - exercised via GmailImapInbox
    if msg.is_multipart():
        for part in msg.walk():
            if part.get_content_type() == "text/plain":
                try:
                    return part.get_payload(decode=True).decode(errors="ignore")
                except Exception:  # noqa: BLE001
                    return ""
        return ""
    try:
        return msg.get_payload(decode=True).decode(errors="ignore")
    except Exception:  # noqa: BLE001
        return msg.get_payload() or ""
