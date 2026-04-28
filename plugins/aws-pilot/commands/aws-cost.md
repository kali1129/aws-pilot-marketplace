---
description: Show current month-to-date AWS cost, end-of-month forecast, and any spend spikes.
---

Run the **aws-cost-monitor** skill. Always read-only.

Output format:
```
MTD: $X.XX  / Budget: $YY  / Forecast EOM: $ZZ.ZZ
Top: <service1 $> <service2 $> <service3 $>
[Spike alert if any]
```

If forecast > budget, suggest the cheapest savings (usually `/aws-cleanup` or stopping idle EC2).
