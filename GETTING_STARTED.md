# Getting started (Phase P, local)

### Set up the environment (venv + pip)

```bash
python -m venv .venv
source .venv/bin/activate            # Windows: .venv\Scripts\activate
pip install -r requirements.txt -r requirements-dev.txt

pytest -q                            # run the tests
python run.py gather --profile config/search_profile.yaml
```

Activate the venv (`source .venv/bin/activate`) in each new shell before running
the commands below, or prefix them with `.venv/bin/`.

### Configure your search

```bash
cp config/search_profile.example.yaml config/search_profile.yaml && $EDITOR config/search_profile.yaml
```

For the candidate profile, import your resume instead of hand-writing YAML:

```bash
python run.py import-resume --file ~/resume.pdf --llm    # .pdf/.docx/.txt/.md
$EDITOR config/candidate.yaml                            # review the result
```

`--llm` structures it with Bedrock (recommended); without it, an offline
heuristic is used. It never invents experience — bullets come from your resume.
Or start from the example: `cp config/candidate.example.yaml config/candidate.yaml`.

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

# optional: also pull LinkedIn jobs from your saved-search ALERT emails
#   set up: LinkedIn → Jobs → save a search → turn alerts on (do this per account)
python run.py pipeline --tailor --linkedin-gmail \
  --profile config/search_profile.yaml --candidate config/candidate.yaml
#   or from an exported JSON of alert emails:
# python run.py pipeline --tailor --linkedin-inbox alerts.json ...

python run.py review                 # list applications + status
python run.py approve --key <key>    # or --all  (approval is REQUIRED)
python run.py submit                 # prepares one-click packages / email drafts
```

`submit` refuses anything not approved, is idempotent, and **auto-sends
nothing**: ATS postings become a one-click package (markdown + apply URL) under
`packages/`; `email:` postings become an `.eml` draft you send yourself unless
you wire a real mailer. State lives in `applications/` (gitignored).

### 6: monitor progress

```bash
# from a JSON export of messages ([{subject, body, from, date, id}, ...])
python run.py monitor --inbox inbox.json

# or read recent Gmail over IMAP (create an app password at myaccount.google.com)
export GMAIL_ADDRESS=you@gmail.com GMAIL_APP_PASSWORD=xxxx
python run.py monitor --gmail

python run.py status --key <key> --set interview     # manual override
```

`monitor` classifies each email (acknowledged/screening/interview/offer/
rejected), matches it to an application (a company signal is required — it won't
guess), advances the status **forward-only**, and notifies on interview/offer/
rejection. Every change is logged to the record's history.

## Optional: the LLM path (Bedrock)

The pipeline runs fully on the offline heuristic. To use Bedrock (Amazon Nova
Lite by default) for richer extraction + a written cover letter:

```bash
# needs real AWS creds for account my2027 (668449743071), region us-east-1,
# with Bedrock model access enabled for the model id below
export JOBPILOT_BEDROCK_MODEL=amazon.nova-lite-v1:0   # optional override
python run.py pipeline --tailor --llm \
  --profile config/search_profile.yaml --candidate config/candidate.yaml
```

If AWS creds/network aren't available, `--llm` prints a notice and falls back to
the heuristic. Live-verify the whole AWS + Bedrock path once on your machine:

```bash
python scripts/live_check.py            # STS identity + a tiny Bedrock Converse call
```

Guardrail: the LLM extractor keeps a skill only if the model returns a verbatim
JD quote for it that actually appears in the posting — hallucinated skills are
dropped. The cover letter is grounded in your real profile facts, and the
human-approval gate is still the backstop.

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
