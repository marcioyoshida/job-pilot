"""Tiny shared HTTP helper for source connectors.

Injectable everywhere (sources take an `http_get` callable) so tests never touch
the network and the same code runs locally or in Lambda.
"""
from __future__ import annotations

import json
import os
import urllib.request
from typing import Callable

# url -> parsed JSON (dict or list, depending on the API)
HttpGet = Callable[[str], object]

_UA = "job-pilot/0.1 (+https://github.com/marcioyoshida/job-pilot)"
# Behind a VPN/corporate proxy latency can be higher; make the timeout tunable.
# urllib already honors HTTPS_PROXY / *_proxy env vars, so a proxy needs no code.
_TIMEOUT = float(os.environ.get("JOBPILOT_HTTP_TIMEOUT_S", "20"))


def http_get_json(url: str, timeout: float | None = None) -> object:  # pragma: no cover - network
    req = urllib.request.Request(url, headers={"User-Agent": _UA})
    with urllib.request.urlopen(req, timeout=timeout or _TIMEOUT) as resp:
        return json.loads(resp.read().decode("utf-8"))
