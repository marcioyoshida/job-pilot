# Getting started (Phase P, local)

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt

# configure your search
cp config/search_profile.example.yaml config/search_profile.yaml
$EDITOR config/search_profile.yaml

# run tests (diff, taxonomy, fit are already real)
pytest -q

# see the CLI shape (no sources wired until Phase P0/P1)
python run.py gather --profile config/search_profile.yaml
```

## Secrets — never commit

LinkedIn credentials and API keys come from the environment or a secret store:

```bash
export LINKEDIN_ACCT1_USER=...   # matches linkedin_accounts[].label "acct1"
export LINKEDIN_ACCT1_PASS=...
export LINKEDIN_ACCT2_USER=...
export LINKEDIN_ACCT2_PASS=...
```

`.gitignore` already excludes `.env`, `config/search_profile.yaml`, `.jobpilot/`,
and any candidate data/materials.

## What's implemented vs stubbed

- **Real:** data types (`src/ingest/base.py`), state (`src/state/store.py`
  JsonState), diff engine, taxonomy, fit scoring, and their tests.
- **Stubbed seams (raise NotImplementedError with the phase they belong to):**
  every source connector, extraction, tailoring, submission, monitoring, and the
  CDK stack. Follow `docs/2026-08-15-phase-plan.md`.

## Rules you can't skip

- No fabrication in generated materials (CON-4).
- No submit without explicit approval (NFR-1).
- LinkedIn = your own accounts only in Phase P, human-paced (CON-1).
