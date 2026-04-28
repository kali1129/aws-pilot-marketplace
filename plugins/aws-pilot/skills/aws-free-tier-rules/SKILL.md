---
name: aws-free-tier-rules
description: Rules of what aws-pilot is allowed to provision when free_tier_only=true (default). Read this BEFORE provisioning ANY AWS resource. Tells you what's free, what charges, and what to use instead. Always invoke as a sanity check before run-instances, create-bucket, create-function, etc.
---

# Free Tier Rules — what aws-pilot will and won't provision

`free_tier_only` is **on by default**. The hook `free-tier-guard.sh` blocks
any `aws` CLI command that would leave the Free Tier. The MCP server reads
the same flag from `AWS_PILOT_FREE_TIER_ONLY` env var.

## Allowed (free if you stay under limits)

| Service          | Free Tier limit                      | Notes |
|------------------|---------------------------------------|-------|
| **EC2**          | t2.micro / t3.micro, 750h/mo, 30GB EBS gp2/gp3, 100GB out | First 12 months only. After that pay $7.60/mo per instance. |
| **S3**           | 5 GB storage, 20K GET, 2K PUT, 100GB out | First 12 months. After that ~$0.023/GB/mo. |
| **Lambda**       | 1M requests/mo, 400k GB-seconds/mo   | **Always free** (no expiration). Best for APIs / jobs. |
| **CloudFront**   | 50 GB out, 2M requests / mo          | **Always free**. Use for static-site CDN. |
| **DynamoDB**     | 25 GB storage, 25 RCU + 25 WCU       | **Always free**. Use instead of RDS for hobby DBs. |
| **CloudWatch**   | 10 metrics, 10 alarms, 5GB logs      | **Always free**. |
| **SNS / SQS**    | 1M msgs/mo (publishes/requests)      | **Always free**. |
| **IAM**          | All operations                        | **Always free**. |
| **Route53**      | $0.50/mo per hosted zone (~free-ish) | NOT actually free. Allowed because it's cheap. |
| **SSM Parameter Store** | Standard tier                  | **Always free**. Use INSTEAD of Secrets Manager. |

## BLOCKED by default (real money)

| Service                | Cost                               | Use instead                       |
|------------------------|-------------------------------------|-----------------------------------|
| **EC2 t3.small+**      | $15-60+/mo                         | t3.micro                          |
| **EC2 Elastic IPs unattached** | $3.65/mo each              | Release when unused               |
| **NAT Gateway**        | $32.40/mo + $0.045/GB              | Run instance in public subnet     |
| **ALB / NLB / ELB**    | $16-22/mo each                     | Direct EC2 SG ingress (port 80/443) |
| **RDS**                | $11+/mo (12mo free, then real)     | DynamoDB / SQLite local           |
| **ElastiCache**        | $11+/mo (no free tier)             | In-process cache or DynamoDB     |
| **EKS**                | $72/mo control plane               | Lambda or single EC2 + Docker     |
| **Fargate**            | $0.04/hr per task                  | Lambda or EC2                     |
| **Secrets Manager**    | $0.40/mo + $0.05/10k API           | SSM Parameter Store (free)        |
| **GuardDuty**          | trial only                         | CloudTrail (free)                 |
| **Direct Connect**     | $216+/mo                           | VPN over public internet         |
| **WorkSpaces**         | $25-75/mo per user                 | EC2 + RDP                         |
| **Customer-managed KMS keys** | $1/mo each                  | AWS-managed keys (free)           |

## How to override (only when you accept the cost)

```
/plugin config aws-pilot free_tier_only=false
```

This re-enables paid services. The hook stops blocking. **Recommend setting
back to true after the one paid op:**

```
/plugin config aws-pilot free_tier_only=true
```

## Pre-provisioning mental checklist

Before running ANY `aws ... create-* / run-* / put-*` command:

1. Is the service in the "Allowed" table above?  → OK
2. Is it in "Blocked"?  → Refuse, suggest the alternative
3. For EC2 specifically: instance-type ∈ {t2.micro, t3.micro}? EBS ≤ 30GB?
4. For S3: bucket policy doesn't enable Requester Pays accidentally
5. For Route53: warn user it's $0.50/mo per zone

## Cost runaway alarms (set up once)

The plugin's `aws_health_check` warns when:
- MTD spend > 80% of `monthly_budget_usd` (default $5)
- Stale access keys >90 days
- Unattached EIPs

Run it weekly: `/aws-health`.
