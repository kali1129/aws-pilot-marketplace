---
name: aws-deploy-vps
description: Provision a VPS-style EC2 instance with all the things a user actually wants — Ubuntu/Amazon Linux, swap, Docker installed, SSH ready, optional Nginx + TLS via Let's Encrypt, optional domain pointing via Route53. Use when the user says "I need a VPS" or "host this on AWS".
---

# aws-deploy-vps

Composite skill that wraps `aws-ec2-manage` with sensible production defaults. Output is a ready-to-use server.

## Defaults (override via user dialog)

- AMI: latest Amazon Linux 2023 (or Ubuntu 22.04 if user prefers apt)
- Type: `t3.small` (2 vCPU, 2GB RAM, $15.18/mo)
- Disk: 16GB gp3
- Region: `${user_config.default_region}`
- Security group: SSH(22) from user IP, HTTPS(443) from anywhere if web; HTTP(80) only for cert challenges
- User-data script (cloud-init): updates, installs docker + docker-compose, creates swap, installs nginx if web=true

## User-data script (runs on first boot)

```bash
#!/bin/bash
set -eux

# System update
dnf update -y || apt-get update -y && apt-get upgrade -y

# Swap (4GB) — useful for small instances running Docker
fallocate -l 4G /swapfile
chmod 600 /swapfile
mkswap /swapfile
swapon /swapfile
echo '/swapfile none swap sw 0 0' >> /etc/fstab

# Docker
if command -v dnf >/dev/null; then
  dnf install -y docker
  systemctl enable --now docker
  usermod -aG docker ec2-user
else
  apt-get install -y docker.io
  systemctl enable --now docker
  usermod -aG docker ubuntu
fi

# Docker compose v2 plugin
DOCKER_CONFIG=${DOCKER_CONFIG:-/usr/local/lib/docker}
mkdir -p $DOCKER_CONFIG/cli-plugins
curl -sSL https://github.com/docker/compose/releases/download/v2.27.0/docker-compose-linux-x86_64 \
  -o $DOCKER_CONFIG/cli-plugins/docker-compose
chmod +x $DOCKER_CONFIG/cli-plugins/docker-compose

# Optional: nginx + certbot if web=true
if [ "${WEB_SETUP:-false}" = "true" ]; then
  if command -v dnf >/dev/null; then
    dnf install -y nginx certbot python3-certbot-nginx
  else
    apt-get install -y nginx certbot python3-certbot-nginx
  fi
  systemctl enable --now nginx
fi

# Marker file for aws-pilot to know cloud-init finished
touch /var/lib/aws-pilot.ready
```

## Workflow

1. Collect inputs from user:
   - Name (required, used for keypair + SG + tag)
   - Purpose: `general | web | db` (drives type + ports)
   - Domain (optional, if user wants TLS)
2. Pick instance type by purpose:
   - general → t3.small
   - web → t3.small + ports 80/443
   - db → t3.medium + private only (no public IP)
3. Show cost preview, ask user to confirm
4. Run `aws-ec2-manage` create flow with the user-data above
5. After `wait instance-running`, also wait for `/var/lib/aws-pilot.ready`:
   ```bash
   ssh -i $KEY -o StrictHostKeyChecking=no ec2-user@$PUB_IP \
     'until [ -f /var/lib/aws-pilot.ready ]; do sleep 5; done'
   ```
6. If domain provided, create Route53 A record (call `aws-route53-dns`)
7. If web=true and domain set, run certbot:
   ```bash
   ssh -i $KEY ec2-user@$PUB_IP \
     "sudo certbot --nginx --non-interactive --agree-tos -m $USER_EMAIL -d $DOMAIN"
   ```
8. Print connection info:
   ```
   VPS ready!
   IP: 1.2.3.4
   SSH: ssh -i ~/.ssh/aws-foo.pem ec2-user@1.2.3.4
   URL: https://foo.example.com (if domain set)
   Tag: ManagedBy=aws-pilot, Purpose=web
   ```

## Constraints

- Refuse if cost would exceed remaining budget
- ALWAYS user-data the cloud-init via base64 (use `--user-data` arg or file)
- ALWAYS save private key to `~/.ssh/aws-<name>.pem` with 0600
- ALWAYS tag `ManagedBy=aws-pilot, Purpose=<purpose>` for cleanup
- If domain in Route53 doesn't exist as a hosted zone, halt and offer to create it
- Never open SSH(22) to 0.0.0.0/0 — always /32 user IP
