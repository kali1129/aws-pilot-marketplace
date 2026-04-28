---
description: AWS account health check — detects missing creds, root keys, no MFA, Cost Explorer disabled, missing default VPC, stale access keys, budget warnings.
---

Call the MCP tool `aws_health_check`.

Render output as a readable report:

```
AWS Health: 80 / 100

[medium] Cost Explorer not enabled
   → Console → Billing → Cost Explorer → Launch (24h delay)

[medium] User 'claude-code-pilot' has no MFA
   → IAM → Users → claude-code-pilot → Security credentials → Assign MFA
```

If score < 50, prefix with "🚨 " — these need attention. If score is 100,
just say "All checks pass."

Never print account ID more than once, never print access keys.
