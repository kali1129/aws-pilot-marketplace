---
name: aws-s3-manage
description: Manage S3 buckets — create, list, configure access, upload/download files, set public/private, enable static website hosting, configure encryption and lifecycle. Use when user wants to "make a bucket", "host static files on S3", or "store backups on S3".
---

# aws-s3-manage

Atomic skill: full S3 lifecycle. Read = always safe; create/delete require `mode: execute`.

## Read

```bash
aws s3api list-buckets --output json
aws s3 ls s3://<bucket>/ --recursive --summarize | tail -3
aws s3api get-bucket-acl --bucket <bucket>
aws s3api get-bucket-policy --bucket <bucket>
aws s3api get-public-access-block --bucket <bucket>
aws s3api get-bucket-encryption --bucket <bucket>
```

## Create a private bucket (default)

```bash
B=my-private-bucket-$(date +%s)
REGION=${user_config.default_region}

aws s3api create-bucket \
  --bucket $B \
  --region $REGION \
  $([ "$REGION" != "us-east-1" ] && echo "--create-bucket-configuration LocationConstraint=$REGION")

# Block all public access (default for new buckets but make explicit)
aws s3api put-public-access-block \
  --bucket $B \
  --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"

# Server-side encryption with SSE-S3
aws s3api put-bucket-encryption --bucket $B --server-side-encryption-configuration '{
  "Rules":[{"ApplyServerSideEncryptionByDefault":{"SSEAlgorithm":"AES256"}}]
}'

# Versioning
aws s3api put-bucket-versioning --bucket $B --versioning-configuration Status=Enabled
```

## Create a public static-site bucket

```bash
B=mysite-static-$(date +%s)

aws s3api create-bucket --bucket $B --region $REGION
# Allow public read
aws s3api delete-public-access-block --bucket $B
cat > /tmp/policy.json <<EOF
{"Version":"2012-10-17","Statement":[{
  "Sid":"PublicRead","Effect":"Allow","Principal":"*",
  "Action":"s3:GetObject","Resource":"arn:aws:s3:::${B}/*"
}]}
EOF
aws s3api put-bucket-policy --bucket $B --policy file:///tmp/policy.json

# Static website hosting
aws s3api put-bucket-website --bucket $B --website-configuration '{
  "IndexDocument":{"Suffix":"index.html"},
  "ErrorDocument":{"Key":"404.html"}
}'

# URL: http://<bucket>.s3-website-<region>.amazonaws.com
echo "http://${B}.s3-website-${REGION}.amazonaws.com"
```

## Upload / download

```bash
# Upload single file
aws s3 cp ./file.txt s3://$B/file.txt

# Sync entire dir
aws s3 sync ./build/ s3://$B/ --delete --cache-control "max-age=3600"

# Download
aws s3 cp s3://$B/file.txt ./
aws s3 sync s3://$B/ ./local-backup/
```

## Lifecycle (auto-delete old versions / move to Glacier)

```bash
cat > /tmp/lifecycle.json <<EOF
{"Rules":[{
  "ID":"expire-old-versions","Status":"Enabled",
  "NoncurrentVersionExpiration":{"NoncurrentDays":30},
  "AbortIncompleteMultipartUpload":{"DaysAfterInitiation":7}
}]}
EOF
aws s3api put-bucket-lifecycle-configuration --bucket $B --lifecycle-configuration file:///tmp/lifecycle.json
```

## Delete (DESTRUCTIVE — hook will block)

```bash
# Empty first (versioned buckets need extra steps)
aws s3 rm s3://$B/ --recursive
# Delete the bucket
aws s3api delete-bucket --bucket $B
```

## Constraints

- Default new buckets to PRIVATE with PublicAccessBlock + SSE-S3
- Public buckets only when explicitly asked AND user accepts cost/risk warning
- Tag bucket: `ManagedBy=aws-pilot, Purpose=<static-site|backup|data>`
- Never `delete-bucket` without confirmation hook approval
- Bucket name must be globally unique; suggest with timestamp suffix
