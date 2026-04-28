#!/usr/bin/env bash
# aws-bb-toolkit PostToolUse: append every aws CLI call to findings JSONL.
# Hook payload (JSON) read from stdin, passed to Python via env var — no interpolation.
set -euo pipefail

HOOK_INPUT=$(cat || true)
export HOOK_INPUT
export FINDINGS_LOG="${FINDINGS_LOG:-${CLAUDE_PLUGIN_DATA:-/tmp}/aws-bb-findings.jsonl}"

PY=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -z "$PY" ] && exit 0

"$PY" - <<'PYEOF'
import json, os, sys, datetime, pathlib

raw = os.environ.get("HOOK_INPUT", "")
if not raw.strip():
    sys.exit(0)
try:
    payload = json.loads(raw)
except Exception:
    sys.exit(0)

cmd = (payload.get("tool_input") or {}).get("command", "")
if not isinstance(cmd, str) or not cmd.strip().startswith("aws "):
    sys.exit(0)

log_path = pathlib.Path(os.environ["FINDINGS_LOG"])
try:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "aws-bb-toolkit",
        "command": cmd.strip(),
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
except (OSError, PermissionError):
    pass
PYEOF
exit 0
