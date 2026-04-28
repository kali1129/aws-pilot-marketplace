---
description: Audit AWS for unused resources eating money — unattached volumes, idle EIPs, old snapshots, idle ALBs/NATs. Read-only audit; deletes require per-resource confirmation.
---

Run the **aws-cleanup-unused** skill.

1. Run the read-only audit across all regions in use
2. Sort findings by potential monthly savings (descending)
3. Render as a table:
   ```
   Resource                       Cost/mo   Last used   Action
   nat-0abc (us-east-1a)          $32.40    no traffic 30d   Delete?
   eip 3.4.5.6                    $3.65     unattached 14d   Release?
   ...
   Total identified               $XX.XX/mo
   ```
4. Walk through each finding and ask: keep / delete / skip
5. After all decisions, print summary:
   ```
   Deleted: N items, ~$X.XX/mo saved
   Skipped: M items
   ```
6. Append everything to audit log.

Constraints:
- Never auto-delete
- Skip resources tagged `DoNotDelete=true` or `Persistent=true`
- Resources <7 days old: skip (could be in-progress work)
