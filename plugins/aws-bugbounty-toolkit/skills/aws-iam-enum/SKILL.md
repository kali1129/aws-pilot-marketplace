---
name: aws-iam-enum
description: Enumerate AWS IAM users, roles, groups, policies, and access keys with stealth pacing for authorized bug bounty programs. Use when you have leaked AWS credentials in scope and want to map the principal's permissions and find privesc paths. Read-only.
---

# aws-iam-enum

Atomic skill: enumerate IAM via boto3/aws-cli. Read-only.

## Pre-flight (mandatory)

1. Verify program scope explicitly includes AWS infra (read the configured scope_file path (set via /plugin config aws-bb-toolkit scope_file=...)).
2. Confirm the credentials profile is the program's leaked/authorized creds, not your personal AWS.
3. Throttle to the configured throttle_seconds (default 3) between calls (default 3s).

## Commands

```bash
# Identity first — never skip
aws sts get-caller-identity --profile $AWS_PROFILE

# enumerate-iam.py is the canonical tool: it brute-forces every iam:List*/Get* call
# https://github.com/andresriancho/enumerate-iam
python3 enumerate-iam.py --access-key AKIA... --secret-key ... --session-token ...

# Manual (one-by-one with throttle)
aws iam list-users --profile $AWS_PROFILE
aws iam list-roles --profile $AWS_PROFILE
aws iam list-groups --profile $AWS_PROFILE
aws iam list-policies --scope Local --profile $AWS_PROFILE
aws iam list-access-keys --user-name <user> --profile $AWS_PROFILE

# Per-user: attached + inline policies
aws iam list-attached-user-policies --user-name <u>
aws iam list-user-policies --user-name <u>
aws iam get-user-policy --user-name <u> --policy-name <p>

# Per-role: trust policy + attached policies
aws iam get-role --role-name <r>
aws iam list-attached-role-policies --role-name <r>
aws iam list-role-policies --role-name <r>
```

## Privesc paths to flag

- `iam:CreateAccessKey` on any user → key takeover
- `iam:UpdateAssumeRolePolicy` → trust policy hijack
- `iam:PassRole` + `lambda:CreateFunction` → execute as role
- `iam:PassRole` + `ec2:RunInstances` with InstanceProfile → EC2 takeover
- `sts:AssumeRole` on overly permissive role
- Wildcard `*` in policy Action or Resource
- `iam:PutUserPolicy` / `iam:AttachUserPolicy` → self-privesc
- `iam:CreatePolicyVersion` + `iam:SetDefaultPolicyVersion` → policy hijack

## Output

Save findings to the configured findings_log path as JSONL:
```json
{"ts":"2026-04-28T...","skill":"aws-iam-enum","principal":"arn:aws:iam::123:user/x","permissions":["iam:*"],"privesc_paths":["CreateAccessKey on AdminUser"]}
```

## Constraints

- NEVER call any iam:Create*/Update*/Delete*/Put* — read-only only
- If you hit `AccessDenied`, log and move on — do not retry
- Stop at the configured max_calls_per_session (default 200)
- If response includes IPs/account IDs of the program owner, redact in chat output
