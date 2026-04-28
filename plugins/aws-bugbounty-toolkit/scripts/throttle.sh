#!/usr/bin/env bash
# aws-bb-toolkit PreToolUse: rate-limit aws CLI calls AND enforce per-session call cap.
# Uses flock for race-safe state under parallel Bash tool calls.
set -euo pipefail

HOOK_INPUT=$(cat || true)

# Extract command without shell-interpolating it
CMD=""
PY=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -n "$PY" ]; then
  CMD=$(HOOK_INPUT="$HOOK_INPUT" "$PY" -c '
import json, os, sys
try:
    p = json.loads(os.environ["HOOK_INPUT"])
    print((p.get("tool_input") or {}).get("command", ""), end="")
except Exception:
    pass
' || true)
else
  CMD=$(printf '%s' "$HOOK_INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"command"[[:space:]]*:[[:space:]]*"\(.*\)"/\1/' || true)
fi

case "$CMD" in
  *"aws "*) ;;
  *) exit 0 ;;
esac

THROTTLE="${THROTTLE_SECONDS:-3}"
MAX_CALLS="${MAX_CALLS_PER_SESSION:-200}"
STATE_DIR="${CLAUDE_PLUGIN_DATA:-/tmp}"
mkdir -p "$STATE_DIR" 2>/dev/null || true
LOCK="$STATE_DIR/aws-bb-throttle.lock"
COUNTER="$STATE_DIR/aws-bb-throttle.count"
LAST_TS="$STATE_DIR/aws-bb-throttle.last"

# Acquire lock (waits up to 10s)
exec 9>"$LOCK"
if command -v flock >/dev/null 2>&1; then
  flock -w 10 9 || exit 0
fi

# Counter check
COUNT=0
[ -f "$COUNTER" ] && COUNT=$(cat "$COUNTER" 2>/dev/null || echo 0)
if [ "$COUNT" -ge "$MAX_CALLS" ]; then
  echo "aws-bb-toolkit: SESSION CALL CAP REACHED ($MAX_CALLS). Reset by deleting $COUNTER or set MAX_CALLS_PER_SESSION higher." >&2
  exit 2
fi

# Throttle: sleep until $THROTTLE seconds since last call
NOW=$(date +%s)
LAST=0
[ -f "$LAST_TS" ] && LAST=$(cat "$LAST_TS" 2>/dev/null || echo 0)
ELAPSED=$((NOW - LAST))
if [ "$ELAPSED" -lt "$THROTTLE" ]; then
  sleep $((THROTTLE - ELAPSED))
fi

# Update state
date +%s > "$LAST_TS"
echo $((COUNT + 1)) > "$COUNTER"

exit 0
