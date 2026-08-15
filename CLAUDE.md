# CLAUDE.md — job-pilot

## What this project is

**job-pilot** — an assistive job-application pipeline that gathers job
postings for a target profile, extracts and normalizes their requirements,
matches them to the candidate's stack, tailors resume highlights + a cover
letter per posting, submits (with a human-approval gate), and monitors each
application's progress.

**Two audiences, two phases — do not conflate them:**

1. **Phase P (personal, CURRENT).** Sole user is the owner. Goal: fulfill the
   owner's own job search. LinkedIn is accessed via the owner's **own personal
   accounts** (see the LinkedIn rules below). Optimize for "works for one person
   this week," not multi-tenant.
2. **Phase C (customer product, LATER).** Multi-tenant SaaS for other job
   seekers. LinkedIn-by-personal-account is **removed** here and replaced by a
   **licensed aggregator** — you cannot operate customers' LinkedIn sessions on
   their behalf. Everything behind the source/connector interface swaps; the
   stage contracts stay the same.

This is a **separate product** from Onça / Signals-Competitor-Intelligence
(different audience, different domain). It deliberately **reuses that project's
build philosophy, AWS account, and cost constraint** so infra and habits carry
over.

## Reused from Signals / Onça (decided — don't relitigate)

- **AWS account:** alias `my2027`, account ID `668449743071`, CLI profile
  `my2027`. Region `us-east-1` for the prototype (broadest Bedrock coverage,
  cheapest).
- **AWS-native, serverless. No Databricks. No OpenSearch Serverless** (idle cost
  floor). Lambda + EventBridge schedule + Step Functions orchestration; DynamoDB
  for state; S3 for materials/artifacts; Bedrock for extraction + drafting.
- **IaC: CDK synthesizing to CloudFormation.**
- **Cost ceiling: ~$100/month.** Before adding any managed service, check its
  idle/floor cost.
- **Model tiering:** cheap models (Nova/Haiku) for extraction/classification,
  stronger models only for cover-letter synthesis; batch non-real-time jobs;
  prompt-cache the shared corpus (the master resume + taxonomy).
- **Conventions:** Python 3.11+, type hints, small pure fetch functions
  (Lambda-portable). State behind a narrow interface (`JsonState` local /
  `DynamoDbState` in Lambda). A diff engine surfaces only new-since-last-run.
- **Every generated output carries its sources** — no uncited claims. Each
  extracted requirement keeps the JD span it came from; each tailored resume
  bullet maps to a real master-resume item.

## LinkedIn rules (read before touching `src/ingest/linkedin.py`)

- **Phase P (own accounts):** automating even your **own** LinkedIn account
  violates LinkedIn's User Agreement (§8.2, no scraping/automated access) and
  risks **those accounts being restricted or banned**. Therefore:
  - Access is **session-based** with credentials **you** supply (never
    committed; env/secret only). Two accounts are supported via config.
  - **Human-paced** rate limits, jitter, and a hard daily cap. No parallel
    hammering. Treat it as fragile and isolate it behind `JobSource`.
  - LinkedIn is one source among many — prefer ATS/board APIs (Greenhouse,
    Lever, Ashby) which are ToS-clean and structured.
- **Phase C (customers):** **remove** personal-account access entirely; get
  LinkedIn breadth only through a **licensed aggregator** under its license.
  Never operate a customer's LinkedIn session.

## Hard product rules — NEVER

- **No fabrication.** Generated resumes/cover letters/screening answers must
  never claim experience, credentials, work authorization, or skills the
  candidate does not have. Every tailored bullet maps to a real master item.
- **No silent auto-submit.** A human-approval gate sits between tailoring
  (Stage 4) and submission (Stage 5). Bulk "approve reviewed" is fine; silent
  submission is not.
- **No login-gated scraping beyond the owner's own LinkedIn accounts in
  Phase P.** Other web fetch is logged-out and respects robots.txt.
- **No OpenSearch Serverless** (cost floor). No Databricks.
- **No estimated numbers (fit scores, comp) presented as sourced** without an
  explicit "estimated" label.
- **No invented API schemas** — verify against a live call first.

## Pipeline stages (contracts stable across phases)

1. **gather** (`src/ingest/`) — postings from sources → `Posting`
2. **extract** (`src/extract/`) — JD → `Requirements` (+ evidence spans)
3. **match** (`src/match/`) — normalize to canonical stack → `FitAnalysis`
4. **tailor** (`src/tailor/`) — `MaterialsVersion` (resume highlights + cover
   letter + drafted answers), draft-only
5. **submit** (`src/submit/`) — human-approved submission + receipt
6. **monitor** (`src/monitor/`) — status lifecycle + inbox parsing

See `docs/2026-08-15-job-pilot-requirements-spec.md` for the full spec and
`docs/2026-08-15-phase-plan.md` for status.
