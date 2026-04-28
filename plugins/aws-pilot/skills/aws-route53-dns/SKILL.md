---
name: aws-route53-dns
description: Manage DNS via Route53 — create hosted zones, add A/AAAA/CNAME/MX/TXT records, point a domain to an EC2 instance, ALB, or CloudFront distribution. Use when user buys a domain or wants to point an existing one at an AWS resource.
---

# aws-route53-dns

Atomic skill: Route53 hosted zones + records. Read = safe; writes require `mode: execute`.

## Read

```bash
aws route53 list-hosted-zones --output json
aws route53 list-resource-record-sets --hosted-zone-id Z123ABC --output json
```

## Create a hosted zone for a new domain

```bash
DOMAIN=example.com
aws route53 create-hosted-zone \
  --name $DOMAIN \
  --caller-reference "aws-pilot-$(date +%s)" \
  --hosted-zone-config Comment="created by aws-pilot",PrivateZone=false

# Returned NameServers — user must update these at the registrar (GoDaddy/Namecheap/etc)
aws route53 get-hosted-zone --id /hostedzone/Z123ABC \
  --query 'DelegationSet.NameServers' --output table
```

After this, tell the user:
```
Update your domain's nameservers at the registrar to:
  ns-123.awsdns-00.com
  ns-456.awsdns-01.net
  ns-789.awsdns-02.co.uk
  ns-012.awsdns-03.org

Propagation can take 1-48h. Check with: dig +short NS example.com
```

## Add an A record (point domain to EC2 IP)

```bash
ZONE_ID=Z123ABC
DOMAIN=example.com
EC2_IP=1.2.3.4

cat > /tmp/change.json <<EOF
{
  "Comment": "aws-pilot: A record for ${DOMAIN}",
  "Changes": [{
    "Action": "UPSERT",
    "ResourceRecordSet": {
      "Name": "${DOMAIN}",
      "Type": "A",
      "TTL": 300,
      "ResourceRecords": [{"Value": "${EC2_IP}"}]
    }
  }]
}
EOF

aws route53 change-resource-record-sets \
  --hosted-zone-id $ZONE_ID \
  --change-batch file:///tmp/change.json
```

## Alias to ALB / CloudFront / S3 website

```bash
# CloudFront alias (no IP needed, AWS resolves it)
cat > /tmp/alias.json <<EOF
{
  "Changes": [{
    "Action": "UPSERT",
    "ResourceRecordSet": {
      "Name": "www.example.com",
      "Type": "A",
      "AliasTarget": {
        "HostedZoneId": "Z2FDTNDATAQYW2",
        "DNSName": "d111111abcdef8.cloudfront.net",
        "EvaluateTargetHealth": false
      }
    }
  }]
}
EOF
# Note: CloudFront's hosted zone ID is always Z2FDTNDATAQYW2
```

Common alias HostedZoneIds:
- CloudFront: `Z2FDTNDATAQYW2`
- ALB/NLB: region-specific, get from `describe-load-balancers`
- S3 website: region-specific (look up in AWS docs)

## Add common records

```bash
# CNAME (e.g., www → root)
# Type=CNAME, Name=www.example.com, Value=example.com

# MX (email)
# Type=MX, Name=example.com, Value="10 mail.example.com"

# TXT (verification, SPF, DKIM)
# Type=TXT, Name=example.com, Value="\"v=spf1 include:_spf.google.com ~all\""
```

## Constraints

- ALWAYS use UPSERT (idempotent), never CREATE (errors if record exists)
- Confirm before delete records
- Hosted zone costs $0.50/mo + $0.40 per million queries. Warn user.
- Health checks cost extra ($0.50/mo each); only set up if user asks
- Tag hosted zone with `ManagedBy=aws-pilot`
