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

P0 + P2 + P3 are done — gather→extract→match→tailor runs offline end-to-end.
Next: **P4 — approval + submit** (review queue over the DRAFT materials, then
email / one-click-package submission with idempotent receipts), or **P1 —
own-account LinkedIn**, or the **LLM upgrade** (BedrockExtractor +
LLM cover-letter prose). Tests cover diff, taxonomy, fit, both source
mappings/filters, heuristic extraction, tailoring/provenance, and the offline
end-to-end chain.
