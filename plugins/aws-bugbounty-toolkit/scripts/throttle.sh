#!/usr/bin/env bash
# aws-bb-toolkit PreToolUse: rate-limit aws CLI calls.
# Reads last-call timestamp from temp file, sleeps if needed.
set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || echo "")

if ! echo "$COMMAND" | grep -qE '^[[:space:]]*aws ' ; then
  exit 0
fi

THROTTLE="${THROTTLE_SECONDS:-3}"
STATE="${CLAUDE_PLUGIN_DATA:-/tmp}/aws-bb-throttle"
mkdir -p "$(dirname "$STATE")"

NOW=$(date +%s)
LAST=0
[ -f "$STATE" ] && LAST=$(cat "$STATE")
ELAPSED=$((NOW - LAST))

if [ "$ELAPSED" -lt "$THROTTLE" ]; then
  WAIT=$((THROTTLE - ELAPSED))
  sleep "$WAIT"
fi

date +%s > "$STATE"
exit 0
