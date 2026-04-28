---
description: First-time AWS setup wizard — installs CLI, walks through IAM user creation, imports keys from CSV, configures plugin. Idempotent (skips done steps). Never prints credentials.
---

Run the **aws-firsttime-setup** skill end-to-end.

1. Start with `aws_health_check` to see what's done.
2. For each missing piece, only do that step (don't redo working things).
3. Browser automation: if the user already has the AWS console open in a
   browser AND `mcp__Claude_in_Chrome__*` is connected, drive the IAM
   wizard from steps 2–6. Otherwise give the user a clear manual checklist.
4. After CSV download, call `aws_import_credentials_from_csv`.
5. Re-run `aws_health_check`. Report score + remaining items.

Never echo `AKIA...` keys or secret values in the chat. Use the dedicated
import tool.
