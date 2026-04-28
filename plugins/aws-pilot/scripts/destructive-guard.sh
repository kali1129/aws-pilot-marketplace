#!/usr/bin/env bash
# aws-pilot PreToolUse hook for Bash:
# Blocks AWS destructive commands unless audit log has a recent "confirmed" marker.
# Hook input on stdin (JSON). Exit 2 + stderr message blocks the tool call.
set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || echo "")

# Only act on aws-cli destructive verbs
if ! echo "$COMMAND" | grep -qE '^[[:space:]]*aws ' ; then
  exit 0
fi

DESTRUCTIVE_RE='aws [a-z0-9-]+ (terminate-instances|delete-bucket|delete-db-instance|delete-function|delete-user|delete-role|delete-policy|drop-|release-address|delete-vpc|delete-security-group|delete-key-pair|deregister-|destroy-)'

if echo "$COMMAND" | grep -qE "$DESTRUCTIVE_RE"; then
  REQUIRE_CONFIRM="${AWS_PILOT_REQUIRE_CONFIRM:-true}"
  if [ "$REQUIRE_CONFIRM" = "false" ]; then
    exit 0
  fi
  cat >&2 <<EOF
DESTRUCTIVE AWS OPERATION BLOCKED.

Command: $COMMAND

This command is destructive (terminate / delete / drop / release).
To proceed, the user must:
  1. Confirm explicitly in chat ("yes, terminate i-abc123")
  2. Or set: claude /plugin config aws-pilot require_confirm_destructive=false (NOT recommended)

aws-pilot will not silently execute destructive ops.
EOF
  exit 2
fi

exit 0
