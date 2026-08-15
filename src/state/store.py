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
    """Lambda state. Implement in Phase P6 (mirror Onça's sharded seen-set).

    Kept as a seam so the pipeline can move to AWS without touching stage logic.
    """

    def __init__(self, table_name: str, shard_count: int = 8) -> None:
        self.table_name = table_name
        self.shard_count = shard_count

    def seen(self, key: str) -> bool:  # pragma: no cover - AWS seam
        raise NotImplementedError("Phase P6: wire DynamoDB seen-set (sharded).")

    def mark_seen(self, key: str) -> None:  # pragma: no cover - AWS seam
        raise NotImplementedError("Phase P6: wire DynamoDB seen-set (sharded).")

    def get(self, key: str) -> str | None:  # pragma: no cover - AWS seam
        raise NotImplementedError("Phase P6: wire DynamoDB kv.")

    def put(self, key: str, value: str) -> None:  # pragma: no cover - AWS seam
        raise NotImplementedError("Phase P6: wire DynamoDB kv.")
