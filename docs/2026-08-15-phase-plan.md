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
- **P2 — extract + match.** `Requirements` extraction (Bedrock cheap model,
  evidence spans) + taxonomy normalization + `FitAnalysis`.
- **P3 — tailor.** Structured master resume → tailored highlights + cover letter
  + drafted screening answers. Draft-only; no fabrication.
- **P4 — approval + submit.** Review queue (approval gate) → email / one-click
  package submission + receipts.
- **P5 — monitor.** Status lifecycle + inbox parsing + manual override +
  notifications.
- **P6 — serverless.** Port pure functions to Lambda (DynamoDbState), Step
  Functions orchestration, EventBridge schedule, S3 materials — same account
  `my2027`, ~$100/mo ceiling.

## Phase C — customer product (LATER)

- Remove personal-account LinkedIn; swap to a **licensed aggregator** connector
  (same `JobSource` interface).
- Multi-tenant: per-tenant profiles, materials, state, PII isolation, billing.
- ATS status APIs, assisted browser automation, full funnel dashboard,
  follow-up automation.

## First thing next session

P0 is done (Greenhouse + Lever). Next: either **live-verify** the two sources on
an open network (adjust mappings if the real schemas differ), or start **P1**
(own-account LinkedIn), or **P2** (extraction/matching over what's gathered).
Tests cover diff, taxonomy, fit, and both source mappings/filters.
