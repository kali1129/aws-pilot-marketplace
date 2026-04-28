#!/usr/bin/env bash
# aws-bb-toolkit PreToolUse: block any aws CLI write operation outright.
# BB toolkit is strictly read-only; protects against accidental tampering with target.
set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || echo "")

if ! echo "$COMMAND" | grep -qE '^[[:space:]]*aws ' ; then
  exit 0
fi

# Allow read verbs only
WRITE_RE='aws [a-z0-9-]+ (create-|update-|put-|delete-|attach-|detach-|terminate-|start-|stop-|run-|invoke|modify-|restore-|add-|remove-|enable-|disable-|reboot-|release-|associate-|disassociate-|authorize-|revoke-|set-|register-|deregister-|tag-resources|untag-)'

if echo "$COMMAND" | grep -qE "$WRITE_RE"; then
  cat >&2 <<EOF
aws-bb-toolkit: WRITE OPERATION BLOCKED.

Command: $COMMAND

This toolkit is read-only by design. Modifying the target's AWS account is out
of scope for any legitimate bug bounty engagement. If you actually need to
provision/modify on YOUR OWN account, install the aws-pilot plugin instead.
EOF
  exit 2
fi

exit 0
