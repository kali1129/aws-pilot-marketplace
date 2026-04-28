# aws-pilot

Claude Code plugin that lets Claude drive an AWS account end-to-end. Built for users who want to leverage AWS but don't know it.

## What it does

- **Provision a VPS in one command**: `/aws-deploy-vps mybox web example.com` → EC2 + SSH key + security group + DNS + TLS cert. SSH command printed at the end.
- **Manage everything else**: S3 buckets, Lambda functions, RDS databases, IAM users/roles, Route53 DNS, Secrets Manager, CloudWatch logs, VPC networking.
- **Watch your money**: `/aws-cost` shows MTD spend + EOM forecast + spend spikes. `/aws-cleanup` finds wasted resources.
- **Stay safe**: read-only or dry-run by default. Destructive ops blocked unless you confirm. Full audit log of every change.

## Components

| Type    | Count | Examples                                                                  |
|---------|-------|---------------------------------------------------------------------------|
| Skills  | 14    | aws-ec2-manage, aws-deploy-vps, aws-s3-manage, aws-iam-manage, aws-rds-manage |
| Agents  | 3     | aws-quick-info (haiku), aws-task-executor (sonnet), aws-architect (opus)  |
| Commands| 4     | /aws-status, /aws-cost, /aws-deploy-vps, /aws-cleanup                     |
| MCP     | 1     | aws-pilot-mcp (boto3, stdio + HTTP modes, Docker for VPS)                 |
| Hooks   | 3     | SessionStart status, PreToolUse destructive-guard, PostToolUse audit      |

## First-time setup

1. **Install AWS CLI** — https://aws.amazon.com/cli/
2. **Get access keys** — AWS Console → IAM → Users → your user → Security credentials → Create access key (pick "CLI" use case)
3. **Configure profile**:
   ```bash
   aws configure --profile aws-pilot
   # paste keys, set region (us-east-1 is fine), output=json
   ```
4. **Install plugin**:
   ```bash
   claude plugin marketplace add kali1129/aws-pilot-marketplace
   claude plugin install aws-pilot@aws-pilot-marketplace
   ```
5. **Configure plugin**:
   ```
   /plugin config aws-pilot aws_profile=aws-pilot
   /plugin config aws-pilot mode=dry-run             # change to "execute" when ready
   /plugin config aws-pilot monthly_budget_usd=20    # your cap
   ```
6. **Test**: ask Claude "/aws-status" — should show your account info.

## Modes

| Mode         | What it does                                                              |
|--------------|---------------------------------------------------------------------------|
| `read-only`  | Blocks ALL writes. Use for first-time exploration of the account.        |
| `dry-run`    | Plans every change but doesn't apply. Use for designing infra safely.    |
| `execute`    | Actually applies changes. Destructive ops still need confirmation.       |

Default is `dry-run` so accidents are impossible until you opt in.

## Cost guardrails

- Every provisioning skill computes monthly cost estimate before launching.
- Refuses to create resources whose monthly cost exceeds (`monthly_budget_usd` − current MTD).
- `/aws-cost` shows trend + forecast.
- `/aws-cleanup` finds wasted spend (idle EIPs, unattached EBS, etc).

## VPS deployment of the MCP server

For production / team use, the MCP server can run on a remote VPS (Docker). See [mcp/README.md](./mcp/README.md) for the full guide. TL;DR:

```bash
# On VPS
docker compose up -d --build

# In Claude Code
/plugin config aws-pilot mcp_remote_url=https://mcp.your-vps.com
/plugin config aws-pilot mcp_auth_token=<bearer-token>
```

## License

MIT.
