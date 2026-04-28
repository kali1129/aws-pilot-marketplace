# aws-pilot MCP server

boto3-backed MCP server exposing tools that the `aws-pilot` Claude Code plugin uses.
Runs in two modes:

- **Local stdio** (default for development): plugin spawns `python3 server.py` as subprocess.
- **Remote HTTP** (for production VPS): containerized, behind a reverse proxy + bearer auth.

## Local dev (stdio)

The plugin's `.mcp.json` already wires this up. To test directly:

```bash
cd mcp
pip install -r requirements.txt
AWS_PROFILE=default AWS_PILOT_MODE=read-only python3 server.py
```

## VPS deploy (HTTP)

1. SSH into your VPS.
2. Install Docker + docker compose.
3. Copy this `mcp/` folder to the VPS.
4. Create `.env` from `.env.example`, set `AWS_PILOT_AUTH_TOKEN` to a long random string.
5. Mount your AWS creds at `~/.aws` (read-only) or use IAM role on the VPS.
6. Build + run:
   ```bash
   docker compose up -d --build
   ```
7. Reverse-proxy it (Caddy example):
   ```caddy
   mcp.yourdomain.com {
     reverse_proxy 127.0.0.1:8080
   }
   ```
8. In Claude Code:
   ```
   /plugin config aws-pilot mcp_remote_url=https://mcp.yourdomain.com
   /plugin config aws-pilot mcp_auth_token=<the-token-from-env>
   ```
9. The plugin will use the remote MCP instead of spawning local stdio.

## Tools exposed

| Tool                          | Mode required  | Description                                 |
|-------------------------------|----------------|---------------------------------------------|
| `aws_account_overview`        | any            | Identity, MTD cost, running resources       |
| `aws_list_resources`          | any            | List ec2/s3/lambda/rds/iam/route53/secrets/logs |
| `aws_create_ec2_with_ssh`     | execute        | Provision EC2 + SSH key + SG                |
| `aws_terminate_ec2`           | execute + confirm | DESTRUCTIVE — terminate instance         |
| `aws_audit_log_tail`          | any            | Last N audit log entries                    |

More tools can be added by following the pattern in `server.py`.

## Safety model

- Every tool checks `AWS_PILOT_MODE`. `read-only` blocks all writes; `dry-run` returns the plan without applying; `execute` actually runs.
- Every call appends to `AWS_PILOT_AUDIT_LOG` (JSONL).
- Destructive ops (`terminate`, `delete`, `drop`) require explicit `confirm=true` even in `execute` mode.
- IP allowlist on SSH security groups (caller's current public IP, never `0.0.0.0/0`).
- All created resources are tagged `ManagedBy=aws-pilot` so they're easy to find with `aws-cleanup-unused`.
