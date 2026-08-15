# job-pilot

Assistive job-application pipeline: **gather → extract → stack-match → tailor →
submit → monitor**. Personal-first (the owner's own job search), designed to
evolve into a multi-tenant customer product.

Built on the same foundations as the Signals/Onça project: AWS-native
serverless, AWS account `my2027` (`668449743071`, `us-east-1`), CDK→CFN,
Python 3.11+, ~$100/mo cost ceiling, diff-engine + narrow state interface, and
"every output carries its sources."

## Status

Scaffold + requirements spec. See:
- `docs/2026-08-15-job-pilot-requirements-spec.md` — full requirements
- `docs/2026-08-15-phase-plan.md` — phases and what's next
- `CLAUDE.md` — project charter and hard rules

## The six stages

| Stage | Module | Output |
|---|---|---|
| Gather | `src/ingest/` | `Posting` (deduped, new-since-last-run) |
| Extract | `src/extract/` | `Requirements` (+ JD evidence spans) |
| Match | `src/match/` | `FitAnalysis` (score, matched, gaps) |
| Tailor | `src/tailor/` | `MaterialsVersion` (draft, human-approved) |
| Submit | `src/submit/` | submission receipt (after approval) |
| Monitor | `src/monitor/` | status lifecycle + notifications |

## Important rules (see CLAUDE.md)

- **No fabrication** in generated materials; every bullet maps to real
  experience.
- **No silent auto-submit** — a human approves before anything is sent.
- **LinkedIn** in the personal phase uses the owner's own accounts, session-based
  and human-paced (this violates LinkedIn's ToS and risks those accounts — see
  CLAUDE.md); the customer phase swaps to a **licensed aggregator**.

## Local dev

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
cp config/search_profile.example.yaml config/search_profile.yaml   # then edit
python run.py --help
pytest -q
```

Secrets (LinkedIn credentials, API keys) go in the environment / a secret store,
**never** in the repo. See `.gitignore`.
