---
name: aws-s3-recon
description: Enumerate S3 buckets in an authorized AWS scope — list buckets, check ACLs/policies/public access, look for sensitive object names, test public read/list/write. Use for bug bounty when S3 is in scope. Read-only.
---

# aws-s3-recon

Atomic skill: S3 enumeration with authenticated creds + unauthenticated bucket guessing. Read-only.

## Pre-flight

1. Verify scope file contains the target's bucket prefix or account ID
2. Throttle 3s between calls

## Commands

```bash
# Authenticated bucket listing
aws s3api list-buckets --profile $AWS_PROFILE --output json

# Per bucket: ACL, policy, public access, versioning, encryption, logging
B=target-bucket
aws s3api get-bucket-acl --bucket $B
aws s3api get-bucket-policy --bucket $B
aws s3api get-public-access-block --bucket $B
aws s3api get-bucket-versioning --bucket $B
aws s3api get-bucket-encryption --bucket $B
aws s3api get-bucket-logging --bucket $B
aws s3api get-bucket-website --bucket $B

# List a sample (avoid downloading entire bucket)
aws s3 ls s3://$B/ --max-items 50

# Unauthenticated guess: bucket name from subdomains / source code
for guess in $(cat candidate_buckets.txt); do
  curl -sI "https://$guess.s3.amazonaws.com/" | head -1
done
```

## What to look for

- `Bucket Policy` with `Principal: "*"` and broad action (`s3:GetObject`, `s3:ListBucket`)
- `PublicAccessBlock` disabled (allows public ACLs)
- `AllUsers` or `AuthenticatedUsers` grantees in ACL
- Backup files: `.sql`, `.tar.gz`, `.bak`, `.env`, `.pem`, source code, build artifacts
- Misconfigured website hosting on internal docs
- `BucketEncryption` missing → data-at-rest finding
- `Logging` disabled → forensics gap (low severity but report)

## Output

```json
{"ts":"...","skill":"aws-s3-recon","bucket":"target-foo","public_read":true,"sensitive_objects":["backup.sql.gz"]}
```

## Constraints

- NEVER write/delete/upload — read-only
- Don't download large objects; head them and extract metadata
- If creds escalate beyond program scope, halt
