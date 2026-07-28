#!/usr/bin/env python3
"""Create a self-contained Terraform project for named EC2 node groups."""

from __future__ import annotations

import argparse
import ipaddress
import json
import re
import shlex
import shutil
import sys
import urllib.error
import urllib.request
from datetime import datetime
from pathlib import Path


DEFAULT_CPU = 2
DEFAULT_MEMORY_GIB = 4
DEFAULT_REGION = "us-west-2"
DEFAULT_ROOT_VOLUME_SIZE = 20

# Keep this catalog intentionally small and x86_64-only so it matches the bundled
# Amazon Linux 2023 AMI. The resolver selects an exact match when available, then
# the smallest catalog entry that satisfies both requested minimums.
INSTANCE_CATALOG = [
    ("t3.micro", 2, 1),
    ("t3.small", 2, 2),
    ("t3.medium", 2, 4),
    ("t3.large", 2, 8),
    ("t3.xlarge", 4, 16),
    ("t3.2xlarge", 8, 32),
    ("c7i.large", 2, 4),
    ("c7i.xlarge", 4, 8),
    ("c7i.2xlarge", 8, 16),
    ("c7i.4xlarge", 16, 32),
    ("c7i.8xlarge", 32, 64),
    ("c7i.12xlarge", 48, 96),
    ("c7i.16xlarge", 64, 128),
    ("m7i.large", 2, 8),
    ("m7i.xlarge", 4, 16),
    ("m7i.2xlarge", 8, 32),
    ("m7i.4xlarge", 16, 64),
    ("m7i.8xlarge", 32, 128),
    ("m7i.12xlarge", 48, 192),
    ("m7i.16xlarge", 64, 256),
    ("r7i.large", 2, 16),
    ("r7i.xlarge", 4, 32),
    ("r7i.2xlarge", 8, 64),
    ("r7i.4xlarge", 16, 128),
    ("r7i.8xlarge", 32, 256),
    ("r7i.12xlarge", 48, 384),
    ("r7i.16xlarge", 64, 512),
]


def positive_int(value: str) -> int:
    number = int(value)
    if number <= 0:
        raise argparse.ArgumentTypeError("must be greater than 0")
    return number


def root_volume_size(value: str) -> int:
    size = positive_int(value)
    if size < 8:
        raise argparse.ArgumentTypeError("must be at least 8 GiB")
    return size


def namespace(value: str) -> str:
    if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,62}", value):
        raise argparse.ArgumentTypeError(
            "use 1-63 lowercase letters, digits, or hyphens"
        )
    return value


def aws_profile(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_+=,.@-]{1,128}", value):
        raise argparse.ArgumentTypeError("contains characters unsupported by AWS profiles")
    return value


def ipv4_cidr(value: str) -> str:
    try:
        network = ipaddress.ip_network(value, strict=False)
    except ValueError as error:
        raise argparse.ArgumentTypeError("must be a valid IPv4 CIDR") from error
    if network.version != 4:
        raise argparse.ArgumentTypeError("must be an IPv4 CIDR")
    return str(network)


def resolve_instance_type(cpu: int, memory_gib: int) -> str:
    candidates = [
        item
        for item in INSTANCE_CATALOG
        if item[1] >= cpu and item[2] >= memory_gib
    ]
    if not candidates:
        raise ValueError(
            f"no supported instance type satisfies {cpu} vCPU and {memory_gib} GiB"
        )

    exact = [item for item in candidates if item[1] == cpu and item[2] == memory_gib]
    if exact:
        return exact[0][0]

    selected = min(
        candidates,
        key=lambda item: (
            item[1] * item[2],
            item[1] - cpu,
            item[2] - memory_gib,
            INSTANCE_CATALOG.index(item),
        ),
    )
    return selected[0]


def parse_node_spec(value: str) -> tuple[str, dict[str, object]]:
    match = re.fullmatch(
        r"(?P<name>[a-z][a-z0-9-]{0,62})="
        r"(?P<count>[1-9][0-9]*)"
        r"(?::(?P<cpu>[1-9][0-9]*):(?P<memory>[1-9][0-9]*))?",
        value,
    )
    if not match:
        raise ValueError(
            "use NAME=COUNT or NAME=COUNT:CPU:MEMORY_GIB; "
            "names must start with a lowercase letter"
        )

    cpu = int(match.group("cpu") or DEFAULT_CPU)
    memory_gib = int(match.group("memory") or DEFAULT_MEMORY_GIB)
    return match.group("name"), {
        "count": int(match.group("count")),
        "cpu": cpu,
        "memory_gib": memory_gib,
        "instance_type": resolve_instance_type(cpu, memory_gib),
    }


def collect_node_groups(values: list[str]) -> dict[str, dict[str, object]]:
    groups: dict[str, dict[str, object]] = {}
    for value in values:
        name, group = parse_node_spec(value)
        if name in groups:
            raise ValueError(f"duplicate node group: {name}")
        groups[name] = group
    return groups


def detect_operator_cidr() -> str:
    try:
        with urllib.request.urlopen(
            "https://checkip.amazonaws.com", timeout=5
        ) as response:
            address = response.read().decode().strip()
        return f"{ipaddress.IPv4Address(address)}/32"
    except (OSError, ValueError, urllib.error.URLError) as error:
        raise ValueError(
            "could not detect the operator public IPv4 address; pass --ssh-cidr"
        ) from error


def resolve_public_key(value: str | None) -> Path:
    if value:
        candidates = [Path(value).expanduser()]
    else:
        candidates = [
            Path.home() / ".ssh" / "id_ed25519.pub",
            Path.home() / ".ssh" / "id_rsa.pub",
        ]
    for candidate in candidates:
        if candidate.is_file():
            return candidate.resolve()
    raise ValueError("no SSH public key found; pass --public-key")


def default_target(namespace_value: str) -> Path:
    return Path.home() / "test" / f"ec2-aws-{namespace_value}"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Scaffold Terraform for named EC2 node groups on AWS."
    )
    parser.add_argument(
        "--node",
        action="append",
        required=True,
        metavar="NAME=COUNT[:CPU:MEMORY_GIB]",
        help=(
            "Node group definition. Repeat for multiple groups. "
            f"CPU and memory default to {DEFAULT_CPU} vCPU/{DEFAULT_MEMORY_GIB} GiB."
        ),
    )
    parser.add_argument("--target", help="Output directory under $HOME/test by default.")
    parser.add_argument("--namespace", type=namespace)
    parser.add_argument("--aws-profile", type=aws_profile, default="default")
    parser.add_argument("--region", default=DEFAULT_REGION)
    parser.add_argument("--availability-zone")
    parser.add_argument("--ssh-cidr", type=ipv4_cidr)
    parser.add_argument("--public-key")
    parser.add_argument("--vpc-cidr", type=ipv4_cidr, default="10.0.0.0/16")
    parser.add_argument(
        "--public-subnet-cidr", type=ipv4_cidr, default="10.0.0.0/20"
    )
    parser.add_argument(
        "--root-volume-size",
        type=root_volume_size,
        default=DEFAULT_ROOT_VOLUME_SIZE,
        metavar="GIB",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace the exact target directory if it already exists.",
    )
    return parser


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.namespace is None:
        args.namespace = f"ec2-nodes-{datetime.now().strftime('%y%m%d%H%M')}"
    try:
        args.node_groups = collect_node_groups(args.node)
        args.ssh_cidr = args.ssh_cidr or detect_operator_cidr()
        args.public_key = resolve_public_key(args.public_key)
    except ValueError as error:
        parser.error(str(error))

    vpc = ipaddress.ip_network(args.vpc_cidr)
    subnet = ipaddress.ip_network(args.public_subnet_cidr)
    if not subnet.subnet_of(vpc):
        parser.error("--public-subnet-cidr must be contained by --vpc-cidr")

    args.target = Path(args.target).expanduser() if args.target else default_target(args.namespace)
    return args


def write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")


def write_project_files(project: Path, args: argparse.Namespace) -> None:
    variables = {
        "namespace": args.namespace,
        "aws_profile": args.aws_profile,
        "region": args.region,
        "availability_zone": args.availability_zone,
        "vpc_cidr": args.vpc_cidr,
        "public_subnet_cidr": args.public_subnet_cidr,
        "ssh_cidr": args.ssh_cidr,
        "public_key_path": str(args.public_key),
        "ssh_user": "ec2-user",
        "root_volume_size": args.root_volume_size,
        "node_groups": args.node_groups,
    }
    write_json(project / "terraform.tfvars.json", variables)
    write_json(
        project / "deployment.json",
        {
            "deployment_path": str(project),
            **variables,
        },
    )
    write_project_readme(project, args)


def write_project_readme(project: Path, args: argparse.Namespace) -> None:
    project_command = shlex.quote(str(project))
    profile = shlex.quote(args.aws_profile)
    region = shlex.quote(args.region)
    instance_types = shlex.quote(
        ",".join(
            sorted({group["instance_type"] for group in args.node_groups.values()})
        )
    )
    readme = f"""# EC2 AWS Deployment: {args.namespace}

Deployment path: `{project}`

This self-contained Terraform project creates named EC2 node groups in one VPC
and public subnet. Nodes communicate freely over private IPs. SSH is limited to
`{args.ssh_cidr}`, and every node receives a stable Elastic IP.

Single-node groups use the exact group name as the EC2 `Name` tag. Multi-node
groups use zero-padded suffixes such as `api-01` and `api-02`.

Elastic IPs incur AWS public IPv4 charges while allocated. Destroy the deployment
when it is no longer needed.

## Requested Nodes

```json
{json.dumps(args.node_groups, indent=2, sort_keys=True)}
```

CPU and memory are minimum requested sizes. `instance_type` is the resolved x86_64
EC2 type and must be offered in `{args.region}`.

## Preflight

```shell
cd {project_command}
aws sts get-caller-identity --profile {profile}
aws ec2 describe-instance-type-offerings \\
  --profile {profile} \\
  --region {region} \\
  --location-type region \\
  --filters Name=instance-type,Values={instance_types} \\
  --query 'InstanceTypeOfferings[].InstanceType'
terraform init
terraform fmt -check
terraform validate
```

If the identity check fails for an SSO profile, refresh it and retry:

```shell
aws sso login --profile {profile}
aws sts get-caller-identity --profile {profile}
```

## Provision Or Update

Review a saved plan before applying it:

```shell
cd {project_command}
terraform plan -out=tfplan
terraform apply tfplan
```

Inspect addresses and connection commands:

```shell
terraform output -json public_ips
terraform output -json private_ips
terraform output -json instance_ids
terraform output -json instance_types
terraform output -json ssh_commands
```

## Post-Apply Validation

Wait until both AWS status checks are healthy for every instance ID.
Test every generated SSH command with a non-destructive command such as `hostname`.

Require the same inputs to produce a no-change plan:

```shell
terraform plan -detailed-exitcode
```

Exit code `0` means the deployment is stable. Exit code `2` means Terraform still
proposes changes; inspect the plan and stop on any unrequested destroy or
replacement.

If direct SSH to one node times out, confirm the current operator public IPv4
still matches `ssh_cidr`, confirm both EC2 status checks are `ok`, and test the
node's private IP through a reachable deployment node. If private SSH succeeds,
report the public-path failure separately from instance health.
Do not replace an Elastic IP solely because one operator network times out.
Replacement is not a deterministic routing fix.

## Destroy

Only destroy when the AWS resources should be removed:

```shell
cd {project_command}
terraform destroy
```

Terraform state contains infrastructure metadata. Do not print or share state files.
"""
    (project / "README.md").write_text(readme)


def scaffold(args: argparse.Namespace) -> Path:
    skill_dir = Path(__file__).resolve().parent.parent
    template = skill_dir / "assets" / "terraform-ec2-aws"
    target = args.target.resolve()
    protected = {
        Path("/").resolve(),
        Path.home().resolve(),
        (Path.home() / "test").resolve(),
        skill_dir.resolve(),
    }
    if target in protected or skill_dir.resolve() in target.parents:
        raise ValueError(f"refusing unsafe target directory: {target}")
    if target.exists():
        if not args.force:
            raise ValueError(f"target already exists; pass --force to replace: {target}")
        shutil.rmtree(target)

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, target)
    write_project_files(target, args)
    return target


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    try:
        target = scaffold(args)
    except ValueError as error:
        raise SystemExit(str(error)) from error

    print(f"Created Terraform project: {target}")
    print(f"Deployment path: {target}")
    print(f"AWS profile: {args.aws_profile}")
    print(f"AWS region: {args.region}")
    print(f"SSH CIDR: {args.ssh_cidr}")
    print(f"Node groups: {json.dumps(args.node_groups, sort_keys=True)}")
    print("Next: run terraform init, validate, plan, and apply from the deployment path.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
