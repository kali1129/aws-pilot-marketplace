---
description: 'Provision a VPS-style EC2 with SSH key, Docker installed, optional domain + TLS. Asks for purpose (general/web/db) and name.'
argument-hint: '[name] [purpose: general|web|db] [domain?]'
---

Run the **aws-deploy-vps** skill end-to-end:

1. Collect inputs from `$ARGUMENTS` (or ask if missing):
   - Name (kebab-case, ≤30 chars)
   - Purpose: `general` (t3.small) | `web` (t3.small + 80/443) | `db` (t3.medium private)
   - Domain (optional)

2. Show cost preview based on purpose. Wait for explicit "yes" before proceeding.

3. Execute the provisioning workflow (calls `aws-ec2-manage`, `aws-route53-dns` if domain).

4. After success, print:
   ```
   ✓ VPS ready
   IP:     X.X.X.X
   SSH:    ssh -i ~/.ssh/aws-<name>.pem ec2-user@X.X.X.X
   URL:    https://<domain>      (if domain provided)
   Tag:    ManagedBy=aws-pilot
   Cost:   ~$Y.YY/mo
   ```

5. Append a row to `${user_config.audit_log}` with all created resource IDs (so `/aws-cleanup` can find them later).
