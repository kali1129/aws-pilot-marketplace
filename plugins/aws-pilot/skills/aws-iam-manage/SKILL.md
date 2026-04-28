---
name: aws-iam-manage
description: Manage IAM users, roles, groups, access keys, and policies. Use when user wants to "create a user for X", "give Lambda access to S3", "rotate my access key", or "make a service account". Enforces least-privilege defaults.
---

# aws-iam-manage

Atomic skill: IAM lifecycle. Reads always safe; creates/attaches require `mode: execute`. Sensitive ops (root keys, AdministratorAccess) require explicit user confirmation.

## Read

```bash
aws iam list-users
aws iam list-roles
aws iam list-policies --scope Local
aws iam get-account-summary
aws iam list-access-keys --user-name <user>
aws iam get-account-password-policy
```

## Create a least-privilege user (deployment service account)

```bash
USER=deployer-frontend

# 1. Create user
aws iam create-user --user-name $USER \
  --tags Key=ManagedBy,Value=aws-pilot Key=Purpose,Value=ci-deploy

# 2. Custom least-privilege policy (only what's needed)
cat > /tmp/policy.json <<EOF
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["s3:PutObject","s3:GetObject","s3:DeleteObject","s3:ListBucket"],
      "Resource": ["arn:aws:s3:::mysite-prod","arn:aws:s3:::mysite-prod/*"]
    },
    {
      "Effect": "Allow",
      "Action": ["cloudfront:CreateInvalidation"],
      "Resource": "arn:aws:cloudfront::${ACCT}:distribution/${DIST_ID}"
    }
  ]
}
EOF

POLICY_ARN=$(aws iam create-policy \
  --policy-name "${USER}-policy" \
  --policy-document file:///tmp/policy.json \
  --query 'Policy.Arn' --output text)

aws iam attach-user-policy --user-name $USER --policy-arn $POLICY_ARN

# 3. Access key
aws iam create-access-key --user-name $USER --output json
# IMPORTANT: save AccessKeyId + SecretAccessKey to ~/.aws/credentials with chmod 600
```

## Create a role for an AWS service (e.g., Lambda → S3)

```bash
ROLE=lambda-uploader-role

# Trust policy: who can assume this role?
cat > /tmp/trust.json <<EOF
{"Version":"2012-10-17","Statement":[{
  "Effect":"Allow",
  "Principal":{"Service":"lambda.amazonaws.com"},
  "Action":"sts:AssumeRole"
}]}
EOF

aws iam create-role \
  --role-name $ROLE \
  --assume-role-policy-document file:///tmp/trust.json \
  --tags Key=ManagedBy,Value=aws-pilot

# Permissions policy
aws iam attach-role-policy \
  --role-name $ROLE \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Inline policy for S3 specifics
cat > /tmp/s3-perm.json <<EOF
{"Version":"2012-10-17","Statement":[{
  "Effect":"Allow",
  "Action":["s3:GetObject","s3:PutObject"],
  "Resource":"arn:aws:s3:::my-bucket/*"
}]}
EOF
aws iam put-role-policy \
  --role-name $ROLE \
  --policy-name s3-access \
  --policy-document file:///tmp/s3-perm.json
```

## Rotate access keys

```bash
USER=anderson
# 1. Create new key
NEW=$(aws iam create-access-key --user-name $USER --output json)
echo "$NEW"  # save somewhere safe

# 2. Update applications/CI to use new key

# 3. Wait 24h, verify new key working

# 4. Deactivate old key
OLD=$(aws iam list-access-keys --user-name $USER \
  --query 'AccessKeyMetadata[?Status==`Active`].AccessKeyId' --output text | head -1)
aws iam update-access-key --access-key-id $OLD --status Inactive --user-name $USER

# 5. After full week, delete old
aws iam delete-access-key --access-key-id $OLD --user-name $USER
```

## Account hardening (run once per account)

```bash
# Strong password policy
aws iam update-account-password-policy \
  --minimum-password-length 14 \
  --require-symbols --require-numbers \
  --require-uppercase-characters --require-lowercase-characters \
  --max-password-age 90 \
  --password-reuse-prevention 5

# MFA on root: must be done in console; surface a TODO with link
echo "TODO: enable MFA on root account at https://console.aws.amazon.com/iam/home#/security_credentials"

# Find users without MFA
aws iam list-users --query 'Users[].UserName' --output text | \
while read u; do
  mfa=$(aws iam list-mfa-devices --user-name $u --query 'length(MFADevices)' --output text)
  [ "$mfa" = "0" ] && echo "MFA missing: $u"
done
```

## Constraints

- DEFAULT to least-privilege custom policies, NOT AWS-managed `AdministratorAccess`
- Refuse to create access keys for `root` user
- ALWAYS attach `ManagedBy=aws-pilot` tag
- Print access key SecretAccessKey ONCE and instruct the user to save it; AWS won't show it again
- For role trust policies, never use `Principal: "*"` — always scope to specific service or account
- Confirm before any `delete-user`, `delete-role`, `detach-user-policy`
