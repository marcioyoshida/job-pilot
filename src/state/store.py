"""State behind a narrow interface — JsonState locally, DynamoDbState in Lambda.

Mirrors the Signals/Onça convention so the same code runs locally and in AWS.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Iterable, Protocol


class State(Protocol):
    """A seen-set + small key/value store keyed by string."""

    def seen(self, key: str) -> bool: ...
    def mark_seen(self, key: str) -> None: ...
    def get(self, key: str) -> str | None: ...
    def put(self, key: str, value: str) -> None: ...


class JsonState:
    """Local file-backed state for `run.py` / tests."""

    def __init__(self, path: str | os.PathLike[str]) -> None:
        self._path = Path(path)
        self._data: dict[str, str] = {}
        self._seen: set[str] = set()
        if self._path.exists():
            blob = json.loads(self._path.read_text() or "{}")
            self._data = blob.get("kv", {})
            self._seen = set(blob.get("seen", []))

    def seen(self, key: str) -> bool:
        return key in self._seen

    def mark_seen(self, key: str) -> None:
        self._seen.add(key)
        self._flush()

    def mark_all_seen(self, keys: Iterable[str]) -> None:
        self._seen.update(keys)
        self._flush()

    def get(self, key: str) -> str | None:
        return self._data.get(key)

    def put(self, key: str, value: str) -> None:
        self._data[key] = value
        self._flush()

    def _flush(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._path.write_text(json.dumps({"kv": self._data, "seen": sorted(self._seen)}))


class DynamoDbState:
    """State backed by a single DynamoDB table (Phase P6 / Lambda).

    Single-table design keyed by a partition key `pk`:
      - seen-set:  pk = "seen#<key>"     (presence == seen)
      - kv store:  pk = "kv#<name>"      (attribute `value`)

    One item per seen key — no single hot item to grow past the 400KB limit or
    serialize writes against (the failure Onça hit with a monolithic seen-set).
    On-demand billing means idle cost is ~zero. The boto3 Table resource is
    injectable so tests use an in-memory fake and never touch AWS.
    """

    def __init__(self, table_name: str | None = None, *, table: object | None = None) -> None:
        import os

        self.table_name = table_name or os.environ.get("JOBPILOT_TABLE", "job-pilot")
        self._table = table

    @property
    def table(self):
        if self._table is None:  # pragma: no cover - needs boto3 + AWS
            import boto3
            self._table = boto3.resource("dynamodb").Table(self.table_name)
        return self._table

    def seen(self, key: str) -> bool:
        return "Item" in self.table.get_item(Key={"pk": f"seen#{key}"})

    def mark_seen(self, key: str) -> None:
        self.table.put_item(Item={"pk": f"seen#{key}"})

    def get(self, key: str) -> str | None:
        item = self.table.get_item(Key={"pk": f"kv#{key}"}).get("Item")
        return item.get("value") if item else None

    def put(self, key: str, value: str) -> None:
        self.table.put_item(Item={"pk": f"kv#{key}", "value": value})
