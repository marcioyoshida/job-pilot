"""Thin, injectable wrapper over Bedrock Runtime's Converse API.

Mirrors the Onça/Signals synthesis pattern: a cheap model (nova-lite) via
Converse, model + region from env, prompt-cacheable system prompt. The boto3
client is created lazily and can be injected — so tests and the offline
heuristic path never import boto3 or touch the network.

Model tiering (NFR-5): default to a cheap model; callers may pass a stronger
model id for prose. Batch/prompt-caching are layered on later (Phase P6).
"""
from __future__ import annotations

import json
import os
import re
from typing import Any, Optional

_DEFAULT_MODEL = os.environ.get("JOBPILOT_BEDROCK_MODEL", "amazon.nova-lite-v1:0")
_JSON_BLOCK = re.compile(r"\{.*\}", re.S)


class BedrockLLM:
    def __init__(self, model_id: str | None = None, region: str | None = None,
                 client: Any | None = None) -> None:
        self.model_id = model_id or _DEFAULT_MODEL
        self._region = region or os.environ.get("AWS_REGION") or "us-east-1"
        self._client = client   # inject a fake in tests; real boto3 client at the edge

    @property
    def client(self) -> Any:
        if self._client is None:  # pragma: no cover - needs boto3 + creds
            import boto3
            self._client = boto3.client("bedrock-runtime", region_name=self._region)
        return self._client

    def converse(self, system: str, user: str, *, max_tokens: int = 1024,
                 temperature: float = 0.2) -> str:
        resp = self.client.converse(
            modelId=self.model_id,
            system=[{"text": system}],
            messages=[{"role": "user", "content": [{"text": user}]}],
            inferenceConfig={"maxTokens": max_tokens, "temperature": temperature},
        )
        return resp["output"]["message"]["content"][0]["text"]

    def converse_json(self, system: str, user: str, **kw: Any) -> dict:
        """Converse and parse the first JSON object from the reply."""
        return extract_json(self.converse(system, user, **kw))


def extract_json(text: str) -> dict:
    """Pull the first {...} JSON object out of a model reply (tolerates fences)."""
    m = _JSON_BLOCK.search(text)
    if not m:
        raise ValueError("no JSON object in model output")
    return json.loads(m.group(0))
