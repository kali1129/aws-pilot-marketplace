---
name: aws-account-status
description: Show a one-page overview of the AWS account — caller identity, account ID, organization, active regions, current month-to-date cost, top 5 spend categories, and any active billing alerts. Use at the start of any AWS session or when the user asks "what's in my AWS" or "show me my account".
---

# aws-account-status

Atomic skill: read-only account snapshot. Always safe to run.

## What it returns

1. **Identity** — `aws sts get-caller-identity` (account ID, ARN, user/role)
2. **Org context** — `aws organizations describe-organization` (master account, OUs) — skip if not in org
3. **Regions in use** — find regions with running EC2/Lambda/RDS/S3
4. **Cost MTD** — `aws ce get-cost-and-usage` for current month, grouped by SERVICE
5. **Active alarms** — `aws cloudwatch describe-alarms --state-value ALARM`
6. **Service health** — anything in trouble?

## Commands

```bash
# Identity
aws sts get-caller-identity --output json

# Cost MTD by service (use ce client, ce is only in us-east-1)
aws ce get-cost-and-usage \
  --time-period Start=$(date -u +%Y-%m-01),End=$(date -u +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --region us-east-1 \
  --output json

# Regions with running EC2
for r in $(aws ec2 describe-regions --query 'Regions[].RegionName' --output text); do
  count=$(aws ec2 describe-instances --region $r --filters Name=instance-state-name,Values=running --query 'length(Reservations[].Instances[])' --output text 2>/dev/null)
  [ "$count" != "0" ] && [ -n "$count" ] && echo "$r: $count running"
done

# Active CloudWatch alarms
aws cloudwatch describe-alarms --state-value ALARM --output json
```

## Output format

Render as a compact markdown table the user can read in 10 seconds:

```
Account: 123456789012  (kali1129)
Region:  us-east-1     (default)
MTD spend: $12.34      (budget: $50)

Top services this month:
  EC2     $8.20
  S3      $2.10
  Lambda  $1.04
  Route53 $0.50
  Other   $0.50

Active alarms: 0
```

## Constraints

- Pure read-only: never modify anything
- If credentials missing/invalid, halt and tell user to run `aws configure --profile <name>`
- If Cost Explorer API not enabled, mention it (it requires opt-in + 24h lag)
- Use the MCP server `aws_account_overview` tool when available (faster, cached, normalized output)
