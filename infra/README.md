# infra

CDK → CloudFormation, matching the Signals/Onça deployment model.

- **Account:** `my2027` / `668449743071`, region `us-east-1`.
- **Cost ceiling:** ~$100/mo. No idle-floor services (no OpenSearch Serverless).
- **Stack:** `infra/app.py` — DynamoDB (on-demand), S3, Lambda, daily EventBridge.
- **Lambda asset:** hand-staged `build/lambda` (no Docker). Run
  `scripts/stage_lambda.sh` before `cdk synth` / `cdk deploy`.

See `docs/2026-08-16-phase6-serverless.md` for the deploy runbook.
