---
name: aws-cred-validator
description: Verify a set of AWS credentials (access key + secret + optional session token) are valid, identify the principal, and map effective permissions. Use immediately after finding credentials in source code, IMDS, env vars, or git history. Read-only.
---

# aws-cred-validator

Atomic skill: validate creds + map permissions. Read-only.

## Inputs

- `AWS_ACCESS_KEY_ID` (AKIA... = long-term, ASIA... = STS session)
- `AWS_SECRET_ACCESS_KEY`
- `AWS_SESSION_TOKEN` (only for ASIA keys)

## Steps

```bash
# Step 1: are they valid?
AWS_ACCESS_KEY_ID=$AK AWS_SECRET_ACCESS_KEY=$SK AWS_SESSION_TOKEN=$ST \
  aws sts get-caller-identity --output json

# Step 2: what kind of principal?
# - arn:aws:iam::123:user/foo → IAM user
# - arn:aws:sts::123:assumed-role/role-name/session → assumed role
# - arn:aws:iam::123:root → root keys (CRITICAL)
# - arn:aws:sts::123:federated-user/x → federated

# Step 3: enumerate-iam.py for permission mapping
git clone https://github.com/andresriancho/enumerate-iam
cd enumerate-iam
python3 enumerate-iam.py \
  --access-key $AK --secret-key $SK \
  ${ST:+--session-token $ST}

# Step 4: are they expired? Check ASIA keys
aws sts decode-authorization-message ...  # if you got an error message
```

## Severity grid

| Principal type           | Permission breadth   | Severity   |
|--------------------------|----------------------|------------|
| Root keys                | any                  | Critical   |
| IAM user with `*` policy | `*:*`                | Critical   |
| IAM user — service-wide  | `s3:*` on `*`        | High       |
| IAM user — scoped        | `s3:GetObject` on 1B | Medium     |
| Read-only / metadata     | iam:Get* / s3:List*  | Low        |
| Expired session token    | n/a                  | Info       |

## Output

```json
{"ts":"...","skill":"aws-cred-validator","ak_prefix":"AKIA...XYZ","valid":true,"principal":"arn:aws:iam::123:user/web-deployer","key_age_days":347,"permissions_count":42,"interesting":["secretsmanager:GetSecretValue","iam:CreateAccessKey"],"severity":"High"}
```

## Constraints

- NEVER share full secret/session token in chat output — show first 4 + length only
- After validation, switch to `aws-iam-enum` for deeper permission mapping
- If creds are root, halt and notify user — never enumerate further with root
- Log the source of the creds (git commit hash, IMDS URL, env var path)
