---
name: aws-ec2-manage
description: Provision, list, start, stop, terminate, and inspect EC2 instances. Use when the user wants to "create a VPS", "spin up a server", "stop my instance", or asks about running EC2. Generates SSH keypairs, configures security groups, and gives the user a ready-to-SSH instance.
---

# aws-ec2-manage

Atomic skill: full EC2 lifecycle. Read-only by default; create/terminate require `mode: execute` + confirmation.

## Read commands (always safe)

```bash
# List all instances across regions
for r in $(aws ec2 describe-regions --query 'Regions[].RegionName' --output text); do
  aws ec2 describe-instances --region $r \
    --query 'Reservations[].Instances[].[InstanceId,InstanceType,State.Name,PublicIpAddress,Tags[?Key==`Name`]|[0].Value]' \
    --output table
done

# Existing keypairs
aws ec2 describe-key-pairs --output json

# Existing security groups
aws ec2 describe-security-groups --output json

# Default VPC
aws ec2 describe-vpcs --filters Name=isDefault,Values=true
```

## Create a new VPS (full workflow)

When the user says "create a VPS" or "spin up a server", run this end-to-end:

```bash
NAME=daurel-prod-01            # ask user for name
INSTANCE_TYPE=t3.micro         # default; ask if heavier needed
REGION=${user_config.default_region}
AMI=$(aws ec2 describe-images --owners amazon \
  --filters "Name=name,Values=al2023-ami-*-kernel-*-x86_64" \
            "Name=state,Values=available" \
  --query 'sort_by(Images,&CreationDate)[-1].ImageId' --output text \
  --region $REGION)

# Step 1: SSH keypair (saves private key locally with 0600)
KEY_PATH="$HOME/.ssh/aws-${NAME}.pem"
aws ec2 create-key-pair \
  --key-name "${NAME}" \
  --key-type rsa --key-format pem \
  --query 'KeyMaterial' --output text \
  --region $REGION > "$KEY_PATH"
chmod 600 "$KEY_PATH"

# Step 2: Security group (SSH from user's current IP only)
MY_IP=$(curl -s https://checkip.amazonaws.com)
SG_ID=$(aws ec2 create-security-group \
  --group-name "${NAME}-sg" \
  --description "auto-created by aws-pilot for ${NAME}" \
  --region $REGION --query 'GroupId' --output text)
aws ec2 authorize-security-group-ingress \
  --group-id $SG_ID \
  --protocol tcp --port 22 \
  --cidr "${MY_IP}/32" \
  --region $REGION

# Step 3: Launch
INSTANCE_ID=$(aws ec2 run-instances \
  --image-id $AMI \
  --instance-type $INSTANCE_TYPE \
  --key-name "${NAME}" \
  --security-group-ids $SG_ID \
  --tag-specifications "ResourceType=instance,Tags=[{Key=Name,Value=${NAME}},{Key=ManagedBy,Value=aws-pilot}]" \
  --region $REGION --query 'Instances[0].InstanceId' --output text)

# Step 4: Wait for running + grab IP
aws ec2 wait instance-running --instance-ids $INSTANCE_ID --region $REGION
PUB_IP=$(aws ec2 describe-instances --instance-ids $INSTANCE_ID \
  --query 'Reservations[0].Instances[0].PublicIpAddress' --output text \
  --region $REGION)

# Step 5: Print SSH command
echo "Instance ready: $INSTANCE_ID at $PUB_IP"
echo "SSH: ssh -i $KEY_PATH ec2-user@$PUB_IP"
```

## Stop / start / terminate

```bash
# Stop (preserves disk; resumable; no compute charge but EBS still charged)
aws ec2 stop-instances --instance-ids i-...

# Start (already-stopped instance)
aws ec2 start-instances --instance-ids i-...

# Terminate (destroys disk; DESTRUCTIVE)
# Hook will block this unless user_config.require_confirm_destructive=false OR user confirms
aws ec2 terminate-instances --instance-ids i-...
```

## Cost preview before launch

| Type        | vCPU | RAM   | $/hr (us-east-1) | $/mo (730h) |
|-------------|------|-------|------------------|-------------|
| t3.nano     | 2    | 0.5GB | $0.0052          | $3.80       |
| t3.micro    | 2    | 1GB   | $0.0104          | $7.60       |
| t3.small    | 2    | 2GB   | $0.0208          | $15.18      |
| t3.medium   | 2    | 4GB   | $0.0416          | $30.37      |
| t3.large    | 2    | 8GB   | $0.0832          | $60.74      |

Plus EBS: gp3 8GB ≈ $0.64/mo. Plus data transfer out: $0.09/GB after 100GB free.

Refuse if estimated monthly cost > (`${user_config.monthly_budget_usd}` − current MTD).

## Constraints

- ALWAYS create keypair with name=instance-name, save to `~/.ssh/aws-<name>.pem` with 0600
- ALWAYS restrict SG to user's current IP, NEVER `0.0.0.0/0` for SSH
- Tag everything with `ManagedBy=aws-pilot` for cleanup later
- Confirm before terminate (hook enforces)
- Show cost preview before launch
