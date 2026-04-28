---
name: aws-vpc-network
description: Manage VPC, subnets, security groups, route tables, internet gateways. Use when user wants "private networking", "isolate my DB", "create a VPC", or asks about firewall rules. Sensible defaults: default VPC fine for hobby; new VPC only for production multi-tier.
---

# aws-vpc-network

Atomic skill: VPC + networking primitives. Read = safe. Create/modify require `mode: execute`.

## When to use what

- **Default VPC** (auto-created in every region): fine for personal/hobby use, 1-3 EC2 instances. Don't over-engineer.
- **New custom VPC**: only when you need (a) multi-tier prod (public ALB + private app + isolated DB), (b) VPC peering with another account, or (c) specific CIDR for VPN/Direct Connect.

## Read

```bash
aws ec2 describe-vpcs --output table
aws ec2 describe-subnets --output table
aws ec2 describe-security-groups --output json
aws ec2 describe-route-tables --output json
aws ec2 describe-internet-gateways
aws ec2 describe-nat-gateways
```

## Create production-ready VPC (3-AZ, public + private subnets)

Use this layout:
```
VPC: 10.0.0.0/16
├── Public  10.0.1.0/24  (us-east-1a)  → IGW
├── Public  10.0.2.0/24  (us-east-1b)  → IGW
├── Public  10.0.3.0/24  (us-east-1c)  → IGW
├── Private 10.0.11.0/24 (us-east-1a)  → NAT
├── Private 10.0.12.0/24 (us-east-1b)  → NAT
└── Private 10.0.13.0/24 (us-east-1c)  → NAT
```

Cost: NAT Gateway is **$32.40/mo + $0.045/GB processed**. Big! Warn user.
Alternative for cheap dev: skip NAT, only use public subnets + SGs.

```bash
# Step 1: VPC
VPC=$(aws ec2 create-vpc --cidr-block 10.0.0.0/16 \
  --tag-specifications "ResourceType=vpc,Tags=[{Key=Name,Value=prod-vpc},{Key=ManagedBy,Value=aws-pilot}]" \
  --query 'Vpc.VpcId' --output text)

aws ec2 modify-vpc-attribute --vpc-id $VPC --enable-dns-hostnames

# Step 2: Internet Gateway + attach
IGW=$(aws ec2 create-internet-gateway \
  --tag-specifications "ResourceType=internet-gateway,Tags=[{Key=Name,Value=prod-igw},{Key=ManagedBy,Value=aws-pilot}]" \
  --query 'InternetGateway.InternetGatewayId' --output text)
aws ec2 attach-internet-gateway --internet-gateway-id $IGW --vpc-id $VPC

# Step 3: Public subnets (3 AZs)
for i in 1 2 3; do
  AZ=$(aws ec2 describe-availability-zones --query "AvailabilityZones[$((i-1))].ZoneName" --output text)
  aws ec2 create-subnet \
    --vpc-id $VPC \
    --cidr-block 10.0.${i}.0/24 \
    --availability-zone $AZ \
    --tag-specifications "ResourceType=subnet,Tags=[{Key=Name,Value=public-${AZ}},{Key=Tier,Value=public}]"
done

# Step 4: Public route table → IGW
RT_PUB=$(aws ec2 create-route-table --vpc-id $VPC \
  --tag-specifications "ResourceType=route-table,Tags=[{Key=Name,Value=rt-public}]" \
  --query 'RouteTable.RouteTableId' --output text)
aws ec2 create-route --route-table-id $RT_PUB --destination-cidr-block 0.0.0.0/0 --gateway-id $IGW

# Associate public subnets with public RT
for SUBNET in $(aws ec2 describe-subnets --filters "Name=vpc-id,Values=$VPC" "Name=tag:Tier,Values=public" --query 'Subnets[].SubnetId' --output text); do
  aws ec2 associate-route-table --route-table-id $RT_PUB --subnet-id $SUBNET
done

# (Skip private subnets + NAT for now to save cost; add if user asks)
```

## Security groups (firewalls)

Always think "what is this SG protecting?":

```bash
# Web tier: HTTPS from internet, no SSH from internet
aws ec2 create-security-group --group-name web-tier --description "ALB + web servers" --vpc-id $VPC
aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 443 --cidr 0.0.0.0/0
aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 80 --cidr 0.0.0.0/0

# App tier: only from web SG
aws ec2 authorize-security-group-ingress --group-id $APP_SG --protocol tcp --port 8080 --source-group $WEB_SG

# DB tier: only from app SG
aws ec2 authorize-security-group-ingress --group-id $DB_SG --protocol tcp --port 5432 --source-group $APP_SG

# SSH: only from your current IP
MY_IP=$(curl -s https://checkip.amazonaws.com)
aws ec2 authorize-security-group-ingress --group-id $SG --protocol tcp --port 22 --cidr ${MY_IP}/32
```

## Constraints

- Default VPC is fine for most personal use; don't create custom VPC unless needed
- NEVER `0.0.0.0/0` on SSH(22), RDP(3389), or DB ports — always restrict
- ALWAYS attach `ManagedBy=aws-pilot` tag
- Confirm before creating NAT Gateway (cost warning)
- Confirm before deleting any VPC (lots of dependencies)
