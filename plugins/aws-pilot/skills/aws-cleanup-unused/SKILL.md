---
name: aws-cleanup-unused
description: Find and optionally remove unused AWS resources eating money — stopped EC2 with attached EBS, unused EIPs, old snapshots, idle ALBs, empty buckets, abandoned NAT Gateways. Use monthly to control costs. Read-only by default; deletes require explicit confirmation per resource.
---

# aws-cleanup-unused

Atomic skill: cost cleanup. Lists candidates; deletions require user OK each.

## Common money-wasters

| Resource                    | Why expensive             | Detection                                              |
|-----------------------------|---------------------------|--------------------------------------------------------|
| Unattached EBS volume       | $0.08–0.10/GB-mo          | `describe-volumes --filters Name=status,Values=available` |
| Stopped EC2 with EBS        | EBS still charged         | `describe-instances` state=stopped + check volumes     |
| Old EBS snapshots           | $0.05/GB-mo               | `describe-snapshots --owner-ids self` older than 90d   |
| Unused Elastic IP           | $0.005/hr ≈ $3.65/mo each | `describe-addresses` w/o AssociationId                 |
| Idle NAT Gateway            | $32.40/mo each            | `describe-nat-gateways` + check VPC traffic            |
| Idle ALB/NLB                | $16/mo each               | `describe-load-balancers` w/o targets                  |
| Old AMIs + their snapshots  | snapshot cost             | `describe-images --owners self` not used by any LC     |
| Empty S3 buckets            | $0.005/1k req but mostly free | `list-buckets` then check object count             |
| Abandoned RDS snapshots     | $0.095/GB-mo              | `describe-db-snapshots` for deleted DBs                |
| CloudWatch log groups       | $0.03/GB-mo, no retention | `describe-log-groups` retentionInDays=null + size      |

## Find candidates (read-only audit)

```bash
# Unattached volumes
aws ec2 describe-volumes \
  --filters Name=status,Values=available \
  --query 'Volumes[].[VolumeId,Size,VolumeType,CreateTime]' --output table

# EIPs without association
aws ec2 describe-addresses \
  --query 'Addresses[?!AssociationId].[PublicIp,AllocationId]' --output table

# Snapshots older than 90 days
aws ec2 describe-snapshots --owner-ids self \
  --query "Snapshots[?StartTime<='$(date -u -d '-90 days' --iso-8601=seconds)'].[SnapshotId,VolumeSize,StartTime,Description]" \
  --output table

# Idle ALBs (no targets registered)
for ARN in $(aws elbv2 describe-load-balancers --query 'LoadBalancers[].LoadBalancerArn' --output text); do
  TARGETS=$(aws elbv2 describe-target-groups --load-balancer-arn $ARN --query 'TargetGroups[].TargetGroupArn' --output text)
  for TG in $TARGETS; do
    HEALTHY=$(aws elbv2 describe-target-health --target-group-arn $TG --query 'length(TargetHealthDescriptions[?TargetHealth.State==`healthy`])' --output text)
    [ "$HEALTHY" = "0" ] && echo "Idle ALB: $ARN (TG: $TG)"
  done
done

# Log groups without retention
aws logs describe-log-groups \
  --query 'logGroups[?!retentionInDays].[logGroupName,storedBytes]' \
  --output table
```

## Cleanup workflow

1. Run audit, group findings by potential monthly savings
2. Show user a table sorted by $$$:
   ```
   Resource                           Monthly cost   Action
   nat-0abc123 (us-east-1a)           $32.40         Delete? (no traffic last 30d)
   eip 3.4.5.6 (unattached)           $3.65          Release? (unattached 14d)
   vol-0xyz789 (50GB gp3)             $4.00          Delete? (detached 21d)
   ─────────────────────────────────  ─────────
   Total identified savings           $40.05/mo
   ```
3. For each, ask: "delete this? y/n/skip"
4. After deletes, log to audit log

## Constraints

- NEVER auto-delete. Always per-resource confirmation.
- Skip resources tagged `DoNotDelete=true` or `Persistent=true`
- For snapshots, check if any AMI references them before deleting
- For EBS, last-detach time must be >7 days (avoid deleting yesterday's troubleshooting)
- Print a "savings achieved" summary at the end
- Tag findings as `aws-pilot-audit-2026-04-28` so users can re-find them
