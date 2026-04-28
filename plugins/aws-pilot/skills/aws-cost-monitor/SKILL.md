---
name: aws-cost-monitor
description: Show current month-to-date AWS cost, top services by spend, forecast end-of-month total, set up budget alerts, and find unexpected spikes. Use when the user asks "how much am I spending" or "set a budget alert".
---

# aws-cost-monitor

Atomic skill: cost visibility + budget alerts. Read by default; alert creation requires `mode: execute`.

## Read commands (always safe)

```bash
# MTD cost grouped by service
aws ce get-cost-and-usage \
  --time-period Start=$(date -u +%Y-%m-01),End=$(date -u +%Y-%m-%d) \
  --granularity MONTHLY \
  --metrics UnblendedCost \
  --group-by Type=DIMENSION,Key=SERVICE \
  --region us-east-1

# Forecast end-of-month
aws ce get-cost-forecast \
  --time-period Start=$(date -u +%Y-%m-%d),End=$(date -u -d "$(date -u +%Y-%m-01) +1 month -1 day" +%Y-%m-%d) \
  --metric UNBLENDED_COST \
  --granularity MONTHLY \
  --region us-east-1

# Find spikes — daily granularity for last 14 days
aws ce get-cost-and-usage \
  --time-period Start=$(date -u -d "-14 days" +%Y-%m-%d),End=$(date -u +%Y-%m-%d) \
  --granularity DAILY \
  --metrics UnblendedCost \
  --region us-east-1

# Existing budgets
aws budgets describe-budgets --account-id $(aws sts get-caller-identity --query Account --output text)
```

## Write commands (require mode=execute + confirmation)

```bash
# Create a $50/mo budget with email alert at 80%
ACCT=$(aws sts get-caller-identity --query Account --output text)
cat > /tmp/budget.json <<EOF
{
  "BudgetName": "monthly-cap-${user_config.monthly_budget_usd}",
  "BudgetLimit": {"Amount": "${user_config.monthly_budget_usd}", "Unit": "USD"},
  "TimeUnit": "MONTHLY",
  "BudgetType": "COST"
}
EOF
cat > /tmp/notif.json <<EOF
[{
  "Notification": {"NotificationType":"ACTUAL","ComparisonOperator":"GREATER_THAN","Threshold":80,"ThresholdType":"PERCENTAGE"},
  "Subscribers": [{"SubscriptionType":"EMAIL","Address":"YOUR_EMAIL_HERE"}]
}]
EOF
aws budgets create-budget --account-id $ACCT --budget file:///tmp/budget.json --notifications-with-subscribers file:///tmp/notif.json
```

## Output

A clean monthly summary:

```
Month-to-date: $14.32  (budget: $50)
Forecast EOM:  $42.10  (84% of budget — on track but watch)

Top services:
  EC2          $9.21
  S3           $2.30
  Route53      $0.55
  CloudWatch   $0.84
  Lambda       $0.02
  Other        $1.40

Spike alert: EC2 jumped from $0.30/day to $1.10/day on 2026-04-25
  → most likely cause: t3.medium left running. Want to /aws-stop-all?
```

## Constraints

- Cost Explorer API has a 24-hour lag and small per-call fee ($0.01/call). Cache results in `${CLAUDE_PLUGIN_DATA}/cost-cache.json` for 1 hour.
- Refuse to provision any resource whose estimated monthly cost exceeds remaining budget headroom
- All `ce` calls go to `us-east-1` regardless of default region
