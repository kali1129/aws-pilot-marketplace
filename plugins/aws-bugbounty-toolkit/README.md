# aws-bb-toolkit

Claude Code plugin for offensive AWS recon during **authorized** bug bounty engagements whose scope explicitly includes AWS infrastructure.

## What it does

Read-only enumeration of AWS resources from a set of credentials you found via legitimate BB methods (leaked in source code, IMDS via SSRF, env vars, etc.). Maps the principal's permissions, finds privesc paths, drafts a report.

## Scope of use — read this

This toolkit is **read-only by design**. Hooks block any AWS write API call. It is for:

- BB programs that explicitly include AWS infra in scope (Microsoft, AWS Marketplace, certain enterprise programs)
- Authorized penetration tests with signed scope documents
- CTF / lab environments

It is **not** for:

- Random AWS accounts you don't have written authorization to test
- Pivoting outside program scope after finding cross-account access
- Modifying or destroying anything in a target account (toolkit blocks this anyway)

## Components

| Type    | Count | Examples                                                                  |
|---------|-------|---------------------------------------------------------------------------|
| Skills  | 7     | aws-iam-enum, aws-s3-recon, aws-secrets-hunt, aws-lambda-recon, aws-ec2-imds-abuse, aws-cred-validator, aws-cloudtrail-pivot |
| Agents  | 3     | aws-bb-recon-runner (haiku), aws-bb-finding-analyst (sonnet), aws-bb-chain-strategist (opus) |
| Hooks   | 4     | scope-check, throttle, readonly-guard, log-finding                        |

## Setup

1. Install AWS CLI + clone https://github.com/andresriancho/enumerate-iam (some skills shell out to it)
2. Install plugin:
   ```bash
   claude plugin marketplace add kali1129/aws-pilot-marketplace
   claude plugin install aws-bb-toolkit@aws-pilot-marketplace
   ```
3. Build a scope file (one ARN/account/CIDR per line):
   ```
   123456789012
   arn:aws:s3:::target-prod-*
   arn:aws:lambda:us-east-1:123456789012:function:*
   ```
4. Configure:
   ```
   /plugin config aws-bb-toolkit scope_file=/path/to/scope.txt
   /plugin config aws-bb-toolkit aws_profile=target-program-creds
   /plugin config aws-bb-toolkit throttle_seconds=3
   /plugin config aws-bb-toolkit max_calls_per_session=200
   ```

## Workflow

```
1. Land creds (SSRF → IMDS, source code, env var, etc.)
2. /agents run aws-bb-recon-runner  → fast read-only enumeration
3. /agents run aws-bb-finding-analyst  → severity + report sections
4. /agents run aws-bb-chain-strategist (if low/medium individually) → chain path
5. Submit
```

## Safety

- `readonly-guard.sh` PreToolUse hook **blocks** any write verb in `aws ...` commands
- `throttle.sh` enforces minimum delay between API calls (avoid CloudTrail anomaly alerts)
- `scope-check.sh` SessionStart hook reminds you which scope file is active
- Findings logged to JSONL for later report generation

## License

MIT. Use ethically.
