#!/usr/bin/env bash
# aws-bb-toolkit PreToolUse: block any aws-cli WRITE op outright. BB toolkit is strictly
# read-only — never modify the target. Distinguishes verb tokens from flag values
# (e.g. `aws s3 cp ./local s3://b/ --delete` is allowed; `--delete` is a flag, not the verb).
set -euo pipefail

HOOK_INPUT=$(cat || true)
export HOOK_INPUT

PY=""
for cand in python3 python py; do
  if command -v "$cand" >/dev/null 2>&1; then PY="$cand"; break; fi
done
if [ -z "$PY" ]; then
  # If no Python, fall back to a conservative regex (may have FPs/FNs but blocks the obvious).
  CMD=$(printf '%s' "$HOOK_INPUT" | grep -o '"command"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*"command"[[:space:]]*:[[:space:]]*"\(.*\)"/\1/' || true)
  if echo "$CMD" | grep -qE '^[[:space:]]*aws '; then
    if echo "$CMD" | grep -qE ' (run-instances|terminate-instances|create-[a-z-]+|put-[a-z-]+|delete-[a-z-]+|modify-[a-z-]+|update-[a-z-]+|start-instances|stop-instances|invoke|attach-[a-z-]+|detach-[a-z-]+) '; then
      echo "aws-bb-toolkit: WRITE OPERATION BLOCKED (fallback regex): $CMD" >&2
      exit 2
    fi
  fi
  exit 0
fi

"$PY" - <<'PYEOF'
import json, os, re, sys

raw = os.environ.get("HOOK_INPUT", "")
if not raw.strip():
    sys.exit(0)
try:
    payload = json.loads(raw)
except Exception:
    sys.exit(0)

cmd = (payload.get("tool_input") or {}).get("command", "")
if not isinstance(cmd, str) or not re.match(r'^\s*aws\b', cmd):
    sys.exit(0)

toks = [t for t in re.split(r'\s+', cmd.strip()) if t and not t.startswith("--")]

WRITE_PREFIXES = (
    "create-", "update-", "put-", "delete-", "attach-", "detach-",
    "terminate-", "modify-", "restore-", "release-", "associate-",
    "disassociate-", "authorize-", "revoke-", "register-", "deregister-",
    "set-", "tag-", "untag-", "enable-", "disable-", "reboot-",
)
WRITE_EXACT = {"invoke", "run-instances", "start-instances", "stop-instances",
               "rb", "rm", "mv", "sync", "cp"}  # s3 high-level commands; some destructive

hit = None
for t in toks[1:]:
    if any(t.startswith(p) for p in WRITE_PREFIXES) or t in WRITE_EXACT:
        # Exclude clearly-read s3 cp/sync from local→local or s3:// → local:
        if t in ("cp", "sync", "mv"):
            # Only block if target is s3:// (writing TO s3)
            args_after = toks[toks.index(t)+1:]
            if not any(a.startswith("s3://") for a in args_after[1:]):
                continue
            # If only source is s3:// (download), that's a read — skip
            if args_after and args_after[0].startswith("s3://") and (len(args_after) < 2 or not args_after[1].startswith("s3://")):
                continue
        hit = t
        break

if hit is None:
    sys.exit(0)

print(f"""aws-bb-toolkit: WRITE OPERATION BLOCKED.

Command: {cmd}

Verb '{hit}' would modify the target. This toolkit is read-only by design — modifying
a bug-bounty target's AWS account is out of scope for any legitimate engagement. If
you actually need to provision/modify on YOUR OWN account, install the aws-pilot
plugin instead.""", file=sys.stderr)
sys.exit(2)
PYEOF
