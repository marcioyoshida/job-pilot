"""AWS Lambda entrypoint for the daily batch (Phase P6).

The unattended job runs gather -> extract -> match -> tailor and writes results
to S3 (materials/<run>/<key>.json + feed/<run>.json + feed/latest.json), using
DynamoDbState for the new-since-last-run seen-set. Human review/approve/submit
stays a local/manual concern (NFR-1) — the cloud job never submits anything.

`run_pipeline` is the pure-ish core: every dependency (sources, state, extractor,
object writer, cover-letter LLM) is injected, so it's unit-tested with fakes and
never needs AWS. `pipeline_handler` wires the real S3 / DynamoDB / Bedrock.
"""
from __future__ import annotations

import json
from dataclasses import asdict
from datetime import datetime, timezone
from typing import Callable, Optional

# Concrete imports (kept explicit for Lambda cold-start clarity)
from src.dashboard.render import feed_item
from src.diff.engine import new_postings
from src.match.fit import analyze_fit
from src.tailor.build import build_materials

PutObject = Callable[[str, str], None]   # (key, body) -> None


def run_pipeline(
    sources: list,
    profile,
    candidate,
    state,
    extractor,
    put_object: PutObject,
    *,
    run_id: str,
    cover_llm: Optional[object] = None,
) -> list[dict]:
    """Gather -> extract -> match -> tailor; write materials + a feed to S3.

    Returns the feed (list of dicts, best fit first). Drafts are written only for
    apply/stretch roles and are never submitted.
    """
    cand_skills = candidate.normalized_skills()

    collected = []
    for s in sources:
        try:
            collected.extend(s.fetch(profile))
        except Exception as exc:  # noqa: BLE001 - isolate a bad source
            print(f"source '{getattr(s, 'name', '?')}' failed: {exc}")
    fresh = new_postings(collected, state)

    feed: list[dict] = []
    for p in fresh:
        try:
            reqs = extractor.extract(p)
        except Exception as exc:  # noqa: BLE001 - fall back per posting
            from src.extract.requirements import extract_requirements
            print(f"extract failed for {p.company} ({exc}); heuristic fallback")
            reqs = extract_requirements(p)
        fit = analyze_fit(reqs, cand_skills)
        materials_key = None
        if fit.recommendation in ("apply", "stretch"):
            materials = build_materials(candidate, p, reqs, fit, llm=cover_llm)
            materials_key = f"materials/{run_id}/{p.dedupe_key()}.json"
            put_object(materials_key, json.dumps({
                "status": "draft_pending_approval",
                "posting": feed_item(p, fit),
                "materials": asdict(materials),
            }, ensure_ascii=False, indent=2))
        feed.append(feed_item(p, fit, materials_key))

    feed.sort(key=lambda i: i["fit_score"], reverse=True)
    body = json.dumps({"run_id": run_id, "generated_at": run_id, "items": feed},
                      ensure_ascii=False, indent=2)
    put_object(f"feed/{run_id}.json", body)
    put_object("feed/latest.json", body)
    return feed


def _build_sources(profile, get_secret):
    from src.ingest.greenhouse import GreenhouseSource
    from src.ingest.lever import LeverSource

    sources = []
    if profile.greenhouse_boards:
        sources.append(GreenhouseSource(boards=profile.greenhouse_boards))
    if profile.lever_companies:
        sources.append(LeverSource(companies=profile.lever_companies))
    # Optional LinkedIn alert ingestion if a Gmail app-password secret is present
    creds = get_secret()
    if creds and creds.get("GMAIL_ADDRESS") and creds.get("GMAIL_APP_PASSWORD"):
        from src.ingest.linkedin import LinkedInAlertsSource
        from src.monitor.inbox import GmailImapInbox
        sources.append(LinkedInAlertsSource(GmailImapInbox(
            address=creds["GMAIL_ADDRESS"], app_password=creds["GMAIL_APP_PASSWORD"])))
    return sources


def pipeline_handler(event, context):  # pragma: no cover - AWS wiring
    """Lambda handler. Env: JOBPILOT_BUCKET, JOBPILOT_TABLE, JOBPILOT_USE_LLM,
    JOBPILOT_BEDROCK_MODEL, JOBPILOT_GMAIL_SECRET_ARN (optional)."""
    import os

    import boto3
    import yaml

    from src.ingest.base import SearchProfile
    from src.profile.candidate import CandidateProfile
    from src.state.store import DynamoDbState

    bucket = os.environ["JOBPILOT_BUCKET"]
    s3 = boto3.client("s3")

    def get_text(key: str) -> str:
        return s3.get_object(Bucket=bucket, Key=key)["Body"].read().decode("utf-8")

    def put_object(key: str, body: str) -> None:
        s3.put_object(Bucket=bucket, Key=key, Body=body.encode("utf-8"),
                      ContentType="application/json")

    def get_secret():
        arn = os.environ.get("JOBPILOT_GMAIL_SECRET_ARN")
        if not arn:
            return None
        val = boto3.client("secretsmanager").get_secret_value(SecretId=arn)["SecretString"]
        return json.loads(val)

    profile = SearchProfile.from_dict(yaml.safe_load(get_text("config/search_profile.yaml")))
    candidate = CandidateProfile.from_dict(yaml.safe_load(get_text("config/candidate.yaml")))
    state = DynamoDbState(os.environ.get("JOBPILOT_TABLE"))

    use_llm = os.environ.get("JOBPILOT_USE_LLM", "").lower() in ("1", "true", "yes")
    extractor = None
    cover_llm = None
    if use_llm:
        from src.extract.requirements import BedrockExtractor
        from src.llm.bedrock import BedrockLLM
        cover_llm = BedrockLLM()
        extractor = BedrockExtractor(cover_llm)
    else:
        from src.extract.requirements import HeuristicExtractor
        extractor = HeuristicExtractor()

    run_id = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")
    feed = run_pipeline(_build_sources(profile, get_secret), profile, candidate,
                        state, extractor, put_object, run_id=run_id, cover_llm=cover_llm)
    return {"run_id": run_id, "count": len(feed),
            "drafts": sum(1 for i in feed if "materials_key" in i)}
