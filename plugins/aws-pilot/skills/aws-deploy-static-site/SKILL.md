---
name: aws-deploy-static-site
description: Deploy a static website (HTML/CSS/JS, React build, Hugo/Jekyll output) to AWS using S3 + CloudFront + Route53 + ACM. Use when user has a `dist/` or `build/` folder and wants it on a custom domain with HTTPS.
---

# aws-deploy-static-site

Composite skill: S3 + CloudFront + ACM + Route53. Cheaper and faster than EC2 for static content.

## Architecture

```
User → CloudFront (CDN, HTTPS) → S3 (origin, private) 
                ↑
              ACM cert (free, auto-renew)
                ↑
        Route53 alias (yourdomain.com → CF distribution)
```

Total cost for low-traffic site: ~$0.50-2.00/mo. Compare to EC2 t3.small at $15/mo.

## Workflow

```bash
DOMAIN=mysite.com
SITE_DIR=./build              # output of `npm run build` etc
BUCKET=mysite-static-$(date +%s)
REGION=us-east-1              # ACM cert MUST be in us-east-1 for CloudFront

# Step 1: Bucket (PRIVATE — CloudFront uses OAC to read it)
aws s3api create-bucket --bucket $BUCKET --region $REGION
aws s3api put-public-access-block --bucket $BUCKET \
  --public-access-block-configuration "BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true"
aws s3 sync $SITE_DIR s3://$BUCKET/ --delete

# Step 2: ACM cert (in us-east-1!)
CERT_ARN=$(aws acm request-certificate \
  --domain-name $DOMAIN \
  --subject-alternative-names "www.$DOMAIN" \
  --validation-method DNS \
  --region us-east-1 \
  --query CertificateArn --output text)

# ACM returns DNS records that need to go in Route53 for validation
# (poll describe-certificate until ResourceRecord shows up)
sleep 30
aws acm describe-certificate --certificate-arn $CERT_ARN --region us-east-1 \
  --query 'Certificate.DomainValidationOptions[0].ResourceRecord'
# Then create those records in Route53 (use aws-route53-dns skill)
# ACM polls every 60s and validates automatically once DNS is correct

# Wait for validation (can take a few minutes)
aws acm wait certificate-validated --certificate-arn $CERT_ARN --region us-east-1

# Step 3: Origin Access Control (OAC) — modern way to let CloudFront read private S3
OAC_ID=$(aws cloudfront create-origin-access-control \
  --origin-access-control-config "Name=${BUCKET}-oac,Description=for ${DOMAIN},SigningProtocol=sigv4,SigningBehavior=always,OriginAccessControlOriginType=s3" \
  --query 'OriginAccessControl.Id' --output text)

# Step 4: CloudFront distribution
cat > /tmp/cf-config.json <<EOF
{
  "CallerReference": "$(date +%s)",
  "Comment": "static site for $DOMAIN",
  "Aliases": {"Quantity": 2, "Items": ["$DOMAIN", "www.$DOMAIN"]},
  "Origins": {"Quantity": 1, "Items": [{
    "Id": "s3-origin",
    "DomainName": "${BUCKET}.s3.${REGION}.amazonaws.com",
    "S3OriginConfig": {"OriginAccessIdentity": ""},
    "OriginAccessControlId": "${OAC_ID}"
  }]},
  "DefaultRootObject": "index.html",
  "DefaultCacheBehavior": {
    "TargetOriginId": "s3-origin",
    "ViewerProtocolPolicy": "redirect-to-https",
    "CachePolicyId": "658327ea-f89d-4fab-a63d-7e88639e58f6",
    "Compress": true,
    "AllowedMethods": {"Quantity": 2, "Items": ["GET", "HEAD"]}
  },
  "ViewerCertificate": {
    "ACMCertificateArn": "${CERT_ARN}",
    "SSLSupportMethod": "sni-only",
    "MinimumProtocolVersion": "TLSv1.2_2021"
  },
  "PriceClass": "PriceClass_100",
  "Enabled": true
}
EOF

CF_ID=$(aws cloudfront create-distribution \
  --distribution-config file:///tmp/cf-config.json \
  --query 'Distribution.Id' --output text)

CF_DOMAIN=$(aws cloudfront get-distribution --id $CF_ID \
  --query 'Distribution.DomainName' --output text)

# Step 5: Bucket policy to allow OAC reads
ACCT=$(aws sts get-caller-identity --query Account --output text)
cat > /tmp/bucket-policy.json <<EOF
{"Version":"2012-10-17","Statement":[{
  "Sid":"AllowCloudFrontOAC","Effect":"Allow",
  "Principal":{"Service":"cloudfront.amazonaws.com"},
  "Action":"s3:GetObject",
  "Resource":"arn:aws:s3:::${BUCKET}/*",
  "Condition":{"StringEquals":{"AWS:SourceArn":"arn:aws:cloudfront::${ACCT}:distribution/${CF_ID}"}}
}]}
EOF
aws s3api put-bucket-policy --bucket $BUCKET --policy file:///tmp/bucket-policy.json

# Step 6: Route53 — alias yourdomain.com → CloudFront
ZONE_ID=$(aws route53 list-hosted-zones-by-name --dns-name $DOMAIN \
  --query 'HostedZones[0].Id' --output text | sed 's|/hostedzone/||')
cat > /tmp/r53-alias.json <<EOF
{"Changes":[{"Action":"UPSERT","ResourceRecordSet":{
  "Name":"${DOMAIN}","Type":"A",
  "AliasTarget":{
    "HostedZoneId":"Z2FDTNDATAQYW2",
    "DNSName":"${CF_DOMAIN}",
    "EvaluateTargetHealth":false
  }
}}]}
EOF
aws route53 change-resource-record-sets --hosted-zone-id $ZONE_ID --change-batch file:///tmp/r53-alias.json

# Step 7: Wait for CF deploy (~15-20 min)
aws cloudfront wait distribution-deployed --id $CF_ID

echo "Live at: https://$DOMAIN (also https://www.$DOMAIN)"
```

## Update site (re-deploy)

```bash
aws s3 sync $SITE_DIR s3://$BUCKET/ --delete --cache-control "max-age=3600"

# Invalidate CloudFront cache so new files show
aws cloudfront create-invalidation --distribution-id $CF_ID --paths "/*"
```

## Constraints

- ACM cert MUST be in us-east-1 (CloudFront requirement)
- ALWAYS use OAC (modern) not OAI (legacy) for S3 origin
- Always `--cache-control` on sync — html short, assets long (use hashed filenames)
- Tag everything: `ManagedBy=aws-pilot, Site=<domain>`
- Cost: free tier 1TB/mo CloudFront + 50GB S3. After that ~$0.085/GB
