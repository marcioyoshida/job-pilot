# job-pilot — requirements spec (2026-08-15)

Status: **Draft for review.** Requirements, not an implementation plan.

Separate product from Signals/Onça, reusing its build (AWS account `my2027` /
`668449743071`, `us-east-1`; AWS-native serverless; CDK→CFN; ~$100/mo ceiling;
Python 3.11+; diff engine; narrow state interface; source-cited outputs).

## 0. Two phases (do not conflate)

- **Phase P — personal (current).** One user (the owner). LinkedIn accessed via
  the owner's **own personal accounts** (session-based, human-paced — see
  CON-1). Optimize for a working single-user tool.
- **Phase C — customer product (later).** Multi-tenant SaaS. Personal-account
  LinkedIn access is **removed**; LinkedIn breadth comes only from a **licensed
  aggregator** (CON-1). Stage contracts below are identical across phases; only
  the source connectors and tenancy change.

Design rule: everything LinkedIn-specific sits behind the `JobSource` interface
(`src/ingest/base.py`) so Phase C swaps the connector without touching
stages 2–6.

---

## 1. Goal

Given a candidate profile, find relevant postings, extract + normalize their
requirements, match them to the candidate's stack, produce **tailored** resume
highlights + a cover letter per posting, submit (with a human-approval gate),
and track each application's status over time.

Non-goal: a fully autonomous mass-applier. Default posture is
**human-approves-before-submit** (NFR-1).

---

## 2. Stages (the six requested capabilities)

### Stage 1 — Gather  (`src/ingest/`)
- **FR-1.1** Ingest from configurable sources behind one `JobSource` interface.
  MVP sources, lowest legal/maintenance risk first:
  1. ATS/board APIs — Greenhouse, Lever, Ashby (ToS-clean, structured).
  2. **Phase P only:** the owner's **own LinkedIn accounts** (2), session-based
     — see CON-1. **Phase C:** a **licensed aggregator** replaces this.
  3. Company career pages — logged-out, robots.txt-respecting.
- **FR-1.2** A **SearchProfile** drives gathering: titles/keywords, seniority,
  location(s) + remote policy, industry, company size, comp band, languages,
  exclude terms/companies, recency window. LinkedIn saved-search **filters** are
  expressed here too, per account.
- **FR-1.3** Dedupe across sources + across the two LinkedIn accounts via a
  stable key (normalized company + title + location + JD hash).
- **FR-1.4** Persist raw posting + normalized fields + source URL + first/last
  seen. Every downstream claim traces to the source URL.
- **FR-1.5** Diff: surface only **new** postings since the last run
  (`src/diff/engine.py`, mirrors the Onça diff engine).

### Stage 2 — Extract requirements  (`src/extract/`)
- **FR-2.1** From each JD, extract a structured `Requirements`:
  `must_have_skills[]`, `nice_to_have_skills[]`, `years_experience`,
  `education`, `certifications[]`, `responsibilities[]`, `domain`, `location`,
  `remote_policy`, `work_authorization`, `languages[]`, `comp`, `seniority`,
  `application_method` (ATS + apply URL / email), `screening_questions[]`.
- **FR-2.2** LLM-assisted but **no invented fields**; unstated = `null`. Keep
  the JD span/quote each requirement came from (evidence).
- **FR-2.3** Classify each requirement **hard** (disqualifying, e.g. work
  authorization) vs **soft**; feeds Stage 3.

### Stage 3 — Stack match  (`src/match/`)
- **FR-3.1** Normalize posting skills to a **canonical taxonomy**
  (`src/match/taxonomy.py`): synonym map + families (language / framework /
  cloud / data / infra / tooling).
- **FR-3.2** Normalize the candidate's stack the same way; compute a
  **fit_score** (`src/match/fit.py`): must-have coverage, nice-to-have coverage,
  gaps; a missing **hard** requirement caps the score.
- **FR-3.3** Surface the **closest-matching stack** the candidate has and the
  **gap list** (skills wanted but missing/under-evidenced) — drives Stage 4.
- **FR-3.4** Emit `FitAnalysis`: `fit_score`, `matched_skills[]`, `gaps[]`,
  `recommendation` (apply / stretch / skip), each with evidence. `fit_score` is
  **estimated** and labeled as such (house rule).

### Stage 4 — Tailor  (`src/tailor/`)
- **FR-4.1** Input: candidate **master resume** (superset) + `Requirements` +
  `FitAnalysis`.
- **FR-4.2** **Tailored resume highlights** — select/re-order/rephrase master
  bullets to foreground what the posting values, **without fabricating**. Every
  tailored bullet maps to a real master item (CON-4).
- **FR-4.3** **Cover letter** — company/role-specific, 2–3 concrete matched
  strengths, honest about key gaps; configurable tone/length.
- **FR-4.4** Draft answers to **screening questions** truthfully from the
  profile; flag ones needing manual input (salary, visa).
- **FR-4.5** All Stage-4 output is a **draft `MaterialsVersion` pending human
  approval** (NFR-1).

### Stage 5 — Submit  (`src/submit/`)
- **FR-5.1** After per-application approval, submit via `application_method`:
  ATS application API (preferred) → email (mail integration) → web form without
  API: **generate a filled, one-click package for the human to finish**
  (default, lowest ToS/CAPTCHA risk); assisted browser automation is opt-in and
  watched. Unattended automation against platforms that forbid it is out of
  scope (CON-3).
- **FR-5.2** Idempotent — never submit the same application twice; record a
  receipt (timestamp, method, confirmation id/screenshot, materials version).
- **FR-5.3** Respect per-source rate limits + etiquette; human-plausible volume.
- **FR-5.4** Store exactly which `MaterialsVersion` went to whom.

### Stage 6 — Monitor  (`src/monitor/`)
- **FR-6.1** Status lifecycle: `discovered → drafted → approved → submitted →
  acknowledged → screening → interview → offer → rejected → withdrawn/expired`.
- **FR-6.2** Signals: ATS status APIs; **inbox parsing** of
  confirmation/rejection/interview email mapped to the application; manual
  override.
- **FR-6.3** Surface a funnel + per-application timeline + action queue
  (approve draft, reply to recruiter, schedule interview) + stale follow-up
  reminders.
- **FR-6.4** Notify/digest on key transitions (interview, rejection, offer) via
  EventBridge→SNS / email (reuse the Onça digest pattern).

---

## 3. Data model

`SearchProfile` (per LinkedIn account + global) · `CandidateProfile` (master
resume, normalized skills, prefs, PII) · `Posting` · `Requirements` (+ evidence)
· `FitAnalysis` · `MaterialsVersion` (immutable once submitted) · `Application`
(Posting + MaterialsVersion + status + receipt + status-event history).

---

## 4. Architecture (reuses the house stack)

AWS-native serverless: Lambda `JobSource` fetchers, EventBridge schedule, Step
Functions `Gather → Extract → Match → Tailor → [human-approval wait] → Submit →
Monitor`, DynamoDB application state, S3 materials, Bedrock extraction/tailoring
(cheap model for extract/classify, stronger only for cover letters; batch;
prompt-cache master resume + taxonomy). Review queue + funnel as a static
S3+CloudFront dashboard reading an aggregated `feed.json` (mirrors the Onça
Phase-3 dashboard). CDK→CFN. Stays under ~$100/mo (no idle-floor services).

Phase P may run stages locally via `run.py` (JsonState) before Lambda; Phase C
requires the full serverless multi-tenant deploy.

---

## 5. Non-functional

- **NFR-1** Human-in-the-loop approval gate between Stage 4 and 5. No silent
  auto-submit.
- **NFR-2** Truthfulness — no fabricated experience/skills/answers (CON-4).
- **NFR-3** Traceability — every extracted requirement links to a JD span;
  every tailored bullet to a real master item.
- **NFR-4** Privacy/PII — resume PII encrypted at rest, least privilege,
  retention + easy deletion; send only what a given application needs. Phase C:
  per-tenant isolation.
- **NFR-5** Cost — model tiering + batch; keep the ~$100/mo ceiling.
- **NFR-6** Auditability — immutable log of what was submitted, where, when.
- **NFR-7** Rate-limit/etiquette compliance per source (esp. LinkedIn, CON-1).

---

## 6. Legal & platform constraints

- **CON-1 LinkedIn.** Phase P automates the **owner's own** accounts:
  session-based, credentials supplied at runtime (never committed), human-paced
  with jitter + hard daily cap, isolated behind `JobSource`. This still violates
  LinkedIn's User Agreement and risks **those accounts** — accepted, personal,
  eyes-open. Phase C **removes** this and uses a **licensed aggregator** only.
- **CON-2** Non-LinkedIn web fetch is logged-out + robots.txt-respecting.
- **CON-3** Auto-apply/anti-bot — prefer application APIs and the one-click
  package; no unattended form automation where forbidden.
- **CON-4** No fabrication (hard rule).
- **CON-5** Honest identity — the owner applies as themselves; the tool assists.
- **CON-6** Aggregator/data used within license terms.

---

## 7. MVP cut (Phase P) vs later (Phase C)

- **Phase P MVP:** Stages 1–4 for Greenhouse + Lever + the owner's 2 LinkedIn
  accounts; human-approval queue; email/one-click submission; Stage-6 status via
  inbox parsing + manual override. Runnable via `run.py` locally, then Lambda.
- **Phase C later:** multi-tenant deploy, licensed-aggregator LinkedIn, ATS
  status APIs, assisted browser automation, richer fit modeling, full funnel
  dashboard, follow-up automation, billing.

---

## 8. Open decisions

- **OPEN-1** Master-resume format — structured (JSON/YAML) vs parsed PDF/DOCX.
  Structured is far more reliable for tailoring. (Recommend structured master +
  optional PDF export.)
- **OPEN-2** LinkedIn access mechanics for own accounts — official (very
  limited) vs session automation library; which respects the daily cap best.
- **OPEN-3** Submission posture — one-click package (safest) vs assisted browser
  automation, and how far toward automation for Phase P.
- **OPEN-4** Screening-question auto-answer scope (salary/visa/demographic —
  default: always defer to user).
- **OPEN-5** Applications-per-day cap (etiquette + LinkedIn safety).
- **OPEN-6** Local-first (`run.py`) vs straight-to-Lambda for Phase P.

---

## 9. Acceptance criteria (Phase P MVP)

1. Given a SearchProfile, returns deduped, new-since-last-run postings from ≥2
   sources (incl. the 2 LinkedIn accounts), each with a source URL.
2. Emits a `Requirements` object per posting with per-field evidence and no
   invented fields.
3. Emits a `FitAnalysis` (score labeled estimated, matched, gaps,
   recommendation) tied to the candidate's normalized stack.
4. Emits tailored resume highlights + cover letter where **every** bullet maps
   to a real master item, plus drafted screening answers with unanswerable ones
   flagged.
5. No application submitted without explicit approval; each submission records
   an immutable receipt + exact `MaterialsVersion`.
6. Application status tracked through §2.6 lifecycle, updated from ≥ inbox
   parsing + manual override, with notifications on key transitions.
