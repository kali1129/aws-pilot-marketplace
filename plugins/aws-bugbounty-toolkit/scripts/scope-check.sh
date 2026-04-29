#!/usr/bin/env bash
# aws-bb-toolkit SessionStart: verify scope file exists; emit context to Claude.
set -euo pipefail

SCOPE="${SCOPE_FILE:-}"
THROTTLE="${THROTTLE_SECONDS:-3}"

if [ -z "$SCOPE" ] || [ ! -f "$SCOPE" ]; then
  MSG="aws-bb-toolkit: WARNING — no scope_file configured. Set with: claude /plugin config aws-bb-toolkit scope_file=/path/to/scope.txt — toolkit will refuse to enumerate without it."
else
  # count non-blank, non-comment lines (handles missing trailing newline)
  COUNT=$(grep -cv -E '^[[:space:]]*(#|$)' "$SCOPE" 2>/dev/null || echo 0)
  MSG="aws-bb-toolkit ready: scope file has $COUNT entries. Throttle ${THROTTLE}s between aws calls. Read-only mode."
fi

# Pick Python (any) for safe JSON encode; fall back to manual escape
PY=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done

if [ -n "$PY" ]; then
  MSG="$MSG" "$PY" -c 'import json, os; print(json.dumps({"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":os.environ["MSG"]}}))'
else
  esc=$(printf '%s' "$MSG" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g')
  printf '{"hookSpecificOutput":{"hookEventName":"SessionStart","additionalContext":"%s"}}\n' "$esc"
fi
