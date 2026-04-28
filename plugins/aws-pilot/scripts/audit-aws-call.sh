#!/usr/bin/env bash
# aws-pilot PostToolUse hook: append every aws-cli invocation to a JSONL audit file.
# The full hook payload (JSON) is read from stdin and passed to Python via an env var,
# never interpolated into the script body — eliminates the triple-quote injection sink.
set -euo pipefail

HOOK_INPUT=$(cat || true)
export HOOK_INPUT
export AWS_PILOT_AUDIT_LOG="${AWS_PILOT_AUDIT_LOG:-${CLAUDE_PLUGIN_DATA:-/tmp}/aws-pilot-audit.jsonl}"

# Pick first available Python interpreter (Windows often has only `python`)
PY=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
[ -z "$PY" ] && exit 0   # silently skip — never block a tool call on missing Python

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

out = (payload.get("tool_response") or {}).get("output", "")
if not isinstance(out, str):
    out = str(out)

log_path = pathlib.Path(os.environ["AWS_PILOT_AUDIT_LOG"])
try:
    log_path.parent.mkdir(parents=True, exist_ok=True)
    entry = {
        "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "source": "bash-hook",
        "command": cmd.strip(),
        "output_preview": out.strip()[:300],
    }
    with log_path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry) + "\n")
except (OSError, PermissionError):
    pass
PYEOF
exit 0
