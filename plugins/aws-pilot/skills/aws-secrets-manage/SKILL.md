---
name: aws-secrets-manage
description: Store and retrieve secrets in AWS Secrets Manager — DB passwords, API keys, OAuth tokens. Use when user says "store this securely on AWS" or "I need a place for my Stripe key". Encrypted at rest, IAM-gated, optional automatic rotation.
---

# aws-secrets-manage

Atomic skill: Secrets Manager CRUD. Read = safe. Create/update/delete require `mode: execute`.

## Store a secret

```bash
NAME=stripe/live-key-restricted
aws secretsmanager create-secret \
  --name $NAME \
  --description "Stripe restricted key for production" \
  --secret-string "{\"stripe_key\":\"rk_live_xxxxxxxxxxxx\"}" \
  --tags Key=ManagedBy,Value=aws-pilot Key=Env,Value=prod
```

For DB credentials (structured):
```bash
aws secretsmanager create-secret \
  --name "rds/myapp/master" \
  --secret-string '{
    "engine":"postgres",
    "host":"myapp-db.abc.us-east-1.rds.amazonaws.com",
    "port":5432,
    "username":"admin",
    "password":"long-random-password",
    "dbname":"myapp"
  }'
```

## Retrieve

```bash
# Get the secret value
aws secretsmanager get-secret-value --secret-id $NAME --query SecretString --output text

# In Python
python3 -c "
import boto3, json
sm = boto3.client('secretsmanager')
r = sm.get_secret_value(SecretId='$NAME')
print(json.loads(r['SecretString'])['stripe_key'])
"
```

## Update

```bash
aws secretsmanager put-secret-value \
  --secret-id $NAME \
  --secret-string "{\"stripe_key\":\"rk_live_NEWKEY\"}"
# Old value still retrievable via VersionStage=AWSPREVIOUS for 24h
```

## List + describe

```bash
aws secretsmanager list-secrets --output table
aws secretsmanager describe-secret --secret-id $NAME
```

## Grant Lambda access to a secret

```bash
# Inline policy on the Lambda execution role
cat > /tmp/sm-read.json <<EOF
{"Version":"2012-10-17","Statement":[{
  "Effect":"Allow",
  "Action":["secretsmanager:GetSecretValue"],
  "Resource":"arn:aws:secretsmanager:${REGION}:${ACCT}:secret:${NAME}-*"
}]}
EOF
aws iam put-role-policy \
  --role-name $LAMBDA_ROLE \
  --policy-name read-${NAME//\//-} \
  --policy-document file:///tmp/sm-read.json
```

## Automatic rotation (RDS only — easy)

```bash
aws secretsmanager rotate-secret \
  --secret-id rds/myapp/master \
  --rotation-rules AutomaticallyAfterDays=30 \
  --rotation-lambda-arn arn:aws:lambda:${REGION}:${ACCT}:function:SecretsManagerRDSPostgreSQLRotationSingleUser
```

## Delete (with recovery window)

```bash
# Soft delete — recoverable for 30 days (default)
aws secretsmanager delete-secret --secret-id $NAME

# Force-delete (no recovery)
# aws secretsmanager delete-secret --secret-id $NAME --force-delete-without-recovery
```

## Cost

- $0.40/secret/month
- $0.05 per 10k API calls

For low-cost alternative: SSM Parameter Store (free for Standard tier, supports SecureString with KMS).

## Constraints

- DEFAULT to JSON-structured secrets so apps can parse multiple values
- ALWAYS tag with `ManagedBy=aws-pilot, Env=<env>`
- NEVER print full secret value in chat — show name + first/last 4 chars + length
- Force-delete requires explicit user confirmation (no recovery)
- For Stripe/OAuth-style high-value keys, recommend Secrets Manager + rotation
- For static config (DB hosts, feature flags), recommend SSM Parameter Store (cheaper)
