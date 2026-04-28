# aws-pilot-marketplace

Two AWS plugins for [Claude Code](https://code.claude.com), packaged as a single git-based marketplace.

## What's inside

### `aws-pilot` — Claude controls your AWS account

For users who want to run things on AWS but don't know AWS. Claude provisions EC2 instances (with auto-generated SSH keys), creates S3 buckets, deploys Lambda functions, manages DNS, monitors billing, and finds wasted resources to delete.

- 14 atomic skills (one per AWS service / common task)
- 3 sub-agents (`haiku` for quick lookups, `sonnet` for execution, `opus` for architecture)
- 4 slash commands (`/aws-status`, `/aws-cost`, `/aws-deploy-vps`, `/aws-cleanup`)
- boto3-backed MCP server (local stdio for dev, Docker/HTTP for VPS deploy)
- Safety hooks: destructive-op confirmation, full audit log, dry-run by default

### `aws-bb-toolkit` — offensive AWS recon for authorized bug bounty

For BB hunters who land AWS-scoped programs and need fast read-only enumeration of leaked creds.

- 7 atomic skills (IAM/S3/Lambda/Secrets/IMDS/CloudTrail)
- 3 sub-agents (recon-runner / finding-analyst / chain-strategist)
- Hooks enforce: scope check, read-only guard, throttle, findings log

## Install

```bash
# Add this marketplace
claude plugin marketplace add kali1129/aws-pilot-marketplace

# Install the plugin you want
claude plugin install aws-pilot@aws-pilot-marketplace
# or
claude plugin install aws-bb-toolkit@aws-pilot-marketplace
```

## Local development

To test changes without publishing:

```bash
# From inside the plugin folder
claude --plugin-dir ./plugins/aws-pilot
# (or both)
claude --plugin-dir ./plugins/aws-pilot --plugin-dir ./plugins/aws-bugbounty-toolkit
```

## Repo layout

```
aws-pilot-marketplace/
├── .claude-plugin/
│   └── marketplace.json        # marketplace manifest (lists both plugins)
├── plugins/
│   ├── aws-pilot/              # control-plane plugin
│   └── aws-bugbounty-toolkit/  # BB recon plugin
├── README.md
└── LICENSE
```

## License

MIT — see [LICENSE](./LICENSE).

## Status

Currently in test/dev. Production hosting (MCP server on a VPS, marketplace published publicly) coming once stable.
