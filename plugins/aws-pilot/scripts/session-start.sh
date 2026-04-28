#!/usr/bin/env bash
# aws-pilot session-start hook: show account context to user.
set -euo pipefail

PROFILE="${AWS_PROFILE:-default}"

if ! command -v aws >/dev/null 2>&1; then
  cat <<EOF
{"hookSpecificOutput":{"additionalContext":"aws-pilot: AWS CLI not installed. Install: https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html"}}
EOF
  exit 0
fi

# Try to get caller identity (don't fail if creds missing)
IDENT=$(aws sts get-caller-identity --profile "$PROFILE" --output json 2>/dev/null || echo "{}")

if [ "$IDENT" = "{}" ]; then
  MSG="aws-pilot: no valid creds for profile '$PROFILE'. Run: aws configure --profile $PROFILE"
else
  ACCT=$(echo "$IDENT" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("Account",""))' 2>/dev/null || echo "?")
  ARN=$(echo "$IDENT" | python3 -c 'import json,sys;print(json.load(sys.stdin).get("Arn",""))' 2>/dev/null || echo "?")
  MODE="${AWS_PILOT_MODE:-dry-run}"
  REGION="${AWS_REGION:-us-east-1}"
  MSG="aws-pilot ready: account=$ACCT arn=$ARN region=$REGION mode=$MODE"
fi

# Hook output: additionalContext shown to Claude
python3 -c "import json,sys; print(json.dumps({'hookSpecificOutput':{'additionalContext':sys.argv[1]}}))" "$MSG"
