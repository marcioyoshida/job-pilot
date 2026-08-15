# job-pilot — phase plan (2026-08-15)

Mirrors the Signals/Onça phase-doc style. Status is **scaffold only** — the
`src/` tree defines interfaces + a few working pure functions (diff, taxonomy,
fit). External I/O (LinkedIn, ATS APIs, Bedrock, email) is stubbed with clear
`NotImplementedError` seams.

## Phase P — personal (CURRENT)

Goal: a working single-user tool for the owner's own job search.

- **P0 — spine (next).** `SearchProfile` config + `JobSource` interface + diff
  engine + `JsonState`. Wire `run.py` to gather from **one ATS source**
  (Greenhouse or Lever — ToS-clean) end-to-end into deduped, new-only postings.
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

Implement P0: make `python run.py gather` pull from one ATS source into
new-only postings using `src/diff/engine.py` + `JsonState`, with a
`config/search_profile.yaml`. Tests already cover diff, taxonomy, and fit.
