#!/usr/bin/env bash
# aws-pilot PreToolUse: block AWS destructive verbs (terminate / delete / drop / cancel /
# revoke / deregister) unless explicitly disabled via require_confirm_destructive=false.
# Hook input on stdin; exit 2 + stderr message blocks the tool call.
set -euo pipefail

HOOK_INPUT=$(cat || true)
export HOOK_INPUT

PY=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done

# Fallback: simple grep-based check if Python missing.
if [ -z "$PY" ]; then
  CMD=$(printf '%s' "$HOOK_INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"command"[[:space:]]*:[[:space:]]*"\(.*\)"/\1/' || true)
  if echo "$CMD" | grep -qE '^[[:space:]]*aws ' && \
     echo "$CMD" | grep -qE '\b(terminate-instances|delete-bucket|delete-db-instance|delete-function|delete-user|delete-role|delete-policy|delete-secret|delete-stack|delete-cluster|delete-table|delete-log-group|delete-vpc|delete-security-group|delete-key-pair|deregister-task-definition|deregister-instance|cancel-spot-instance-requests|release-address|destroy-)\b'; then
    if [ "${AWS_PILOT_REQUIRE_CONFIRM:-true}" = "false" ]; then exit 0; fi
    echo "DESTRUCTIVE AWS OPERATION BLOCKED: $CMD" >&2
    exit 2
  fi
  exit 0
fi

# Python path: parses stdin and applies a precise regex (only blocks on the verb token).
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
if not isinstance(cmd, str):
    sys.exit(0)

# Only act on aws CLI invocations
if not re.match(r'^\s*aws\b', cmd):
    sys.exit(0)

# Tokenize and find the verb (3rd or 4th token usually: `aws <service> <verb>` or `aws <service> <subcommand> <verb>`)
toks = re.split(r'\s+', cmd.strip())
# verbs that are unambiguously destructive when they appear as the action token
DESTRUCTIVE = {
    "terminate-instances", "delete-bucket", "delete-db-instance",
    "delete-function", "delete-user", "delete-role", "delete-policy",
    "delete-secret", "delete-stack", "delete-cluster", "delete-table",
    "delete-log-group", "delete-vpc", "delete-security-group",
    "delete-key-pair", "delete-load-balancer", "delete-target-group",
    "delete-cache-cluster", "delete-distribution", "delete-hosted-zone",
    "deregister-task-definition", "deregister-instance",
    "cancel-spot-instance-requests", "release-address",
    "rb",  # `aws s3 rb` removes a bucket
    "rm",  # `aws s3 rm` deletes objects (only when target starts with s3://)
}

# Look for any token that is in DESTRUCTIVE
hit = None
for t in toks[1:]:  # skip the leading "aws"
    if t in DESTRUCTIVE:
        # special case: `aws s3 rm` is destructive only if a path follows starting with s3://
        if t == "rm" and not any(x.startswith("s3://") for x in toks):
            continue
        hit = t
        break

if hit is None:
    sys.exit(0)

require_confirm = os.environ.get("AWS_PILOT_REQUIRE_CONFIRM", "true").lower()
if require_confirm == "false":
    sys.exit(0)

print(f"""DESTRUCTIVE AWS OPERATION BLOCKED.

Command: {cmd}

Verb: '{hit}' is destructive (deletes / terminates / cancels resources).
To proceed:
  1. Confirm explicitly in chat ("yes, terminate i-abc123") and let Claude retry, OR
  2. Set: claude /plugin config aws-pilot require_confirm_destructive=false (NOT recommended)

aws-pilot will not silently execute destructive ops.""", file=sys.stderr)
sys.exit(2)
PYEOF
