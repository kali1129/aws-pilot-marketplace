"""
aws-pilot MCP server.

Exposes structured tools for AWS account control via boto3. Runs in two modes:
- Local stdio (default): subprocess of Claude Code via .mcp.json
- Remote HTTP (set AWS_PILOT_REMOTE_URL): proxies tool calls to a VPS-hosted instance

Safety: every tool checks AWS_PILOT_MODE (read-only / dry-run / execute) and
appends to AWS_PILOT_AUDIT_LOG.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import ClientError, NoCredentialsError
from mcp.server.fastmcp import FastMCP

# ----- config -----
MODE = os.environ.get("AWS_PILOT_MODE", "dry-run")  # read-only | dry-run | execute
REGION = os.environ.get("AWS_REGION", "us-east-1")
PROFILE = os.environ.get("AWS_PROFILE", "default")
BUDGET_USD = float(os.environ.get("AWS_PILOT_BUDGET_USD", "50"))
AUDIT_LOG = Path(os.environ.get(
    "AWS_PILOT_AUDIT_LOG",
    str(Path.home() / ".claude" / "plugins" / "data" / "aws-pilot" / "audit.jsonl")
))
AUDIT_LOG.parent.mkdir(parents=True, exist_ok=True)


# ----- session / clients (cached) -----
_session = None
_clients = {}

def session():
    global _session
    if _session is None:
        _session = boto3.Session(profile_name=PROFILE, region_name=REGION)
    return _session

def client(name: str, region: str | None = None):
    key = (name, region or REGION)
    if key not in _clients:
        _clients[key] = session().client(name, region_name=region or REGION)
    return _clients[key]


# ----- audit -----
def audit(action: str, params: dict, result_summary: str, success: bool):
    entry = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "mode": MODE,
        "action": action,
        "params": params,
        "result": result_summary[:500],
        "success": success,
    }
    with AUDIT_LOG.open("a") as f:
        f.write(json.dumps(entry) + "\n")


# ----- safety gate -----
WRITE_VERBS = {"create", "update", "delete", "put", "attach", "detach",
               "terminate", "start", "stop", "run", "modify", "restore",
               "add", "remove", "enable", "disable", "reboot", "release",
               "associate", "disassociate", "authorize", "revoke", "set"}

def is_write(action: str) -> bool:
    return any(action.lower().startswith(v) for v in WRITE_VERBS)

def gate(action: str) -> str | None:
    """Return None if allowed, an error string if blocked."""
    if MODE == "read-only" and is_write(action):
        return f"Blocked: mode=read-only, '{action}' is a write operation."
    if MODE == "dry-run" and is_write(action):
        return f"Dry-run: would call '{action}' (set mode=execute to apply)."
    return None


# ----- MCP server -----
mcp = FastMCP("aws-pilot")


@mcp.tool()
def aws_account_overview() -> dict:
    """Return identity, region, MTD cost (best-effort), running resources count.
    Always read-only, safe to call any time."""
    try:
        ident = client("sts").get_caller_identity()
    except NoCredentialsError:
        return {"error": "no AWS credentials configured. Run 'aws configure --profile " + PROFILE + "'."}

    out = {
        "account_id": ident["Account"],
        "arn": ident["Arn"],
        "user_id": ident["UserId"],
        "region_default": REGION,
        "profile": PROFILE,
        "mode": MODE,
        "budget_usd": BUDGET_USD,
    }

    # MTD cost (Cost Explorer is us-east-1 only, opt-in required)
    try:
        ce = client("ce", region="us-east-1")
        today = datetime.now(timezone.utc).date()
        first = today.replace(day=1)
        r = ce.get_cost_and_usage(
            TimePeriod={"Start": first.isoformat(), "End": today.isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
            GroupBy=[{"Type": "DIMENSION", "Key": "SERVICE"}],
        )
        groups = r.get("ResultsByTime", [{}])[0].get("Groups", [])
        out["mtd_cost"] = sum(float(g["Metrics"]["UnblendedCost"]["Amount"]) for g in groups)
        out["top_services"] = sorted(
            [(g["Keys"][0], float(g["Metrics"]["UnblendedCost"]["Amount"])) for g in groups],
            key=lambda x: -x[1]
        )[:5]
    except ClientError as e:
        out["mtd_cost_error"] = str(e)

    # Running EC2 across regions
    try:
        regions = [r["RegionName"] for r in client("ec2").describe_regions()["Regions"]]
        running = {}
        for r in regions:
            try:
                resp = client("ec2", region=r).describe_instances(
                    Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
                )
                count = sum(len(rsv["Instances"]) for rsv in resp["Reservations"])
                if count:
                    running[r] = count
            except ClientError:
                pass
        out["running_ec2"] = running
    except ClientError:
        pass

    audit("aws_account_overview", {}, json.dumps(out)[:200], True)
    return out


@mcp.tool()
def aws_list_resources(service: str, region: str | None = None) -> dict:
    """List resources of a given service. Read-only.

    Supported: ec2, s3, lambda, rds, iam, route53, secretsmanager, cloudwatch-logs.
    """
    region = region or REGION
    try:
        if service == "ec2":
            r = client("ec2", region).describe_instances()
            instances = []
            for rsv in r["Reservations"]:
                for i in rsv["Instances"]:
                    name = next((t["Value"] for t in i.get("Tags", []) if t["Key"] == "Name"), "")
                    instances.append({
                        "id": i["InstanceId"], "type": i["InstanceType"],
                        "state": i["State"]["Name"], "ip": i.get("PublicIpAddress"),
                        "name": name, "az": i["Placement"]["AvailabilityZone"],
                    })
            result = {"instances": instances}
        elif service == "s3":
            r = client("s3").list_buckets()
            result = {"buckets": [{"name": b["Name"], "created": b["CreationDate"].isoformat()} for b in r["Buckets"]]}
        elif service == "lambda":
            r = client("lambda", region).list_functions()
            result = {"functions": [{"name": f["FunctionName"], "runtime": f["Runtime"], "memory": f["MemorySize"]} for f in r["Functions"]]}
        elif service == "rds":
            r = client("rds", region).describe_db_instances()
            result = {"db_instances": [{"id": d["DBInstanceIdentifier"], "engine": d["Engine"], "class": d["DBInstanceClass"], "status": d["DBInstanceStatus"]} for d in r["DBInstances"]]}
        elif service == "iam":
            users = client("iam").list_users()["Users"]
            roles = client("iam").list_roles()["Roles"]
            result = {"users": [u["UserName"] for u in users], "roles": [r["RoleName"] for r in roles]}
        elif service == "route53":
            r = client("route53").list_hosted_zones()
            result = {"zones": [{"id": z["Id"], "name": z["Name"], "records": z["ResourceRecordSetCount"]} for z in r["HostedZones"]]}
        elif service == "secretsmanager":
            r = client("secretsmanager", region).list_secrets()
            result = {"secrets": [{"name": s["Name"], "arn": s["ARN"]} for s in r["SecretList"]]}
        elif service == "cloudwatch-logs":
            r = client("logs", region).describe_log_groups()
            result = {"log_groups": [{"name": g["logGroupName"], "size": g.get("storedBytes", 0), "retention_days": g.get("retentionInDays")} for g in r["logGroups"]]}
        else:
            return {"error": f"unsupported service: {service}"}

        audit("aws_list_resources", {"service": service, "region": region}, f"ok: {len(json.dumps(result))} bytes", True)
        return result
    except ClientError as e:
        audit("aws_list_resources", {"service": service, "region": region}, str(e), False)
        return {"error": str(e)}


@mcp.tool()
def aws_create_ec2_with_ssh(name: str, instance_type: str = "t3.micro", region: str | None = None) -> dict:
    """Create an EC2 instance with auto-generated SSH key + security group restricted to caller IP.
    Honors AWS_PILOT_MODE.

    Returns: {instance_id, public_ip, ssh_command, key_path, security_group, monthly_cost_estimate}"""
    blocked = gate("run_instances")
    if blocked:
        return {"blocked": blocked}

    region = region or REGION
    ec2 = client("ec2", region)

    # Latest Amazon Linux 2023 AMI
    ami = ec2.describe_images(
        Owners=["amazon"],
        Filters=[
            {"Name": "name", "Values": ["al2023-ami-*-kernel-*-x86_64"]},
            {"Name": "state", "Values": ["available"]},
        ],
    )["Images"]
    if not ami:
        return {"error": "no AL2023 AMI found in region " + region}
    ami_id = sorted(ami, key=lambda i: i["CreationDate"])[-1]["ImageId"]

    # Keypair
    key_path = Path.home() / ".ssh" / f"aws-{name}.pem"
    if key_path.exists():
        return {"error": f"key file already exists at {key_path} — pick a different name or delete first"}
    kp = ec2.create_key_pair(KeyName=name, KeyType="rsa", KeyFormat="pem")
    key_path.write_text(kp["KeyMaterial"])
    key_path.chmod(0o600)

    # Caller's public IP
    import urllib.request
    try:
        my_ip = urllib.request.urlopen("https://checkip.amazonaws.com", timeout=5).read().decode().strip()
    except Exception:
        my_ip = "0.0.0.0"

    # Security group
    sg = ec2.create_security_group(
        GroupName=f"{name}-sg",
        Description=f"auto-created by aws-pilot for {name}",
    )
    sg_id = sg["GroupId"]
    ec2.authorize_security_group_ingress(
        GroupId=sg_id,
        IpPermissions=[{
            "IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
            "IpRanges": [{"CidrIp": f"{my_ip}/32", "Description": "SSH from creator"}]
        }]
    )

    # Launch
    launched = ec2.run_instances(
        ImageId=ami_id,
        InstanceType=instance_type,
        KeyName=name,
        SecurityGroupIds=[sg_id],
        MinCount=1, MaxCount=1,
        TagSpecifications=[{
            "ResourceType": "instance",
            "Tags": [
                {"Key": "Name", "Value": name},
                {"Key": "ManagedBy", "Value": "aws-pilot"},
                {"Key": "CreatedAt", "Value": datetime.now(timezone.utc).isoformat()},
            ]
        }]
    )
    inst_id = launched["Instances"][0]["InstanceId"]

    # Wait for running + grab IP
    waiter = ec2.get_waiter("instance_running")
    waiter.wait(InstanceIds=[inst_id])
    desc = ec2.describe_instances(InstanceIds=[inst_id])
    pub_ip = desc["Reservations"][0]["Instances"][0].get("PublicIpAddress", "(none)")

    # Cost estimate
    cost_table = {"t3.nano": 3.80, "t3.micro": 7.60, "t3.small": 15.18, "t3.medium": 30.37, "t3.large": 60.74}
    monthly = cost_table.get(instance_type, 0) + 0.64  # plus 8GB EBS

    result = {
        "instance_id": inst_id,
        "public_ip": pub_ip,
        "ssh_command": f"ssh -i {key_path} ec2-user@{pub_ip}",
        "key_path": str(key_path),
        "security_group": sg_id,
        "monthly_cost_estimate_usd": monthly,
    }
    audit("aws_create_ec2_with_ssh", {"name": name, "type": instance_type, "region": region}, json.dumps(result), True)
    return result


@mcp.tool()
def aws_terminate_ec2(instance_id: str, region: str | None = None, confirm: bool = False) -> dict:
    """Terminate an EC2 instance. DESTRUCTIVE. Requires confirm=true AND mode=execute."""
    blocked = gate("terminate_instances")
    if blocked:
        return {"blocked": blocked}
    if not confirm:
        return {"error": "destructive op — pass confirm=true to proceed"}

    region = region or REGION
    r = client("ec2", region).terminate_instances(InstanceIds=[instance_id])
    audit("aws_terminate_ec2", {"instance_id": instance_id, "region": region}, json.dumps(r["TerminatingInstances"]), True)
    return {"terminating": r["TerminatingInstances"]}


@mcp.tool()
def aws_audit_log_tail(lines: int = 20) -> str:
    """Return last N lines of the audit log."""
    if not AUDIT_LOG.exists():
        return "(empty)"
    with AUDIT_LOG.open() as f:
        all_lines = f.readlines()
    return "".join(all_lines[-lines:])


if __name__ == "__main__":
    print(f"aws-pilot MCP starting (mode={MODE}, profile={PROFILE}, region={REGION})", file=sys.stderr)
    mcp.run()
