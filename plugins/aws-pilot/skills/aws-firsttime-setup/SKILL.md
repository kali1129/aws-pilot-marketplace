---
name: aws-firsttime-setup
description: First-time setup workflow for users who have never connected AWS to Claude Code. Walks through installing AWS CLI, creating an IAM user, generating access keys, and configuring the plugin — without ever printing credentials in the chat. Use when the user says "I have an AWS account but never used it" or aws_health_check reports no_creds.
---

# aws-firsttime-setup

Composite skill: detects what's already done and only does what's missing.

## Pre-check (always run first)

Call `aws_health_check`. The findings tell you exactly what's missing:
- `no_creds` → continue from Step 1
- `cost_explorer_disabled` / `no_mfa` → only those need fixing
- nothing → setup is already complete

## Step 1 — AWS CLI installed?

```bash
command -v aws || command -v aws.exe
```

If missing:
| OS      | Command                                   |
|---------|-------------------------------------------|
| Windows | `winget install Amazon.AWSCLI`            |
| macOS   | `brew install awscli`                     |
| Linux   | https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html |

## Step 2 — IAM user with access keys

The user needs to do this in their AWS console (we cannot do it for them
because creating IAM users is a Tier-1 sensitive op). Walk them through:

1. **Open** https://us-east-1.console.aws.amazon.com/iam/home#/users/create
2. **Username**: e.g. `claude-code-pilot` — leave the "console access" checkbox UNCHECKED
3. **Permissions**: choose "Attach policies directly" → search "AdministratorAccess" → check the row whose policy is exactly `AdministratorAccess` (NOT the variants like `AdministratorAccess-Amplify`)
4. **Create user**, then click into the user → **Security credentials** tab
5. Scroll to **Access keys** → "Create access key" → use case "Command Line Interface (CLI)" → check the disclaimer → Next → (description tag optional) → Create
6. **Download the .csv** (last chance to see the secret)

If they're already logged in to the AWS console in their browser AND we have
the `mcp__Claude_in_Chrome__*` tools available, we CAN automate steps 1–6 by
driving the browser. But require:
- a connected browser (`list_connected_browsers`)
- the right window focused (use Win32 EnumWindows on Windows if multiple
  browser windows; see /memory/feedback_browser_window_enum.md)

## Step 3 — Import the keys (no copy-paste, no chat leak)

Once the CSV is downloaded:

```python
mcp__plugin_aws-pilot_aws-pilot-mcp__aws_import_credentials_from_csv(
    csv_path="<path to .csv, usually ~/Downloads/<user>_accessKeys.csv>",
    profile="default",
    delete_after=True,
)
```

This reads the CSV, configures `~/.aws/credentials` silently, verifies via
`sts get-caller-identity`, and deletes the CSV. The chat sees only metadata
(prefix + length, never the secret value).

## Step 4 — Plug it into the plugin

```
/plugin config aws-pilot aws_profile=default
```

(Skip if `default` is already correct — the plugin's default value.)

## Step 5 — Verify

Run `aws_health_check` again. Score should be ≥80. Common remaining items:
- `cost_explorer_disabled` (medium): manual opt-in at Billing console, 24h lag
- `no_mfa` (medium): recommended but optional
- `no_default_vpc` (medium): only if user picked an unusual region

## Step 6 — Sanity check

Call `aws_account_overview`. Should return account_id, ARN, region, and (if
Cost Explorer is enabled) MTD spend.

## Constraints

- Never ask the user to paste keys into chat
- Never use `aws configure` interactively (use `aws configure set` per-key)
- Always set `delete_after=True` when importing CSV so it doesn't linger
- Recommend AdministratorAccess only as a starting point; add a TODO to scope
  down later (least privilege)
