# infra

CDK → CloudFormation, matching the Signals/Onça deployment model.

- **Account:** `my2027` / `668449743071`, region `us-east-1`.
- **Cost ceiling:** ~$100/mo. No idle-floor services (no OpenSearch Serverless).
- **Not built yet** — see `app.py` for the intended stack. Phase P runs locally
  via `run.py` first (Phase P0–P5); the serverless port is Phase P6.

When building, reuse the Onça hardening lessons: hand-staged `build/lambda`,
sharded DynamoDB seen-set, per-source budgets, one daily EventBridge schedule
driving a Step Functions state machine.
