# Phase P6 — serverless deploy runbook (2026-08-16)

Run the daily batch (gather → extract → match → tailor) unattended on AWS. The
human review/approve/submit stays local (NFR-1) — the cloud job never submits.

**Status:** code complete + unit-tested, and the CDK stack **has been
`cdk synth`'d** (CDK 2.1136, aws-cdk-lib 2.x) — it produces valid CloudFormation
with a Docker-free Lambda asset (Handler `src.aws.handler.pipeline_handler`,
`bedrock:InvokeModel`, daily `cron(0 7 * * ? *)`, DynamoDB PAY_PER_REQUEST,
encrypted S3). Only `cdk deploy` remains, which needs your my2027 credentials.

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
- Node + CDK v2: `npm i -g aws-cdk` (or `npx cdk`).
- **No Docker needed** — the Lambda is a plain asset (stdlib + boto3 only).

## Deploy

```bash
python -m venv .venv-infra && source .venv-infra/bin/activate
pip install -r infra/requirements.txt

cd infra
cdk bootstrap aws://668449743071/us-east-1     # once per account/region
cdk synth                                       # already validated; sanity check
cdk deploy                                      # note the BucketName output
```

Then upload your config as JSON (the Lambda reads JSON so it needs no PyYAML):

```bash
python run.py export-config                      # writes build/cloud-config/*.json
BUCKET=<BucketName from the deploy output>
aws s3 cp build/cloud-config/search_profile.json s3://$BUCKET/config/
aws s3 cp build/cloud-config/candidate.json       s3://$BUCKET/config/
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
