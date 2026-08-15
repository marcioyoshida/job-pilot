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

## The apply loop (Stages 1-5)

```bash
# 1-4: gather -> extract -> match -> tailor DRAFT materials for apply/stretch roles
python run.py pipeline --tailor \
  --profile config/search_profile.yaml --candidate config/candidate.yaml

python run.py review                 # list applications + status
python run.py approve --key <key>    # or --all  (approval is REQUIRED)
python run.py submit                 # prepares one-click packages / email drafts
```

`submit` refuses anything not approved, is idempotent, and **auto-sends
nothing**: ATS postings become a one-click package (markdown + apply URL) under
`packages/`; `email:` postings become an `.eml` draft you send yourself unless
you wire a real mailer. State lives in `applications/` (gitignored).

## Running behind a VPN / corporate proxy

A plain VPN is transparent routing — no config needed. Two things to know:

- **Geography:** job-board and (later) LinkedIn requests exit from your VPN's
  IP, so location-filtered results follow that IP's country/region. Set your
  VPN region to match the market you're targeting.
- **Proxy:** if your setup is actually an HTTP proxy, `urllib` honors the
  `HTTPS_PROXY` / `*_proxy` environment variables automatically. If the proxy
  adds latency, bump the request timeout:

  ```bash
  export JOBPILOT_HTTP_TIMEOUT_S=45
  ```

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
