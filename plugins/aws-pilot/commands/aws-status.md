---
description: Show a one-page summary of the AWS account — caller identity, cost MTD, top services, active alarms.
---

Run the **aws-account-status** skill and render its output as a compact summary the user can read in 10 seconds. Use the `aws_account_overview` MCP tool if available for cached/normalized output. Always read-only.

If the user has not configured `aws_profile` yet, halt and instruct:
```
You haven't connected an AWS account yet.

1. Install AWS CLI:    https://docs.aws.amazon.com/cli/latest/userguide/getting-started-install.html
2. Get keys:           AWS Console → IAM → Users → your-user → Security credentials → Create access key
3. Configure:          aws configure --profile aws-pilot
4. Set in plugin:      claude /plugin config aws-pilot aws_profile=aws-pilot
```
