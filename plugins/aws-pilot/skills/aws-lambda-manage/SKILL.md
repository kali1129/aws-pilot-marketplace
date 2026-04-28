---
name: aws-lambda-manage
description: Create, update, invoke, list, and delete AWS Lambda functions. Use when user wants to "deploy a serverless function", "run code on a schedule", or "respond to S3 uploads automatically". Handles role creation, code packaging (zip), env vars, and triggers.
---

# aws-lambda-manage

Atomic skill: Lambda lifecycle. Read = safe. Create/update/delete require `mode: execute`.

## Read

```bash
aws lambda list-functions --output json
aws lambda get-function --function-name <name>
aws lambda list-event-source-mappings --function-name <name>
aws logs tail /aws/lambda/<name> --follow
```

## Deploy a new Python function

```bash
F=hello-world
REGION=${user_config.default_region}

# Step 1: Create execution role (if doesn't exist)
ROLE=lambda-${F}-role
aws iam create-role \
  --role-name $ROLE \
  --assume-role-policy-document '{
    "Version":"2012-10-17",
    "Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]
  }'
aws iam attach-role-policy \
  --role-name $ROLE \
  --policy-arn arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole

# Wait for role propagation (~10s)
sleep 10

# Step 2: Package code
mkdir -p /tmp/$F && cd /tmp/$F
cat > lambda_function.py <<EOF
def lambda_handler(event, context):
    return {"statusCode": 200, "body": "Hello from aws-pilot!"}
EOF
zip -r function.zip lambda_function.py

# Step 3: Create function
ROLE_ARN=$(aws iam get-role --role-name $ROLE --query 'Role.Arn' --output text)
aws lambda create-function \
  --function-name $F \
  --runtime python3.12 \
  --role $ROLE_ARN \
  --handler lambda_function.lambda_handler \
  --zip-file fileb:///tmp/$F/function.zip \
  --timeout 10 \
  --memory-size 128 \
  --environment "Variables={ENV=prod}" \
  --tags ManagedBy=aws-pilot \
  --region $REGION
```

## Update code

```bash
cd /tmp/$F
zip -r function.zip lambda_function.py
aws lambda update-function-code \
  --function-name $F \
  --zip-file fileb://function.zip
```

## Update env vars

```bash
aws lambda update-function-configuration \
  --function-name $F \
  --environment "Variables={ENV=prod,API_KEY=abc123}"
```

## Add a public Function URL (HTTPS endpoint)

```bash
aws lambda create-function-url-config \
  --function-name $F \
  --auth-type NONE  # or AWS_IAM for sig-v4 auth
# Returns: https://abc123xyz.lambda-url.us-east-1.on.aws/

# Allow public invoke
aws lambda add-permission \
  --function-name $F \
  --statement-id FunctionURLAllowPublicAccess \
  --action lambda:InvokeFunctionUrl \
  --principal "*" \
  --function-url-auth-type NONE
```

## Add an EventBridge schedule (cron)

```bash
RULE=daily-${F}
aws events put-rule \
  --name $RULE \
  --schedule-expression "cron(0 12 * * ? *)" \
  --state ENABLED \
  --description "trigger ${F} daily at noon UTC"

aws lambda add-permission \
  --function-name $F \
  --statement-id ${RULE}-invoke \
  --action lambda:InvokeFunction \
  --principal events.amazonaws.com \
  --source-arn $(aws events describe-rule --name $RULE --query Arn --output text)

aws events put-targets \
  --rule $RULE \
  --targets "Id=1,Arn=$(aws lambda get-function --function-name $F --query Configuration.FunctionArn --output text)"
```

## Invoke (test)

```bash
aws lambda invoke \
  --function-name $F \
  --payload '{"key":"value"}' \
  --cli-binary-format raw-in-base64-out \
  /tmp/response.json
cat /tmp/response.json
```

## Constraints

- ALWAYS create a dedicated role per function (not shared)
- Default timeout: 10s. Default memory: 128MB. Increase only with user consent (cost grows linearly with memory)
- Function URL with `AuthType: NONE` is publicly invokable — warn user about cost/abuse
- Tag every function with `ManagedBy=aws-pilot`
- Refuse to log function code in chat if it contains hardcoded secrets — flag instead
- Lambda free tier: 1M req/mo + 400k GB-sec/mo. Monitor usage.
