#!/usr/bin/env bash
# aws-pilot SessionStart hook: emit a one-line account context for Claude.
# Pure bash + jq fallback (works whether or not Python is installed).
set -euo pipefail

PROFILE="${AWS_PROFILE:-default}"
MODE="${AWS_PILOT_MODE:-dry-run}"
REGION="${AWS_REGION:-us-east-1}"

# Pick Python interpreter (any name)
PY=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done

emit() {
  # Emit hook output JSON. If Python available use it; else use heredoc with manual JSON escape.
  local msg="$1"
  if [ -n "$PY" ]; then
    MSG="$msg" "$PY" -c 'import json, os; print(json.dumps({"hookSpecificOutput": {"additionalContext": os.environ["MSG"]}}))'
  else
    # naive escape: backslash, double-quote, newline
    local esc
    esc=$(printf '%s' "$msg" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e ':a;N;$!ba;s/\n/\\n/g')
    printf '{"hookSpecificOutput":{"additionalContext":"%s"}}\n' "$esc"
  fi
}

if ! command -v aws >/dev/null 2>&1; then
  emit "aws-pilot: AWS CLI not installed. Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"
  exit 0
fi

IDENT_JSON=$(aws sts get-caller-identity --profile "$PROFILE" --output json 2>/dev/null || echo "")

if [ -z "$IDENT_JSON" ]; then
  emit "aws-pilot: no valid creds for profile '$PROFILE'. Run: aws configure --profile $PROFILE"
  exit 0
fi

if [ -n "$PY" ]; then
  ACCT=$(IDENT="$IDENT_JSON" "$PY" -c 'import json, os; d=json.loads(os.environ["IDENT"]); print(d.get("Account",""))' 2>/dev/null || echo "?")
  ARN=$(IDENT="$IDENT_JSON" "$PY" -c 'import json, os; d=json.loads(os.environ["IDENT"]); print(d.get("Arn",""))' 2>/dev/null || echo "?")
elif command -v jq >/dev/null 2>&1; then
  ACCT=$(echo "$IDENT_JSON" | jq -r '.Account // ""')
  ARN=$(echo "$IDENT_JSON" | jq -r '.Arn // ""')
else
  ACCT=$(echo "$IDENT_JSON" | grep -o '"Account"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*: *"//;s/"//')
  ARN=$(echo "$IDENT_JSON" | grep -o '"Arn"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*: *"//;s/"//')
fi

emit "aws-pilot ready: account=$ACCT arn=$ARN region=$REGION mode=$MODE"
