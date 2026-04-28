---
name: aws-secrets-hunt
description: Enumerate AWS Secrets Manager and SSM Parameter Store entries in an authorized scope. Use when leaked creds have secretsmanager:* or ssm:* permissions and you want to map what secrets exist (names + last-rotated, NOT values unless scope allows). Read-only.
---

# aws-secrets-hunt

Atomic skill: list and describe secrets without exfiltrating values. Read-only.

## Pre-flight

- Confirm the program scope explicitly allows reading Secrets Manager values (most do NOT — names only is the safe default)
- Default behavior: list names + metadata, NEVER call `get-secret-value` unless user confirms scope allows it

## Commands

```bash
# Secrets Manager — list (names only)
aws secretsmanager list-secrets --profile $AWS_PROFILE --output json

# Per secret: describe metadata, NOT value
aws secretsmanager describe-secret --secret-id <arn>

# SSM Parameter Store — list (names only)
aws ssm describe-parameters --profile $AWS_PROFILE --output json

# Per parameter: get without decryption (still gets the value but as ciphertext for SecureString)
aws ssm get-parameter --name <p> --with-decryption=false

# DO NOT RUN unless scope allows:
# aws secretsmanager get-secret-value --secret-id <arn>
# aws ssm get-parameter --name <p> --with-decryption=true
```

## What to flag

- Secret names hinting at production prod creds (`db-password-prod`, `stripe-live-key`)
- Wide IAM permission to `secretsmanager:GetSecretValue` on `Resource: "*"`
- SSM SecureString without KMS rotation
- Parameters with hardcoded secrets in plaintext (`String` type instead of `SecureString`)

## Severity guide

- Names + metadata only → Low/Info
- Read value of one prod secret → High/Critical (depending on contents)
- Cross-account secret access via resource policy → High

## Output

```json
{"ts":"...","skill":"aws-secrets-hunt","secret_count":42,"high_value_names":["prod-db-master","stripe-live-restricted"],"value_read":false}
```

## Constraints

- DEFAULT: never call `get-secret-value` or `get-parameter --with-decryption`
- If user/scope explicitly allows reading values, log every value read in findings.jsonl
- Redact actual secret values in chat output (show first 4 chars + length)
