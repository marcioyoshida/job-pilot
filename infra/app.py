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

Deploy is done on a machine with real my2027 credentials — see
docs/2026-08-16-phase6-serverless.md.

Docker-free: the Lambda needs only stdlib + boto3 (both in the Python runtime),
because config is read from S3 as JSON, so a plain aws_lambda.Function with
Code.from_asset is enough — no bundling, no PythonFunction, no Docker.
"""
from __future__ import annotations

import os

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
REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class JobPilotStack(cdk.Stack):
    def __init__(self, scope: Construct, cid: str, **kw) -> None:
        super().__init__(scope, cid, **kw)

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

        fn = lambda_.Function(
            self, "Pipeline",
            runtime=lambda_.Runtime.PYTHON_3_11,
            handler="src.aws.handler.pipeline_handler",
            code=lambda_.Code.from_asset(REPO_ROOT, exclude=[
                ".git", ".git/**", ".venv", ".venv/**", ".venv-infra", ".venv-infra/**",
                "tests", "tests/**", "infra", "infra/**", "materials", "materials/**",
                "packages", "packages/**", "applications", "applications/**",
                "build", "build/**", "docs", "docs/**", "**/__pycache__", "**/__pycache__/**",
                "*.md", "config/*.yaml", ".jobpilot", ".jobpilot/**",
            ]),
            timeout=Duration.minutes(5),
            memory_size=512,
            environment={
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
            resources=[f"arn:aws:bedrock:{REGION}::foundation-model/*"],
        ))

        # once-daily schedule (07:00 UTC). Adjust to taste.
        events.Rule(
            self, "Daily",
            schedule=events.Schedule.cron(minute="0", hour="7"),
            targets=[targets.LambdaFunction(fn)],
        )

        cdk.CfnOutput(self, "BucketName", value=bucket.bucket_name)
        cdk.CfnOutput(self, "TableName", value=table.table_name)


app = cdk.App()
JobPilotStack(app, "JobPilot", env=cdk.Environment(account=ACCOUNT, region=REGION))
app.synth()
