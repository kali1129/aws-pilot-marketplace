#!/usr/bin/env bash
# aws-pilot PreToolUse hook: block AWS commands that would leave Free Tier.
# Honors AWS_PILOT_FREE_TIER_ONLY env var (default: true).
# Bypassed only if the user explicitly opts out via /plugin config.
set -euo pipefail

# Default ON — user must opt out via /plugin config aws-pilot free_tier_only=false
if [ "${AWS_PILOT_FREE_TIER_ONLY:-true}" = "false" ]; then
  exit 0
fi

HOOK_INPUT=$(cat || true)
export HOOK_INPUT

PY=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -z "$PY" ] && exit 0   # if no Python, fail-open (don't block — let MCP-side rules catch it)

"$PY" - <<'PYEOF'
import json, os, re, sys

raw = os.environ.get("HOOK_INPUT", "")
if not raw.strip():
    sys.exit(0)
try:
    payload = json.loads(raw)
except Exception:
    sys.exit(0)

cmd = (payload.get("tool_input") or {}).get("command", "")
if not isinstance(cmd, str) or not re.match(r'^\s*aws\b', cmd):
    sys.exit(0)

# Free Tier allowlist of EC2 instance types
FREE_TIER_INSTANCE = {"t2.micro", "t3.micro"}
# Services that are NOT free at all and almost always racking up charges
BLOCKED_SUBCMDS = {
    # service: [list of high-risk subcommands that auto-charge]
    "ec2": ["create-nat-gateway", "allocate-address"],   # EIP charges if unused
    "elasticloadbalancing": ["create-load-balancer", "create-target-group"],
    "rds": ["create-db-instance", "create-db-cluster"],
    "elasticache": ["create-cache-cluster"],
    "eks": ["create-cluster"],
    "fargate": ["*"],
    "ecs": ["create-cluster"],   # ECS itself is free but Fargate runs aren't
    "kms": ["create-key"],
    "secretsmanager": ["create-secret"],
    "shield": ["*"],
    "guardduty": ["create-detector"],
    "workspaces": ["*"],
    "directconnect": ["*"],
    "directoryservice": ["create-directory", "create-microsoft-ad"],
}

toks = re.split(r'\s+', cmd.strip())
if len(toks) < 3:
    sys.exit(0)

service = toks[1]
subcmd = toks[2]

# Block dangerous service subcommands
if service in BLOCKED_SUBCMDS:
    blocks = BLOCKED_SUBCMDS[service]
    if "*" in blocks or subcmd in blocks:
        print(f"""aws-pilot Free Tier guard: BLOCKED.

Command: {cmd}

The service '{service}' / subcommand '{subcmd}' is NOT in the AWS Free Tier
or has high charge risk. Letting this run could cost you real money.

To override (you accept the cost):
  /plugin config aws-pilot free_tier_only=false
  ...then retry your command.

Cheaper alternatives by service:
  rds          → SQLite locally, or DynamoDB (always-free 25GB)
  elasticache  → in-process cache, or DynamoDB
  eks/fargate  → Lambda (1M req/mo always free) or single EC2 t3.micro + Docker
  alb/nlb      → just open the EC2 port directly with a security group rule
  nat-gateway  → use public subnet + per-instance public IP (free) for hobby use
  secrets mgr  → SSM Parameter Store (Standard tier free)
  workspaces   → run a Linux EC2 + RDP (vastly cheaper)""", file=sys.stderr)
        sys.exit(2)

# Block run-instances with non-free instance types
if service == "ec2" and subcmd == "run-instances":
    m = re.search(r'--instance-type\s+(\S+)', cmd)
    if m:
        itype = m.group(1)
        if itype not in FREE_TIER_INSTANCE:
            print(f"""aws-pilot Free Tier guard: BLOCKED.

Command: {cmd}

Instance type '{itype}' is NOT Free Tier eligible. Allowed:
  • t2.micro  ($0.0116/hr — 750h/mo free for first 12 months)
  • t3.micro  ($0.0104/hr — 750h/mo free for first 12 months)

To use a larger type (you accept the cost):
  /plugin config aws-pilot free_tier_only=false
  ...then retry your command.""", file=sys.stderr)
            sys.exit(2)
    # Also check --block-device-mappings for >30 GB total EBS
    bdm = re.search(r'--block-device-mappings\s+(\'[^\']*\'|"[^"]*"|\S+)', cmd)
    if bdm:
        try:
            bdm_str = bdm.group(1).strip("'\"")
            for mapping in json.loads(bdm_str):
                vol_size = mapping.get("Ebs", {}).get("VolumeSize", 0)
                if vol_size > 30:
                    print(f"""aws-pilot Free Tier guard: EBS volume size {vol_size}GB > 30GB Free Tier limit.""",
                          file=sys.stderr)
                    sys.exit(2)
        except Exception:
            pass

# Allow everything else (read-only AWS calls, allowed creates)
sys.exit(0)
PYEOF
