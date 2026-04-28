---
name: aws-rds-manage
description: Provision, list, snapshot, and manage RDS databases (Postgres, MySQL, MariaDB). Use when user wants "a managed database", "Postgres on AWS", or asks about backups. Sets up VPC SG correctly so the DB is reachable from the user's EC2 but not the public internet.
---

# aws-rds-manage

Atomic skill: RDS instance lifecycle. Read = safe. Create/modify/delete require `mode: execute` + cost confirmation.

## Read

```bash
aws rds describe-db-instances --output json
aws rds describe-db-snapshots --output json
aws rds describe-db-subnet-groups
aws rds describe-db-parameter-groups
```

## Create a Postgres instance (private)

```bash
DB=daurel-db-prod
ENGINE=postgres
ENGINE_VERSION=16.3
INSTANCE_CLASS=db.t4g.micro       # 2 vCPU, 1GB RAM, ~$12/mo
ALLOCATED_GB=20                    # 20GB gp3, ~$2.30/mo
USER_NAME=daurel_admin
PASSWORD=$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)
EC2_SG=sg-abc123                   # SG of the EC2 that will connect to this DB

# Step 1: Subnet group (use default VPC subnets unless user wants private)
DEFAULT_VPC=$(aws ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId' --output text)
SUBNET_IDS=$(aws ec2 describe-subnets --filters Name=vpc-id,Values=$DEFAULT_VPC --query 'Subnets[].SubnetId' --output text)

aws rds create-db-subnet-group \
  --db-subnet-group-name ${DB}-subnet \
  --db-subnet-group-description "auto-created by aws-pilot" \
  --subnet-ids $SUBNET_IDS

# Step 2: SG for DB — only allow EC2_SG to connect on port 5432
DB_SG=$(aws ec2 create-security-group \
  --group-name ${DB}-sg \
  --description "RDS access from app SG only" \
  --vpc-id $DEFAULT_VPC \
  --query 'GroupId' --output text)

aws ec2 authorize-security-group-ingress \
  --group-id $DB_SG \
  --protocol tcp --port 5432 \
  --source-group $EC2_SG

# Step 3: Create the DB
aws rds create-db-instance \
  --db-instance-identifier $DB \
  --engine $ENGINE \
  --engine-version $ENGINE_VERSION \
  --db-instance-class $INSTANCE_CLASS \
  --allocated-storage $ALLOCATED_GB \
  --storage-type gp3 \
  --storage-encrypted \
  --master-username $USER_NAME \
  --master-user-password "$PASSWORD" \
  --db-subnet-group-name ${DB}-subnet \
  --vpc-security-group-ids $DB_SG \
  --no-publicly-accessible \
  --backup-retention-period 7 \
  --preferred-backup-window "03:00-04:00" \
  --preferred-maintenance-window "Sun:04:00-Sun:05:00" \
  --auto-minor-version-upgrade \
  --tags Key=ManagedBy,Value=aws-pilot Key=Engine,Value=$ENGINE

# Save password to Secrets Manager
aws secretsmanager create-secret \
  --name "rds/${DB}/master" \
  --secret-string "{\"username\":\"${USER_NAME}\",\"password\":\"${PASSWORD}\"}"

# Wait for available
aws rds wait db-instance-available --db-instance-identifier $DB

ENDPOINT=$(aws rds describe-db-instances --db-instance-identifier $DB \
  --query 'DBInstances[0].Endpoint.Address' --output text)
echo "DB ready. Connect from EC2: psql -h $ENDPOINT -U $USER_NAME -d postgres"
echo "Password stored in Secrets Manager: rds/${DB}/master"
```

## Cost preview (us-east-1, on-demand, single-AZ)

| Class           | vCPU | RAM | $/hr    | $/mo (730h) |
|-----------------|------|-----|---------|-------------|
| db.t4g.micro    | 2    | 1GB | $0.016  | $11.68      |
| db.t4g.small    | 2    | 2GB | $0.032  | $23.36      |
| db.t4g.medium   | 2    | 4GB | $0.065  | $47.45      |

Plus storage gp3: $0.115/GB-mo. Plus backups: free up to size of DB. Plus data transfer out: $0.09/GB after 100GB free.

## Snapshot / restore

```bash
# Manual snapshot (free until your DB is deleted)
aws rds create-db-snapshot \
  --db-instance-identifier $DB \
  --db-snapshot-identifier ${DB}-snap-$(date +%Y%m%d)

# Restore from snapshot to a new instance
aws rds restore-db-instance-from-db-snapshot \
  --db-instance-identifier ${DB}-restored \
  --db-snapshot-identifier ${DB}-snap-20260428
```

## Delete (DESTRUCTIVE — hook will block)

```bash
# Always take a final snapshot
aws rds delete-db-instance \
  --db-instance-identifier $DB \
  --final-db-snapshot-identifier ${DB}-final-$(date +%Y%m%d)
# (or --skip-final-snapshot if user explicitly accepts data loss)
```

## Constraints

- DEFAULT to private (no public IP), encrypted storage, daily backups
- ALWAYS store master password in Secrets Manager, never in chat history
- Refuse `db.r5.*` / `db.m5.*` classes unless user explicitly asks (they're expensive)
- Hook blocks `delete-db-instance` without `--final-db-snapshot-identifier` unless user confirms
- Tag with `ManagedBy=aws-pilot, Engine=<engine>`
- Multi-AZ doubles cost; only enable if user asks for HA
