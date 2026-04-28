#!/usr/bin/env bash
# aws-pilot PostToolUse hook: log every aws-cli invocation to JSONL audit file.
set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || echo "")
OUTPUT=$(echo "$INPUT" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_response",{}).get("output","")[:500])' 2>/dev/null || echo "")

if ! echo "$COMMAND" | grep -qE '^[[:space:]]*aws ' ; then
  exit 0
fi

LOG="${AWS_PILOT_AUDIT_LOG:-${CLAUDE_PLUGIN_DATA:-/tmp}/aws-pilot-audit.jsonl}"
mkdir -p "$(dirname "$LOG")"

python3 -c "
import json, sys, datetime
entry = {
    'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source': 'bash-hook',
    'command': '''$COMMAND'''.strip(),
    'output_preview': '''$OUTPUT'''.strip()[:200],
}
print(json.dumps(entry))
" >> "$LOG"

exit 0
