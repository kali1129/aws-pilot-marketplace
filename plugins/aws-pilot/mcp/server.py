"""
aws-pilot MCP server.

Exposes structured tools for AWS account control via boto3. Runs in two modes:
- Local stdio (default): subprocess of Claude Code via .mcp.json
- Remote HTTP (set AWS_PILOT_REMOTE_URL): proxies tool calls to a VPS-hosted instance

Safety: every tool checks AWS_PILOT_MODE (read-only / dry-run / execute), wraps
boto3 calls in try/except so credential / network / quota failures return as
structured errors instead of crashing the MCP transport, and appends to
AWS_PILOT_AUDIT_LOG.
"""

import json
import os
import sys
import functools
import traceback
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import boto3
from botocore.exceptions import (
    ClientError,
    NoCredentialsError,
    EndpointConnectionError,
    PartialCredentialsError,
    ProfileNotFound,
    BotoCoreError,
)
from mcp.server.fastmcp import FastMCP

# ----- config -----
MODE = os.environ.get("AWS_PILOT_MODE", "dry-run")  # read-only | dry-run | execute
REGION = os.environ.get("AWS_REGION", "us-east-1")
PROFILE = os.environ.get("AWS_PROFILE", "default")
BUDGET_USD = float(os.environ.get("AWS_PILOT_BUDGET_USD", "50"))


def _resolve_audit_path() -> Path:
    """Best-effort resolution of audit log path. Falls back to user temp if unwritable."""
    raw = os.environ.get("AWS_PILOT_AUDIT_LOG", "")
    if raw and "${" not in raw:  # CLAUDE_PLUGIN_DATA may be passed literal — fall back
        candidate = Path(raw)
    else:
        # default: per-user data dir under .claude
        candidate = Path.home() / ".claude" / "plugins" / "data" / "aws-pilot" / "audit.jsonl"
    try:
        candidate.parent.mkdir(parents=True, exist_ok=True)
        return candidate
    except (OSError, PermissionError):
        # last resort: temp
        import tempfile
        fallback = Path(tempfile.gettempdir()) / "aws-pilot-audit.jsonl"
        return fallback


AUDIT_LOG = _resolve_audit_path()


# ----- session / clients (cached) -----
_session = None
_clients: dict = {}


def _list_profiles() -> list:
    """Return available profile names, or [] if AWS config can't be read."""
    try:
        return list(boto3.Session().available_profiles)
    except Exception:
        return []


def _has_env_creds() -> bool:
    return bool(os.environ.get("AWS_ACCESS_KEY_ID"))


def _creds_problem() -> str | None:
    """Return None if creds look usable, else a clear setup message."""
    if PROFILE in _list_profiles():
        return None
    if _has_env_creds():
        return None  # env vars supersede profile
    return (
        f"No AWS credentials available for profile '{PROFILE}'.\n"
        f"Setup:\n"
        f"  1. aws configure --profile {PROFILE}\n"
        f"  2. /plugin config aws-pilot aws_profile={PROFILE}\n"
        f"Or set AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY env vars before launching Claude."
    )


def session():
    """Build a boto3 session. Caller must ensure creds are available (use _creds_problem first)."""
    global _session
    if _session is None:
        if PROFILE in _list_profiles():
            _session = boto3.Session(profile_name=PROFILE, region_name=REGION)
        else:
            # No matching profile — temporarily strip AWS_PROFILE env so boto3 doesn't auto-pick it
            saved = os.environ.pop("AWS_PROFILE", None)
            try:
                _session = boto3.Session(region_name=REGION)
            finally:
                if saved is not None:
                    os.environ["AWS_PROFILE"] = saved
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
        "result": str(result_summary)[:500],
        "success": success,
    }
    try:
        with AUDIT_LOG.open("a", encoding="utf-8") as f:
            f.write(json.dumps(entry, default=str) + "\n")
    except (OSError, PermissionError):
        # never let audit failure crash the tool
        pass


# ----- safety gate -----
WRITE_VERBS = {
    "create", "update", "delete", "put", "attach", "detach",
    "terminate", "start", "stop", "run", "modify", "restore",
    "add", "remove", "enable", "disable", "reboot", "release",
    "associate", "disassociate", "authorize", "revoke",
    "register", "deregister", "cancel", "import", "export",
}


def is_write(action: str) -> bool:
    """Classify an action name (snake_case verb) as write or read."""
    head = action.lower().split("_", 1)[0]
    return head in WRITE_VERBS


def gate(action: str) -> str | None:
    """Return None if allowed, an error string if blocked by current MODE."""
    if MODE == "read-only" and is_write(action):
        return f"Blocked: mode=read-only, '{action}' is a write operation. Set mode=execute to apply."
    if MODE == "dry-run" and is_write(action):
        return f"Dry-run: would call '{action}'. Set mode=execute to apply."
    return None


def safe_tool(action_label: str):
    """Decorator: pre-check creds, then catch boto/MCP errors and return structured error dicts."""
    def decorator(fn):
        @functools.wraps(fn)
        def wrapper(*args, **kwargs):
            # Pre-check: bail early with helpful message if no creds.
            # (`aws_audit_log_tail` is the only tool that doesn't touch AWS — let it through.)
            if action_label != "aws_audit_log_tail":
                problem = _creds_problem()
                if problem:
                    audit(action_label, kwargs, problem, False)
                    return {"error": problem, "kind": "no_credentials"}
            try:
                result = fn(*args, **kwargs)
                if isinstance(result, dict) and "error" in result:
                    audit(action_label, kwargs, result["error"], False)
                else:
                    audit(action_label, kwargs, "ok", True)
                return result
            except (NoCredentialsError, ProfileNotFound) as e:
                msg = (
                    f"No AWS credentials available for profile '{PROFILE}'. "
                    f"Set up by running: aws configure --profile {PROFILE}\n"
                    f"Then in Claude: /plugin config aws-pilot aws_profile={PROFILE}\n"
                    f"(detail: {e})"
                )
                audit(action_label, kwargs, msg, False)
                return {"error": msg, "kind": "no_credentials"}
            except PartialCredentialsError as e:
                msg = f"Incomplete AWS credentials: {e}"
                audit(action_label, kwargs, msg, False)
                return {"error": msg, "kind": "partial_credentials"}
            except EndpointConnectionError as e:
                msg = f"Cannot reach AWS endpoint: {e}"
                audit(action_label, kwargs, msg, False)
                return {"error": msg, "kind": "endpoint"}
            except ClientError as e:
                code = e.response.get("Error", {}).get("Code", "ClientError")
                msg = e.response.get("Error", {}).get("Message", str(e))
                audit(action_label, kwargs, f"{code}: {msg}", False)
                return {"error": msg, "kind": "aws_client_error", "code": code}
            except BotoCoreError as e:
                msg = f"boto core error: {e}"
                audit(action_label, kwargs, msg, False)
                return {"error": msg, "kind": "botocore"}
            except Exception as e:
                # last-resort: surface but don't crash transport
                tb = traceback.format_exc().splitlines()[-3:]
                msg = f"Unexpected: {e}"
                audit(action_label, kwargs, msg + " | " + " ".join(tb), False)
                return {"error": msg, "kind": "internal", "trace_tail": tb}
        return wrapper
    return decorator


# ----- helpers -----
def _current_mtd_cost_usd() -> float | None:
    """Best-effort MTD spend in USD. None if Cost Explorer not enabled."""
    try:
        ce = client("ce", region="us-east-1")
        today = datetime.now(timezone.utc).date()
        first = today.replace(day=1)
        r = ce.get_cost_and_usage(
            TimePeriod={"Start": first.isoformat(), "End": today.isoformat()},
            Granularity="MONTHLY",
            Metrics=["UnblendedCost"],
        )
        rows = r.get("ResultsByTime", [])
        if not rows:
            return 0.0
        return float(rows[0]["Total"]["UnblendedCost"]["Amount"])
    except (ClientError, BotoCoreError):
        return None


def _detect_my_public_ip() -> str | None:
    """Return the caller's public IPv4 or None on failure (NEVER fall back to 0.0.0.0)."""
    for url in ("https://checkip.amazonaws.com", "https://api.ipify.org"):
        try:
            ip = urllib.request.urlopen(url, timeout=5).read().decode().strip()
            # rudimentary IPv4 validation
            parts = ip.split(".")
            if len(parts) == 4 and all(p.isdigit() and 0 <= int(p) <= 255 for p in parts):
                return ip
        except Exception:
            continue
    return None


# ----- MCP server -----
mcp = FastMCP("aws-pilot")


@mcp.tool()
@safe_tool("aws_account_overview")
def aws_account_overview() -> dict:
    """Return identity, region, MTD cost (best-effort), running resources count.
    Always read-only, safe to call any time."""
    ident = client("sts").get_caller_identity()

    out = {
        "account_id": ident["Account"],
        "arn": ident["Arn"],
        "user_id": ident["UserId"],
        "region_default": REGION,
        "profile": PROFILE,
        "mode": MODE,
        "budget_usd": BUDGET_USD,
        "audit_log": str(AUDIT_LOG),
    }

    mtd = _current_mtd_cost_usd()
    if mtd is not None:
        out["mtd_cost_usd"] = round(mtd, 2)
        out["budget_remaining_usd"] = round(BUDGET_USD - mtd, 2)

    # Top services this month (best-effort)
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
        out["top_services"] = sorted(
            [(g["Keys"][0], round(float(g["Metrics"]["UnblendedCost"]["Amount"]), 2)) for g in groups],
            key=lambda x: -x[1],
        )[:5]
    except (ClientError, BotoCoreError):
        pass

    # Running EC2 across regions (capped to avoid long calls)
    try:
        regions = [r["RegionName"] for r in client("ec2").describe_regions()["Regions"]]
        running = {}
        for r in regions[:20]:  # cap at 20 to avoid 30+ slow calls
            try:
                resp = client("ec2", region=r).describe_instances(
                    Filters=[{"Name": "instance-state-name", "Values": ["running"]}]
                )
                count = sum(len(rsv["Instances"]) for rsv in resp["Reservations"])
                if count:
                    running[r] = count
            except (ClientError, BotoCoreError):
                pass
        out["running_ec2"] = running
    except (ClientError, BotoCoreError):
        pass

    return out


@mcp.tool()
@safe_tool("aws_list_resources")
def aws_list_resources(service: str, region: str | None = None) -> dict:
    """List resources of a given service. Read-only.

    Supported: ec2, s3, lambda, rds, iam, route53, secretsmanager, cloudwatch-logs, vpc.
    """
    region = region or REGION
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
        return {"instances": instances, "count": len(instances)}
    if service == "s3":
        r = client("s3").list_buckets()
        return {"buckets": [{"name": b["Name"], "created": b["CreationDate"].isoformat()} for b in r["Buckets"]], "count": len(r["Buckets"])}
    if service == "lambda":
        r = client("lambda", region).list_functions()
        funs = [{"name": f["FunctionName"], "runtime": f["Runtime"], "memory": f["MemorySize"], "timeout": f["Timeout"]} for f in r["Functions"]]
        return {"functions": funs, "count": len(funs)}
    if service == "rds":
        r = client("rds", region).describe_db_instances()
        dbs = [{"id": d["DBInstanceIdentifier"], "engine": d["Engine"], "class": d["DBInstanceClass"], "status": d["DBInstanceStatus"]} for d in r["DBInstances"]]
        return {"db_instances": dbs, "count": len(dbs)}
    if service == "iam":
        users = client("iam").list_users()["Users"]
        roles = client("iam").list_roles()["Roles"]
        return {"users": [u["UserName"] for u in users], "roles": [r["RoleName"] for r in roles]}
    if service == "route53":
        r = client("route53").list_hosted_zones()
        return {"zones": [{"id": z["Id"], "name": z["Name"], "records": z["ResourceRecordSetCount"]} for z in r["HostedZones"]]}
    if service == "secretsmanager":
        r = client("secretsmanager", region).list_secrets()
        return {"secrets": [{"name": s["Name"], "arn": s["ARN"]} for s in r["SecretList"]], "count": len(r["SecretList"])}
    if service in ("cloudwatch-logs", "logs"):
        r = client("logs", region).describe_log_groups()
        return {"log_groups": [{"name": g["logGroupName"], "size_bytes": g.get("storedBytes", 0), "retention_days": g.get("retentionInDays")} for g in r["logGroups"]]}
    if service == "vpc":
        vpcs = client("ec2", region).describe_vpcs()["Vpcs"]
        return {"vpcs": [{"id": v["VpcId"], "cidr": v["CidrBlock"], "is_default": v["IsDefault"], "state": v["State"]} for v in vpcs]}
    return {"error": f"unsupported service: {service}", "supported": ["ec2", "s3", "lambda", "rds", "iam", "route53", "secretsmanager", "cloudwatch-logs", "vpc"]}


@mcp.tool()
@safe_tool("aws_create_ec2_with_ssh")
def aws_create_ec2_with_ssh(name: str, instance_type: str = "t3.micro", region: str | None = None) -> dict:
    """Create an EC2 instance with auto-generated SSH key + security group restricted to caller IP.
    Honors AWS_PILOT_MODE. Refuses to create if estimated monthly cost would exceed budget headroom.
    Rolls back partial state (keypair, SG) if any step after creation fails.

    Returns: {instance_id, public_ip, ssh_command, key_path, security_group, monthly_cost_estimate_usd}
    """
    blocked = gate("run_instances")
    if blocked:
        return {"blocked": blocked}

    # Cost preview & budget check
    cost_table = {"t3.nano": 3.80, "t3.micro": 7.60, "t3.small": 15.18, "t3.medium": 30.37, "t3.large": 60.74}
    monthly = cost_table.get(instance_type, 0.0) + 0.64  # plus 8GB EBS gp3
    mtd = _current_mtd_cost_usd()
    if mtd is not None:
        remaining = BUDGET_USD - mtd
        if monthly > remaining:
            return {
                "error": f"Would exceed budget: estimated ${monthly:.2f}/mo > remaining ${remaining:.2f} (MTD ${mtd:.2f} of ${BUDGET_USD:.2f}). Raise monthly_budget_usd or pick a cheaper instance type.",
                "kind": "budget_exceeded",
                "estimate_usd": monthly,
                "budget_remaining_usd": remaining,
            }

    region = region or REGION
    ec2 = client("ec2", region)

    # Validate region exists
    try:
        ec2.describe_availability_zones()
    except ClientError as e:
        return {"error": f"region '{region}' invalid or inaccessible: {e}", "kind": "bad_region"}

    # Detect caller IP (refuse if undetectable — never default to 0.0.0.0/0)
    my_ip = _detect_my_public_ip()
    if my_ip is None:
        return {"error": "Could not detect your public IP. Aborting (would not pin SSH to your IP).", "kind": "no_ip"}

    # ~/.ssh dir
    ssh_dir = Path.home() / ".ssh"
    try:
        ssh_dir.mkdir(parents=True, exist_ok=True)
    except (OSError, PermissionError) as e:
        return {"error": f"Cannot create {ssh_dir}: {e}", "kind": "ssh_dir"}

    key_path = ssh_dir / f"aws-{name}.pem"
    if key_path.exists():
        return {"error": f"key file already exists: {key_path}. Pick a different name or delete the existing file.", "kind": "key_exists"}

    # Latest AL2023 AMI
    images = ec2.describe_images(
        Owners=["amazon"],
        Filters=[
            {"Name": "name", "Values": ["al2023-ami-*-kernel-*-x86_64"]},
            {"Name": "state", "Values": ["available"]},
        ],
    )["Images"]
    if not images:
        return {"error": f"No Amazon Linux 2023 AMI available in {region}", "kind": "no_ami"}
    ami_id = sorted(images, key=lambda i: i["CreationDate"])[-1]["ImageId"]

    # Create keypair (rollback on later failure)
    created_keypair = False
    created_sg = None
    try:
        kp = ec2.create_key_pair(KeyName=name, KeyType="rsa", KeyFormat="pem")
        created_keypair = True
        # write private key with restrictive perms (best-effort on Windows)
        key_path.write_text(kp["KeyMaterial"], encoding="utf-8")
        try:
            key_path.chmod(0o600)
        except Exception:
            pass  # NTFS may ignore; that's OK, file is in user-private dir

        # Default VPC (or first VPC)
        vpcs = ec2.describe_vpcs(Filters=[{"Name": "isDefault", "Values": ["true"]}])["Vpcs"]
        if not vpcs:
            vpcs = ec2.describe_vpcs()["Vpcs"]
        if not vpcs:
            return {"error": f"No VPC in {region}. Create a VPC first.", "kind": "no_vpc"}
        vpc_id = vpcs[0]["VpcId"]

        # Security group
        sg = ec2.create_security_group(
            GroupName=f"{name}-sg",
            Description=f"auto-created by aws-pilot for {name}",
            VpcId=vpc_id,
        )
        created_sg = sg["GroupId"]
        ec2.authorize_security_group_ingress(
            GroupId=created_sg,
            IpPermissions=[{
                "IpProtocol": "tcp", "FromPort": 22, "ToPort": 22,
                "IpRanges": [{"CidrIp": f"{my_ip}/32", "Description": "SSH from creator"}],
            }],
        )

        # Launch
        launched = ec2.run_instances(
            ImageId=ami_id,
            InstanceType=instance_type,
            KeyName=name,
            SecurityGroupIds=[created_sg],
            MinCount=1, MaxCount=1,
            TagSpecifications=[{
                "ResourceType": "instance",
                "Tags": [
                    {"Key": "Name", "Value": name},
                    {"Key": "ManagedBy", "Value": "aws-pilot"},
                    {"Key": "CreatedAt", "Value": datetime.now(timezone.utc).isoformat()},
                ],
            }],
        )
        inst_id = launched["Instances"][0]["InstanceId"]

        # Wait running with bounded retries (10 min max)
        waiter = ec2.get_waiter("instance_running")
        waiter.wait(InstanceIds=[inst_id], WaiterConfig={"Delay": 5, "MaxAttempts": 120})

        desc = ec2.describe_instances(InstanceIds=[inst_id])
        pub_ip = desc["Reservations"][0]["Instances"][0].get("PublicIpAddress", "(no public IP — instance is in private subnet)")

        return {
            "instance_id": inst_id,
            "public_ip": pub_ip,
            "ssh_command": f"ssh -i \"{key_path}\" ec2-user@{pub_ip}",
            "key_path": str(key_path),
            "security_group": created_sg,
            "vpc_id": vpc_id,
            "monthly_cost_estimate_usd": monthly,
            "your_ip": my_ip,
        }
    except Exception:
        # rollback partial state to avoid orphans
        if created_sg:
            try:
                ec2.delete_security_group(GroupId=created_sg)
            except Exception:
                pass
        if created_keypair:
            try:
                ec2.delete_key_pair(KeyName=name)
            except Exception:
                pass
            try:
                if key_path.exists():
                    key_path.unlink()
            except Exception:
                pass
        raise


@mcp.tool()
@safe_tool("aws_terminate_ec2")
def aws_terminate_ec2(instance_id: str, region: str | None = None, confirm: bool = False) -> dict:
    """Terminate an EC2 instance. DESTRUCTIVE. Requires confirm=True AND mode=execute.
    Also deletes the auto-tagged SG and keypair if they were created by aws-pilot."""
    blocked = gate("terminate_instances")
    if blocked:
        return {"blocked": blocked}
    if not confirm:
        return {"error": "destructive op — pass confirm=True to proceed", "kind": "needs_confirm"}

    region = region or REGION
    ec2 = client("ec2", region)

    # Look up the instance to know its name (for SG/keypair cleanup)
    desc = ec2.describe_instances(InstanceIds=[instance_id])
    if not desc["Reservations"]:
        return {"error": f"instance {instance_id} not found in {region}", "kind": "not_found"}
    inst = desc["Reservations"][0]["Instances"][0]
    tag_name = next((t["Value"] for t in inst.get("Tags", []) if t["Key"] == "Name"), None)
    managed_by = next((t["Value"] for t in inst.get("Tags", []) if t["Key"] == "ManagedBy"), None)

    r = ec2.terminate_instances(InstanceIds=[instance_id])
    out = {"terminating": r["TerminatingInstances"]}

    # If tagged ManagedBy=aws-pilot, schedule cleanup of SG + keypair after instance stops
    if managed_by == "aws-pilot" and tag_name:
        out["cleanup_pending"] = {"sg": f"{tag_name}-sg", "keypair": tag_name}
        out["cleanup_note"] = "Run aws_cleanup_managed (TODO) after instance is fully terminated to remove SG + keypair."

    return out


@mcp.tool()
@safe_tool("aws_audit_log_tail")
def aws_audit_log_tail(lines: int = 20) -> dict:
    """Return last N lines of the audit log. Bounded read (last 1MB) so doesn't OOM on huge logs."""
    if not AUDIT_LOG.exists():
        return {"path": str(AUDIT_LOG), "content": "(empty — no calls audited yet)"}
    try:
        size = AUDIT_LOG.stat().st_size
        with AUDIT_LOG.open("rb") as f:
            # seek to last 1MB
            if size > 1024 * 1024:
                f.seek(-1024 * 1024, os.SEEK_END)
                f.readline()  # discard partial line
            tail = f.read().decode("utf-8", errors="replace").splitlines()
        n = max(1, min(lines, 500))
        return {"path": str(AUDIT_LOG), "lines": tail[-n:], "total_bytes": size}
    except (OSError, PermissionError) as e:
        return {"error": f"cannot read audit log: {e}", "kind": "io"}


if __name__ == "__main__":
    print(f"aws-pilot MCP starting (mode={MODE}, profile={PROFILE}, region={REGION}, audit={AUDIT_LOG})", file=sys.stderr)
    mcp.run()
