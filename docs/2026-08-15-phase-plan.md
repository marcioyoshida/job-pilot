# job-pilot — phase plan (2026-08-15)

Mirrors the Signals/Onça phase-doc style. Status is **scaffold only** — the
`src/` tree defines interfaces + a few working pure functions (diff, taxonomy,
fit). External I/O (LinkedIn, ATS APIs, Bedrock, email) is stubbed with clear
`NotImplementedError` seams.

## Phase P — personal (CURRENT)

Goal: a working single-user tool for the owner's own job search.

- **P0 — spine (DONE 2026-08-15).** `SearchProfile` config + `JobSource`
  interface + diff engine + `JsonState`, plus a working **Greenhouse** source
  (`src/ingest/greenhouse.py`) **and Lever** (`src/ingest/lever.py`) sources:
  public APIs → `Posting`, shared `src/ingest/filters.py` (HTML→text, recency,
  `matches()`) and `src/ingest/http.py` (injectable HTTP for tests). Both wired
  into `run.py gather` end-to-end into deduped, new-only postings. Tests:
  `tests/test_greenhouse.py`, `tests/test_lever.py` (20 total green).
  **Live-verify pending:** this build's egress policy blocks the job-board
  hosts, so run `python -m src.ingest.greenhouse gitlab` and
  `python -m src.ingest.lever netflix` on an unrestricted network once to
  confirm the schemas (house rule).
- **P1 — LinkedIn via alert emails (DONE 2026-08-15).** Chose the ToS-clean
  path over direct scraping: `src/ingest/linkedin.py` `parse_linkedin_alert`
  turns LinkedIn saved-search job-alert emails into Postings (title/company/
  location/canonical job URL, defensive), and `LinkedInAlertsSource` reads them
  from any `InboxSource` (FileInbox or GmailImapInbox), filtering to LinkedIn
  alert senders, deduping by job id, applying the profile. Wired into
  `gather`/`pipeline` via `--linkedin-inbox <file>` / `--linkedin-gmail`. No
  LinkedIn creds or scraping; no account-ban risk. Limitation: alerts carry no
  full JD, so extraction runs on the title. Direct-session scraping was
  intentionally not built. Tests: `tests/test_linkedin_alerts.py` (55 total
  green).
- **P2 — extract + match (DONE 2026-08-15).** `HeuristicExtractor`
  (`src/extract/requirements.py`): deterministic, offline JD→`Requirements` —
  taxonomy skill scan with must/nice split + evidence spans, years/education/
  work-auth(+hard)/seniority/remote. No fabrication (only reports what's in the
  JD). `BedrockExtractor` left as a guarded LLM seam (Phase P2-LLM).
  `CandidateProfile` (`src/profile/candidate.py`) + `config/candidate.example.
  yaml` feed `analyze_fit`. `run.py pipeline` runs gather→extract→match ranked
  by fit. Tests: `tests/test_extract.py`, `tests/test_pipeline_integration.py`
  (28 total green).
- **P3 — tailor (DONE 2026-08-15).** `src/tailor/`: `resume.py` ranks master
  bullets by relevance and emits highlights with `bullet_provenance` (every
  highlight verbatim from a real bullet id) + `verify_provenance` guard;
  `cover_letter.py` writes an honest templated letter (never overclaims, never
  surfaces work-auth as a talking point) + defers salary/visa/demographic
  screening questions; `build.py` assembles a DRAFT `MaterialsVersion` (refuses
  to emit if provenance fails) and writes it to `materials/{date}/` (gitignored,
  `status=draft_pending_approval`). `run.py pipeline --tailor` produces drafts
  for apply/stretch roles. LLM prose left as guarded seams. Tests:
  `tests/test_tailor.py` (34 total green).
- **P4 — approval + submit (DONE 2026-08-15).** `ApplicationRecord` +
  `ApplicationStore` (`src/apply/records.py`) persist drafted→approved→submitted
  under `applications/` (gitignored); re-drafts never downgrade progress.
  `src/submit/submitter.py` enforces the approval gate + idempotency and
  dispatches by `application_method`: ATS URL → one-click package (markdown +
  apply URL, CON-3 no auto-form-fill); `email:<addr>` → email via an INJECTED
  mailer that defaults to writing an `.eml` draft and sends nothing. Receipts
  carry a materials fingerprint. CLI: `run.py review | approve | submit`.
  Tests: `tests/test_submit.py` (40 total green).
- **P5 — monitor (DONE 2026-08-15).** `src/monitor/tracker.py`:
  `classify_inbox_message` (keyword buckets: acknowledged/screening/interview/
  offer/rejected, rejection checked first), `match_to_application` (company
  signal required, title as tie-breaker), `monitor_messages` orchestration.
  Forward-only `advance_status` with per-record `history` in
  `src/apply/records.py`. Inbox adapters (`src/monitor/inbox.py`): `FileInbox`
  (JSON, local/testable) + `GmailImapInbox` (imaplib, env app-password,
  injectable). CLI: `run.py monitor --inbox <file> | --gmail` (notifies on
  interview/offer/rejected) and `run.py status --key --set` (manual override).
  Tests: `tests/test_monitor.py` (51 total green).
- **P6 — serverless (DEPLOYED 2026-08-16 on my2027 / us-east-1).**
  `DynamoDbState` implemented (single-table seen-set + kv, injectable, tested).
  `src/aws/handler.py`: `run_pipeline` core (injectable state/sources/extractor/
  object-writer/LLM → writes `materials/<run>/…` + `feed/<run>.json` +
  `feed/latest.json` to S3; diff-aware; never submits) with `pipeline_handler`
  wiring S3/DynamoDB/Bedrock. CDK stack `infra/app.py` follows the Onça
  hand-staged `build/lambda` asset (no Docker): DynamoDB on-demand, S3,
  Python Lambda, daily EventBridge (07:00 UTC), IAM for Bedrock/Dynamo/S3.
  Staging: `scripts/stage_lambda.sh`. Runbook:
  `docs/2026-08-16-phase6-serverless.md`. Tests: `tests/test_aws.py` (67 total
  green). First live invoke: 7 postings, 0 drafts (all `skip`).

- **LLM upgrade (DONE 2026-08-15).** `src/llm/bedrock.py` — injectable
  `BedrockLLM` over the Converse API (nova-lite default, model/region from env,
  lazy boto3). `BedrockExtractor` (`src/extract/requirements.py`) parses JSON
  requirements and DROPS any skill/field whose evidence quote isn't verbatim in
  the JD (anti-fabrication). `write_cover_letter_llm` writes prose grounded only
  in real profile facts. `run.py pipeline --llm` (env `JOBPILOT_USE_LLM`) opts
  in, with graceful per-call fallback to the heuristic. Tests use a fake client
  (`tests/test_llm.py`, 45 total green). **Live-verify pending:** this
  environment has only the proxy's placeholder AWS creds (STS
  InvalidClientTokenId), so run the one-liner in GETTING_STARTED on a machine
  with real my2027 creds + Bedrock model access.

## Phase C — customer product (LATER)

- Remove personal-account LinkedIn; swap to a **licensed aggregator** connector
  (same `JobSource` interface).
- Multi-tenant: per-tenant profiles, materials, state, PII isolation, billing.
- ATS status APIs, assisted browser automation, full funnel dashboard,
  follow-up automation.

## First thing next session

P0–P6 + the LLM upgrade are done — **all six stages** run locally
(gather→extract→match→tailor→approve→submit→monitor), and the unattended
gather→extract→match→tailor batch is live on my2027 (daily 07:00 UTC).
Human-approval gate is still local (NFR-1). 67 tests green. Remaining
Phase-P options: **P1 — own-account LinkedIn** (intentionally not built;
alerts path is the ToS-clean source), more ATS sources (Ashby), a
DynamoDB-backed ApplicationStore / dashboard so approve/submit can happen
against `feed/latest.json`, or richer notifications/digest.
