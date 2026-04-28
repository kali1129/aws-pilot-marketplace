---
name: aws-cloudwatch-logs
description: Query and tail CloudWatch logs from any AWS service (Lambda, EC2, ECS, RDS). Use when user wants "show me Lambda logs", "tail my server logs", "find errors from yesterday", or "why did this fail?". Includes CloudWatch Insights queries.
---

# aws-cloudwatch-logs

Atomic skill: log retrieval + analysis. Read-only; never deletes log groups unless user confirms.

## List log groups

```bash
aws logs describe-log-groups --output json
aws logs describe-log-groups --log-group-name-prefix /aws/lambda/ --output json
```

## Tail logs (live, like `tail -f`)

```bash
# Lambda (most common)
aws logs tail /aws/lambda/my-function --follow --format short

# With filter (errors only)
aws logs tail /aws/lambda/my-function --follow --filter-pattern "ERROR"

# Time range
aws logs tail /aws/lambda/my-function --since 1h
aws logs tail /aws/lambda/my-function --since 2026-04-28T10:00:00Z --until 2026-04-28T11:00:00Z
```

## Search with CloudWatch Insights

```bash
# Save common query
QUERY='fields @timestamp, @message | filter @message like /ERROR/ | sort @timestamp desc | limit 100'
aws logs start-query \
  --log-group-name /aws/lambda/my-function \
  --start-time $(date -u -d '-1 hour' +%s) \
  --end-time $(date -u +%s) \
  --query-string "$QUERY"

# Get results (poll)
QID=<from-above>
aws logs get-query-results --query-id $QID
```

## Useful Insights queries

```sql
-- Top error messages last hour
fields @message
| filter @message like /ERROR/
| stats count(*) by @message
| sort count desc
| limit 20

-- Lambda duration p95 by function
filter @type = "REPORT"
| stats avg(@duration), pct(@duration, 95), max(@duration) by @log

-- VPC flow logs: top talkers
fields @timestamp, srcAddr, dstAddr, dstPort, action
| filter action = "REJECT"
| stats count(*) as denied by srcAddr
| sort denied desc

-- ALB access logs: 5xx by URL
fields @timestamp, request_url, elb_status_code
| filter elb_status_code >= 500
| stats count(*) by request_url
| sort count desc
```

## Set retention (avoid unbounded log costs)

```bash
# Check existing retention
aws logs describe-log-groups --query 'logGroups[].[logGroupName,retentionInDays]' --output table

# Set to 7 days (cheap default)
aws logs put-retention-policy \
  --log-group-name /aws/lambda/my-function \
  --retention-in-days 7
```

Common retention values: 1, 3, 5, 7, 14, 30, 60, 90, 365 days. CloudWatch Logs ingestion: $0.50/GB. Storage: $0.03/GB-mo. Without retention, costs grow forever.

## Constraints

- Read-only: never delete log groups or streams unless user confirms
- Default retention for new log groups: 7 days (set explicitly when create_function provisions one)
- Limit Insights queries to ≤24h time range and `limit 1000` to avoid runaway cost
- Surface long log groups (>1GB) and prompt user to set retention
