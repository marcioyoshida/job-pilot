# Phase P6 — serverless deploy runbook (2026-08-16)

Run the daily batch (gather → extract → match → tailor) unattended on AWS. The
human review/approve/submit stays local (NFR-1) — the cloud job never submits.

**Status:** code complete + unit-tested offline. The CDK stack (`infra/app.py`)
was written against CDK v2 but **not** `cdk synth`'d in the build sandbox (no
creds/Docker there). Do the first synth/deploy on your machine and adjust if
your CDK version differs.

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
  (`python scripts/live_check.py` green).
- **Docker** running (PythonFunction bundles `requirements.txt`). No Docker?
  See "No-Docker" below.
- Node + CDK v2: `npm i -g aws-cdk` (or `npx cdk`).

## Deploy

```bash
python -m venv .venv-infra && source .venv-infra/bin/activate
pip install -r infra/requirements.txt

cd infra
cdk bootstrap aws://668449743071/us-east-1     # once per account/region
cdk synth                                       # verify it builds; fix any version drift
cdk deploy                                      # note the BucketName output
```

Then upload your config so the Lambda can read it:

```bash
BUCKET=<BucketName from the deploy output>
aws s3 cp config/search_profile.yaml s3://$BUCKET/config/search_profile.yaml
aws s3 cp config/candidate.yaml       s3://$BUCKET/config/candidate.yaml
```

Trigger a run now (instead of waiting for 07:00 UTC), then read the feed:

```bash
aws lambda invoke --function-name <JobPilot Pipeline fn name> /dev/stdout
aws s3 cp s3://$BUCKET/feed/latest.json -   # ranked results + material keys
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
Pull a run down and drive the same local flow:

```bash
aws s3 sync s3://$BUCKET/materials/ ./materials/
# review the feed, then use the local CLI (review/approve/submit) as usual
```

A DynamoDB-backed ApplicationStore + a small dashboard reading `feed/latest.json`
are the natural follow-ons if you want approve/submit in the cloud too.

## No-Docker alternative

If Docker isn't available for bundling, swap `PythonFunction` for
`aws_lambda.Function` with `code=lambda_.Code.from_asset("..")` plus a Lambda
layer containing PyYAML (boto3 is in the runtime). See the CDK docs for
`lambda.LayerVersion`.
