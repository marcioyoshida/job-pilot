# Phase P6 — serverless deploy runbook (2026-08-16)

Run the daily batch (gather → extract → match → tailor) unattended on AWS. The
human review/approve/submit stays local (NFR-1) — the cloud job never submits.

**Status:** deployed 2026-08-16 on my2027 / us-east-1 (`JobPilot` stack CREATE_COMPLETE).
Packaging follows the Onça hand-staged `build/lambda` asset (no Docker).

Live outputs:

| Output | Value |
|---|---|
| BucketName | `jobpilot-data666c94c7-6lsreryeo6va` |
| FunctionName | `JobPilot-PipelineC660917D-UHtbd6BvciXz` |
| TableName | `JobPilot-State1C20CC9A-1WIENF8AVFA7D` |

First invoke (`2026-08-17T012347Z`) gathered 7 new GitLab/Coinbase postings; all
were `skip` so no drafts were written (NFR-1 still holds — the job never submits).

## What gets deployed (fits CLAUDE.md: AWS-native, CFN, ~$100/mo, no idle floor)

- **DynamoDB** table (on-demand) — new-since-last-run seen-set + kv
  (`src/state/store.py:DynamoDbState`).
- **S3** bucket — `config/` (your two YAMLs), `materials/<run>/…json` drafts,
  `feed/<run>.json` + `feed/latest.json`.
- **Lambda** `src.aws.handler.pipeline_handler` — the batch core
  (`run_pipeline`, unit-tested).
- **EventBridge** rule — fires it once daily (07:00 UTC by default).
- **IAM** — Bedrock `InvokeModel`, DynamoDB RW, S3 RW, optional Secrets read.

## Cost (prototype ceiling ~$100/mo)

DynamoDB on-demand + Lambda (a few invocations/day) + S3 (tiny) ≈ cents/month at
idle. The only real variable is Bedrock nova-lite per posting, which is cheap and
bounded by how many new postings appear daily. No idle-floor services.

## One-time prerequisites

- Real credentials for **my2027** (`668449743071`), region **us-east-1**
  (`AWS_PROFILE=my2027 python scripts/live_check.py` green).
- Node + CDK v2: `npm i -g aws-cdk` (or `npx cdk`).
- Account already bootstrapped (`CDKToolkit` in us-east-1).

No Docker. The Lambda zip is assembled by `scripts/stage_lambda.sh` (rsync
`src/` + a manylinux/CPython 3.11 PyYAML wheel). boto3 is in the Lambda
runtime.

## Deploy

```bash
python -m venv .venv-infra && source .venv-infra/bin/activate
pip install -r infra/requirements.txt

scripts/stage_lambda.sh                 # rebuilds build/lambda

cd infra
export AWS_PROFILE=my2027 AWS_DEFAULT_REGION=us-east-1
cdk synth                               # verify it builds
cdk deploy                              # note BucketName / FunctionName outputs
```

Then upload your config so the Lambda can read it:

```bash
BUCKET=<BucketName from the deploy output>
aws s3 cp config/search_profile.yaml s3://$BUCKET/config/search_profile.yaml
aws s3 cp config/candidate.yaml       s3://$BUCKET/config/candidate.yaml
```

`run.py export-config` can emit JSON copies under `build/cloud-config/` if you
want them; the live handler reads the YAML keys above.

Trigger a run now (instead of waiting for 07:00 UTC), then read the feed:

```bash
aws lambda invoke --function-name <FunctionName> /tmp/jobpilot-invoke.json
cat /tmp/jobpilot-invoke.json
aws s3 cp s3://$BUCKET/feed/latest.json -
```

## Optional: LinkedIn alerts in the cloud

Store Gmail app-password creds in Secrets Manager and point the Lambda at them:

```bash
aws secretsmanager create-secret --name job-pilot/gmail \
  --secret-string '{"GMAIL_ADDRESS":"you@gmail.com","GMAIL_APP_PASSWORD":"xxxx"}'
```

Set `JOBPILOT_GMAIL_SECRET_ARN` in the Lambda env (uncomment in `infra/app.py`)
and grant read (`secret.grant_read(fn)`), then redeploy.

## Reviewing / applying

The cloud job produces ranked drafts in S3; **approval + submission stay local**.
Pull a run down and drive the same local CLI:

```bash
aws s3 sync s3://$BUCKET/materials/ ./materials/
# review the feed, then use the local CLI (review/approve/submit) as usual
```

A DynamoDB-backed ApplicationStore + a small dashboard reading `feed/latest.json`
are the natural follow-ons if you want approve/submit in the cloud too.

## Notes

- `new_postings` marks keys seen **before** extract/tailor. A timed-out run
  will not resurface those keys. Timeout is 15 minutes (Onça's 5-min lesson).
- Rebuild the asset after any `src/` change: `scripts/stage_lambda.sh && cd infra && cdk deploy`.
