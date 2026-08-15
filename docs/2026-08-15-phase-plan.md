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
- **P1 — LinkedIn (own accounts).** Implement `src/ingest/linkedin.py` behind
  `JobSource`: session-based, 2 accounts from config, saved-search filters,
  human-paced (jitter + hard daily cap). Credentials from env/secret only.
  See CON-1 — accept the account risk knowingly.
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
- **P5 — monitor.** Status lifecycle + inbox parsing + manual override +
  notifications.
- **P6 — serverless.** Port pure functions to Lambda (DynamoDbState), Step
  Functions orchestration, EventBridge schedule, S3 materials — same account
  `my2027`, ~$100/mo ceiling.

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

P0 + P2 + P3 + P4 are done — gather→extract→match→tailor→(approve)→submit runs
offline end-to-end, with the human-approval gate enforced. Next: **P5 — monitor**
(status lifecycle already scaffolded in `src/monitor/tracker.py`; wire inbox
parsing via the connected Gmail + manual override + notifications), or **P1 —
own-account LinkedIn**, or the **LLM upgrade** (BedrockExtractor + cover-letter
prose). Tests cover every built stage plus the offline end-to-end chain.
