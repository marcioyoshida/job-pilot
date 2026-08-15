"""CDK app skeleton (Phase P6) — synthesizes to CloudFormation.

Mirrors the Signals/Onça infra choices: AWS-native serverless, account `my2027`
(668449743071), us-east-1, no idle-floor services, ~$100/mo ceiling.

Not deployable yet — this is the seam. When Phase P6 starts, define:
  - one Lambda per JobSource + extract/match/tailor/submit/monitor
  - a Step Functions state machine:
      Gather -> Extract -> Match -> Tailor -> [approval wait] -> Submit -> Monitor
  - DynamoDB table for application state (DynamoDbState, sharded seen-set)
  - S3 bucket for MaterialsVersions (encrypted; lifecycle)
  - EventBridge daily schedule
  - Static S3 + CloudFront review-queue/funnel dashboard (reads feed.json)
  - Secrets Manager for LinkedIn creds + aggregator/API keys (never in code)
"""
from __future__ import annotations

ACCOUNT = "668449743071"   # my2027
REGION = "us-east-1"
COST_CEILING_USD_MONTH = 100

# import aws_cdk as cdk
#
# app = cdk.App()
# JobPilotStack(app, "JobPilot", env=cdk.Environment(account=ACCOUNT, region=REGION))
# app.synth()
