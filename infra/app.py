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
docs/2026-08-16-phase6-serverless.md. This file was written against the CDK v2
API but has NOT been `cdk synth`'d in this sandbox (no creds/Docker here);
run `cdk synth` first and adjust if your CDK version differs.

NOTE: PythonFunction (aws-lambda-python-alpha) bundles requirements.txt and needs
Docker available at synth/deploy time. If Docker isn't available, swap to a
plain aws_lambda.Function with a prebuilt layer (see the runbook).
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
from aws_cdk.aws_lambda_python_alpha import PythonFunction
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

        fn = PythonFunction(
            self, "Pipeline",
            entry=REPO_ROOT,                       # bundles requirements.txt
            index="src/aws/handler.py",
            handler="pipeline_handler",
            runtime=lambda_.Runtime.PYTHON_3_11,
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
