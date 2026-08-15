#!/usr/bin/env python3
"""Live-verify the AWS + Bedrock path for job-pilot.

Run this on a machine with real my2027 credentials (this proves the LLM path
end-to-end; the offline heuristic never needs it). Usage (venv active):

    python scripts/live_check.py

It checks: boto3 present -> STS caller identity (expects account 668449743071)
-> a tiny Bedrock Converse call with the configured model.
"""
from __future__ import annotations

import os
import sys

# Make `src` importable no matter the cwd (scripts/ is on sys.path, repo root isn't).
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

EXPECTED_ACCOUNT = "668449743071"  # my2027


def main() -> int:
    try:
        import boto3
    except ImportError:
        print("boto3 not installed — activate the venv and `pip install -r requirements.txt`.")
        return 2

    region = os.environ.get("AWS_REGION") or "us-east-1"

    try:
        acct = boto3.client("sts", region_name=region).get_caller_identity()["Account"]
    except Exception as exc:  # noqa: BLE001
        print(f"STS get_caller_identity failed: {exc}")
        print("→ These aren't valid AWS creds. Log in to the my2027 account first.")
        return 1
    ok = "OK" if acct == EXPECTED_ACCOUNT else "WARNING: unexpected account"
    print(f"AWS account: {acct} (expected {EXPECTED_ACCOUNT} / my2027) — {ok}")

    from src.llm.bedrock import BedrockLLM

    llm = BedrockLLM(region=region)
    print(f"Bedrock model: {llm.model_id} @ {region}")
    try:
        reply = llm.converse("Reply with exactly: OK", "ping", max_tokens=10)
    except Exception as exc:  # noqa: BLE001
        print(f"Bedrock Converse failed: {exc}")
        print("→ Enable model access for this model id in this region "
              "(Bedrock console → Model access), or set JOBPILOT_BEDROCK_MODEL.")
        return 1
    print(f"Converse reply: {reply.strip()!r}")
    print("LLM path is LIVE ✔  — you can now run `run.py pipeline --tailor --llm`.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
