---
name: aws-cloudtrail-pivot
description: Analyze CloudTrail logs (when readable) to find privilege escalation paths, recent admin actions, IPs/principals doing sensitive ops, and stale credentials. Use after IAM enum confirmed CloudTrail read access. Read-only.
---

# aws-cloudtrail-pivot

Atomic skill: read CloudTrail to find privesc opportunities and admin patterns. Read-only.

## Pre-flight

- Confirm `cloudtrail:LookupEvents` or S3 bucket read access for the trail
- Identify trail's S3 bucket: `aws cloudtrail list-trails && aws cloudtrail describe-trails`

## Commands

```bash
# List trails
aws cloudtrail describe-trails --output json

# Lookup recent events (90-day default)
aws cloudtrail lookup-events \
  --lookup-attributes AttributeKey=EventName,AttributeValue=ConsoleLogin \
  --max-results 50

# Useful filters
aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=AssumeRole
aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=CreateAccessKey
aws cloudtrail lookup-events --lookup-attributes AttributeKey=EventName,AttributeValue=PutUserPolicy
aws cloudtrail lookup-events --lookup-attributes AttributeKey=Username,AttributeValue=admin

# If you have S3 read on trail bucket: download + parse with jq
aws s3 cp s3://my-trail-bucket/AWSLogs/123/CloudTrail/us-east-1/2026/04/28/ . --recursive
gunzip *.gz
cat *.json | jq -r '.Records[] | select(.eventName=="CreateAccessKey")'
```

## What to flag

- **Unused IAM users** — last login >90 days but key still active → stale cred risk
- **Failed login attempts** — bursts from one IP → credential stuffing in progress
- **AssumeRole patterns** — find which roles get assumed by whom (privesc graph)
- **CreateAccessKey events** — track who's adding keys to whom
- **PutUserPolicy / AttachUserPolicy** — privesc events
- **DisableLogging / StopLogging / DeleteTrail** — anti-forensics, immediate Critical
- **GetCallerIdentity from Tor exit node** — recon by attacker

## Output

```json
{"ts":"...","skill":"aws-cloudtrail-pivot","trails":["arn:..."],"recent_admin_actions":42,"stale_users":["bob","alice"],"suspicious_ips":["1.2.3.4"],"anti_forensics":false}
```

## Constraints

- Read-only: never call `cloudtrail:Stop*/Delete*/Update*/Put*`
- If logs reveal user PII, redact in output
- 90-day API window is a hard limit; for older, must read S3 directly
- Sampling: don't pull entire trail, focus on event names of interest
