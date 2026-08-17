"""CDK app — job-pilot serverless batch (Phase P6). Synthesizes to CloudFormation.

Mirrors the Signals/Onça deployment model: AWS-native serverless, account my2027
(668449743071), us-east-1, no idle-floor services, ~$100/mo ceiling.

Provisions:
  - DynamoDB table (on-demand) for the new-since-last-run seen-set + kv
  - S3 bucket (encrypted) for config/ (search_profile.yaml, candidate.yaml),
    materials/, and feed/ outputs
  - a Python Lambda running src.aws.handler.pipeline_handler
  - an EventBridge rule firing it once daily
  - IAM: Bedrock InvokeModel, DynamoDB RW, S3 RW, and (optional) read of a
    Secrets Manager secret holding Gmail app-password creds

Lambda packaging follows Onça: a hand-staged `build/lambda` asset (src/ +
PyYAML manylinux wheel). No Docker. Run `scripts/stage_lambda.sh` before
synth/deploy. See docs/2026-08-16-phase6-serverless.md.
"""
from __future__ import annotations

import os
from pathlib import Path

import aws_cdk as cdk
from aws_cdk import (
    Duration,
    RemovalPolicy,
    aws_dynamodb as dynamodb,
    aws_events as events,
    aws_events_targets as targets,
    aws_iam as iam,
    aws_lambda as lambda_,
    aws_s3 as s3,
)
from constructs import Construct

ACCOUNT = "668449743071"   # my2027
REGION = "us-east-1"
BEDROCK_MODEL = os.environ.get("JOBPILOT_BEDROCK_MODEL", "amazon.nova-lite-v1:0")
REPO_ROOT = Path(__file__).resolve().parents[1]
LAMBDA_ASSET = REPO_ROOT / "build" / "lambda"


class JobPilotStack(cdk.Stack):
    def __init__(self, scope: Construct, cid: str, **kw) -> None:
        super().__init__(scope, cid, **kw)

        cdk.Tags.of(self).add("Application", "job-pilot")
        cdk.Tags.of(self).add("Environment", "personal")
        cdk.Tags.of(self).add("Phase", "P6")

        if not (LAMBDA_ASSET / "src" / "aws" / "handler.py").is_file():
            raise RuntimeError(
                f"Lambda asset missing at {LAMBDA_ASSET}. "
                "Run scripts/stage_lambda.sh before cdk synth/deploy."
            )

        table = dynamodb.Table(
            self, "State",
            partition_key=dynamodb.Attribute(name="pk", type=dynamodb.AttributeType.STRING),
            billing_mode=dynamodb.BillingMode.PAY_PER_REQUEST,   # no idle floor
            removal_policy=RemovalPolicy.DESTROY,
        )

        bucket = s3.Bucket(
            self, "Data",
            encryption=s3.BucketEncryption.S3_MANAGED,
            block_public_access=s3.BlockPublicAccess.BLOCK_ALL,
            removal_policy=RemovalPolicy.RETAIN,   # holds your materials/feed
        )

        # 15 min: Onça's ingest timed out at 5 min; first-run LLM per new
        # apply/stretch posting can add up even with a tight title filter.
        fn = lambda_.Function(
            self, "Pipeline",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="src.aws.handler.pipeline_handler",
            code=lambda_.Code.from_asset(str(LAMBDA_ASSET)),
            timeout=Duration.minutes(15),
            memory_size=1024,
            environment={
                "PYTHONPATH": "/var/task",
                "JOBPILOT_BUCKET": bucket.bucket_name,
                "JOBPILOT_TABLE": table.table_name,
                "JOBPILOT_USE_LLM": os.environ.get("JOBPILOT_USE_LLM", "true"),
                "JOBPILOT_BEDROCK_MODEL": BEDROCK_MODEL,
                # "JOBPILOT_GMAIL_SECRET_ARN": "<set if using LinkedIn alerts>",
            },
        )

        table.grant_read_write_data(fn)
        bucket.grant_read_write(fn)
        fn.add_to_role_policy(iam.PolicyStatement(
            actions=["bedrock:InvokeModel"],
            resources=[
                f"arn:aws:bedrock:{REGION}::foundation-model/{BEDROCK_MODEL}",
                f"arn:aws:bedrock:{REGION}::foundation-model/*",
            ],
        ))

        # once-daily schedule (07:00 UTC). Adjust to taste.
        events.Rule(
            self, "Daily",
            schedule=events.Schedule.cron(minute="0", hour="7"),
            targets=[targets.LambdaFunction(fn)],
        )

        cdk.CfnOutput(self, "BucketName", value=bucket.bucket_name)
        cdk.CfnOutput(self, "TableName", value=table.table_name)
        cdk.CfnOutput(self, "FunctionName", value=fn.function_name)


app = cdk.App()
JobPilotStack(app, "JobPilot", env=cdk.Environment(account=ACCOUNT, region=REGION))
app.synth()
