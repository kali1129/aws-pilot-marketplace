---
name: aws-lambda-recon
description: Enumerate AWS Lambda functions in an authorized scope — list functions, extract environment variables (often contain secrets), download code for review, map function URLs and triggers. Use for bug bounty AWS targets. Read-only.
---

# aws-lambda-recon

Atomic skill: Lambda enumeration. Read-only.

## Pre-flight

- Verify program scope includes Lambda
- Throttle 3s between calls

## Commands

```bash
# List all functions across regions
for r in $(aws ec2 describe-regions --query 'Regions[].RegionName' --output text); do
  aws lambda list-functions --region $r --profile $AWS_PROFILE --output json
done

# Per function: full config + env vars
F=my-function
aws lambda get-function --function-name $F --output json

# Function URL (publicly invokable?)
aws lambda get-function-url-config --function-name $F

# Resource-based policy (cross-account invoke?)
aws lambda get-policy --function-name $F

# Triggers (event sources)
aws lambda list-event-source-mappings --function-name $F

# Download code (returns S3 presigned URL)
aws lambda get-function --function-name $F --query 'Code.Location' --output text | xargs curl -o function.zip
unzip -l function.zip
```

## What to look for

- **Env vars with secrets**: `DB_PASSWORD`, `API_KEY`, `STRIPE_KEY`, `JWT_SECRET` in Configuration.Environment.Variables
- **Function URL** with `AuthType: NONE` → publicly invokable
- **Resource policy** with `Principal: "*"` → cross-account invoke
- **IAM execution role** over-privileged (e.g., `s3:*` when only one bucket needed)
- **Hardcoded secrets** in function code (after unzip)
- **Outdated runtimes** (nodejs12, python3.6) — not a vuln but reportable as info
- **Layer code** — also worth downloading: `aws lambda list-layer-versions`

## Output

```json
{"ts":"...","skill":"aws-lambda-recon","function":"prod-api","env_secrets":["JWT_SECRET","DB_PASS"],"public_url":true,"role":"arn:..."}
```

## Constraints

- NEVER call `aws lambda invoke` unless scope explicitly allows it (write op semantically)
- NEVER `update-function-code` / `delete-function` / `add-permission`
- If function code contains user PII, redact before sharing
- Lambda code download is safe (read of own/scoped function code)
