#!/usr/bin/env bash
# aws-bb-toolkit PostToolUse: append every aws CLI call to findings JSONL.
set -euo pipefail

INPUT=$(cat)
COMMAND=$(echo "$INPUT" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("tool_input",{}).get("command",""))' 2>/dev/null || echo "")

if ! echo "$COMMAND" | grep -qE '^[[:space:]]*aws ' ; then
  exit 0
fi

LOG="${FINDINGS_LOG:-${CLAUDE_PLUGIN_DATA:-/tmp}/aws-bb-findings.jsonl}"
mkdir -p "$(dirname "$LOG")"

python3 -c "
import json, datetime
print(json.dumps({
    'ts': datetime.datetime.now(datetime.timezone.utc).isoformat(),
    'source': 'aws-bb-toolkit',
    'command': '''$COMMAND'''.strip()
}))
" >> "$LOG"

exit 0
