#!/usr/bin/env bash
# aws-bb-toolkit session-start: verify scope file exists and remind user.
set -euo pipefail

SCOPE="${SCOPE_FILE:-}"
MSG=""

if [ -z "$SCOPE" ] || [ ! -f "$SCOPE" ]; then
  MSG="aws-bb-toolkit: WARNING — no scope_file configured. Set with: claude /plugin config aws-bb-toolkit scope_file=/path/to/scope.txt — toolkit will refuse to enumerate without it."
else
  COUNT=$(wc -l < "$SCOPE" 2>/dev/null || echo 0)
  MSG="aws-bb-toolkit ready: scope file has $COUNT entries. Throttle ${THROTTLE_SECONDS:-3}s. Read-only mode."
fi

python3 -c "import json,sys; print(json.dumps({'hookSpecificOutput':{'additionalContext':sys.argv[1]}}))" "$MSG"
