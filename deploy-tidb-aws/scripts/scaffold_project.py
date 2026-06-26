#!/usr/bin/env python3
"""Create a self-contained Terraform project for deploying TiDB on AWS."""

from __future__ import annotations

import argparse
import json
import re
import shlex
import shutil
import sys
from datetime import datetime
from pathlib import Path


DEFAULTS = {
    "namespace": None,
    "n_pd": 1,
    "n_tidb": 3,
    "n_tikv": 3,
    "n_tiflash": 1,
    "n_ticdc": 3,
    "ticdc_architecture": "new",
    "username": "ubuntu",
    "aws_profile": "default",
    "region": "us-west-2",
    "image": "ami-003e5556ddc999e13",
    "cluster_name": "tidb-cluster",
    "tidb_version": "latest-stable",
}

AMI_BY_REGION = {
    "us-east-1": "ami-0c398cb65a93047f2",
    "us-east-2": "ami-05cda54fbc39e2381",
    "us-west-1": "ami-0575bfdeb6f59b5d8",
    "us-west-2": "ami-003e5556ddc999e13",
}


def non_negative_int(value: str) -> int:
    number = int(value)
    if number < 0:
        raise argparse.ArgumentTypeError("must be >= 0")
    return number


def namespace(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9-]{0,62}", value):
        raise argparse.ArgumentTypeError(
            "use 1-63 letters, digits, or hyphens; start with a letter or digit"
        )
    return value


def aws_profile(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_+=,.@-]{1,128}", value):
        raise argparse.ArgumentTypeError(
            "use 1-128 AWS profile-safe characters: letters, digits, _, +, =, ,, ., @, or -"
        )
    return value


def service_name(value: str) -> str:
    if not re.fullmatch(r"[a-z][a-z0-9-]{0,62}", value):
        raise argparse.ArgumentTypeError(
            "use 1-63 lowercase letters, digits, or hyphens; start with a letter"
        )
    return value


def parse_extra_service(value: str) -> tuple[str, dict[str, object]]:
    match = re.fullmatch(
        r"(?P<name>[a-z][a-z0-9-]{0,62})=(?P<count>[0-9]+)(:(?P<instance>[A-Za-z0-9.-]+))?",
        value,
    )
    if not match:
        raise argparse.ArgumentTypeError(
            "use <service-name>=<count> or <service-name>=<count>:<instance-type>"
        )
    count = int(match.group("count"))
    item: dict[str, object] = {"count": count}
    instance_type = match.group("instance")
    if instance_type:
        item["instance_type"] = instance_type
    return service_name(match.group("name")), item


def default_target(namespace_value: str) -> Path:
    return Path.home() / "test" / f"tidb-aws-{namespace_value}"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Scaffold a Terraform project for TiDB on AWS."
    )
    parser.add_argument(
        "--target",
        help="Output directory. Defaults to $HOME/test/tidb-aws-<namespace>.",
    )
    parser.add_argument("--namespace", type=namespace)
    parser.add_argument("--n-pd", type=non_negative_int, default=DEFAULTS["n_pd"])
    parser.add_argument("--n-tidb", type=non_negative_int, default=DEFAULTS["n_tidb"])
    parser.add_argument("--n-tikv", type=non_negative_int, default=DEFAULTS["n_tikv"])
    parser.add_argument(
        "--n-tiflash", type=non_negative_int, default=DEFAULTS["n_tiflash"]
    )
    parser.add_argument("--n-ticdc", type=non_negative_int, default=DEFAULTS["n_ticdc"])
    parser.add_argument(
        "--ticdc-architecture",
        choices=["new", "old"],
        default=DEFAULTS["ticdc_architecture"],
        help="TiCDC architecture. Defaults to new.",
    )
    parser.add_argument(
        "--extra-service",
        action="append",
        default=[],
        type=parse_extra_service,
        metavar="NAME=COUNT[:INSTANCE_TYPE]",
        help="Add standalone extra service nodes. Repeat for multiple services.",
    )
    parser.add_argument("--username", default=DEFAULTS["username"])
    parser.add_argument(
        "--aws-profile", type=aws_profile, default=DEFAULTS["aws_profile"]
    )
    parser.add_argument("--region", default=DEFAULTS["region"])
    parser.add_argument("--image", help="AMI ID. Defaults to the known AMI for region.")
    parser.add_argument("--cluster-name", type=namespace)
    parser.add_argument(
        "--tidb-version",
        default=DEFAULTS["tidb_version"],
        help="TiDB version for TiUP deploy. Defaults to latest-stable.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace target directory if it already exists.",
    )
    args = parser.parse_args()
    if args.namespace is None:
        args.namespace = f"tidb-cluster-{datetime.now().strftime('%y%m%d%H%M')}"
    if args.n_pd != 1:
        raise SystemExit("This template supports exactly one PD node; use --n-pd 1.")
    args.image = args.image or AMI_BY_REGION.get(args.region)
    if not args.image:
        raise SystemExit(
            f"No default AMI is known for {args.region}; pass --image explicitly."
        )
    args.cluster_name = args.cluster_name or args.namespace
    args.extra_services = dict(args.extra_service)
    args.target = args.target or str(default_target(args.namespace))
    return args


def render_extra_services(extra_services: dict[str, dict[str, object]]) -> str:
    if not extra_services:
        return "  extra_services = {}\n"
    lines = ["  extra_services = {"]
    for name in sorted(extra_services):
        service = extra_services[name]
        count_key = "count        " if "instance_type" in service else "count"
        lines.extend(
            [
                f'    "{name}" = {{',
                f"      {count_key} = {service['count']}",
            ]
        )
        if "instance_type" in service:
            lines.append(f'      instance_type = "{service["instance_type"]}"')
        lines.extend(["    }", ""])
    lines.append("  }")
    return "\n".join(lines) + "\n"


def render_locals_common(args: argparse.Namespace) -> str:
    cdc_newarch = "true" if args.ticdc_architecture == "new" else "false"
    return f"""locals {{
  namespace   = "{args.namespace}"
  n_pd        = 1
  n_tidb      = {args.n_tidb}
  n_tikv      = {args.n_tikv}
  n_tiflash   = {args.n_tiflash}
  n_ticdc     = {args.n_ticdc}
  cdc_newarch = {cdc_newarch}
  username    = "{args.username}"

{render_extra_services(args.extra_services)}}}
"""


def update_advanced(project: Path, args: argparse.Namespace) -> None:
    path = project / "locals_advanced.tf"
    text = path.read_text()
    text = re.sub(r'  region = "[^"]+"', f'  region = "{args.region}"', text)
    text = re.sub(r'  image  = "[^"]+"', f'  image  = "{args.image}"', text)
    path.write_text(text)


def update_provider(project: Path, args: argparse.Namespace) -> None:
    path = project / "main.tf"
    text = path.read_text()
    text = re.sub(r'  profile = "[^"]+"', f'  profile = "{args.aws_profile}"', text)
    path.write_text(text)


def write_deployment_metadata(project: Path, args: argparse.Namespace) -> None:
    metadata = {
        "deployment_path": str(project),
        "namespace": args.namespace,
        "cluster_name": args.cluster_name,
        "tidb_version": args.tidb_version,
        "username": args.username,
        "aws_profile": args.aws_profile,
        "region": args.region,
        "image": args.image,
        "counts": {
            "pd": 1,
            "tidb": args.n_tidb,
            "tikv": args.n_tikv,
            "tiflash": args.n_tiflash,
            "ticdc": args.n_ticdc,
        },
        "ticdc_architecture": args.ticdc_architecture,
        "cdc_newarch": args.ticdc_architecture == "new",
        "extra_services": args.extra_services,
    }
    (project / "deployment.json").write_text(json.dumps(metadata, indent=2) + "\n")


def render_tidb_version_readme_section(args: argparse.Namespace) -> str:
    if args.tidb_version == DEFAULTS["tidb_version"]:
        return """The scaffold requested `latest-stable`; keep the value resolved by the previous command.
If you intentionally want a fixed version instead, set it directly, for example:

```shell
tidb_version="v8.5.0"
```"""
    return f"""This deployment requested a concrete TiDB version:

```shell
tidb_version="{args.tidb_version}"
```"""


def write_project_readme(project: Path, args: argparse.Namespace) -> None:
    cd_project = shlex.quote(str(project))
    tidb_version_section = render_tidb_version_readme_section(args)
    readme = f"""# TiDB AWS Deployment: {args.cluster_name}

Deployment path: `{project}`

This directory contains the Terraform configuration and local state for this TiDB
AWS deployment. Run Terraform commands from this directory.

## Metadata

- Namespace: `{args.namespace}`
- Cluster name: `{args.cluster_name}`
- TiDB version request: `{args.tidb_version}`
- TiCDC architecture: `{args.ticdc_architecture}`
- AWS profile: `{args.aws_profile}`
- AWS region: `{args.region}`
- Deployment metadata: `deployment.json`

The template exposes SSH, Grafana, and TiDB Dashboard ports publicly. Review the
security group rules before using this deployment for anything sensitive.

## Preflight

```shell
cd {cd_project}
aws sts get-caller-identity --profile {args.aws_profile}
test -f ~/.ssh/id_rsa.pub
test -f master_key -a -f master_key.pub || ssh-keygen -t rsa -b 4096 -f ./master_key -q -N ""
terraform init
terraform fmt -check
terraform validate
```

If the AWS identity check fails, refresh SSO login and retry:

```shell
aws sso login --profile {args.aws_profile}
aws sts get-caller-identity --profile {args.aws_profile}
```

## Provision Or Update AWS VMs

Prefer a saved Terraform plan:

```shell
cd {cd_project}
terraform plan -out=tfplan
terraform apply tfplan
```

For non-interactive runs only:

```shell
terraform apply -auto-approve
```

Inspect outputs after apply:

```shell
terraform output
terraform output -raw ssh-center
terraform output -raw url-grafana
terraform output -raw url-tidb-dashboard
terraform output private-ip-pd
terraform output private-ip-tidb
terraform output private-ip-tikv
terraform output private-ip-tiflash
terraform output private-ip-ticdc
terraform output private-ip-extra-services
terraform output ssh-extra-services
```

## Deploy Or Start TiDB From The Center VM

Get the center VM SSH command locally:

```shell
cd {cd_project}
terraform output -raw ssh-center
```

On the center VM, wait for cloud-init and verify TiUP:

```shell
cloud-init status --wait
test -f ~/topology.yaml
test -f ~/.ssh/id_rsa
tiup --version
```

If `deployment.json` records `latest-stable`, resolve the concrete stable TiDB
version on the center VM before deploying:

```shell
tidb_version="$(
  tiup list tidb --refresh 2>/dev/null |
    awk '{{print $1}}' |
    grep -E '^v[0-9]+\\.[0-9]+\\.[0-9]+$' |
    sort -V |
    tail -n 1
)"
test -n "$tidb_version"
```

{tidb_version_section}

Deploy and start the TiUP cluster from the center VM:

```shell
tiup cluster deploy {args.cluster_name} "$tidb_version" ./topology.yaml --user {args.username} -i ~/.ssh/id_rsa --yes
tiup cluster start {args.cluster_name} --yes
tiup cluster display {args.cluster_name}
```

If the TiUP cluster already exists:

```shell
tiup cluster list
tiup cluster display {args.cluster_name}
tiup cluster start {args.cluster_name} --yes
```

## Validate TiDB

From the center VM:

```shell
mysql -u root --host 127.0.0.1 --port 4000 -e "select tidb_version();"
```

## Destroy AWS Resources

Only run destroy when the cluster should be removed:

```shell
cd {cd_project}
terraform destroy -auto-approve
```

Leave local files such as `master_key`, `master_key.pub`, `.tfstate`, and
`tfplan` in place unless you intentionally want to remove local artifacts.
"""
    (project / "README.md").write_text(readme)


def main() -> int:
    args = parse_args()
    script_dir = Path(__file__).resolve().parent
    skill_dir = script_dir.parent
    template = skill_dir / "assets" / "terraform-up-tidb-aws"
    target = Path(args.target).expanduser().resolve()

    if not template.is_dir():
        raise SystemExit(f"Template directory does not exist: {template}")
    protected = {
        Path("/").resolve(),
        Path.home().resolve(),
        (Path.home() / "test").resolve(),
        skill_dir.resolve(),
    }
    if target in protected or skill_dir.resolve() in target.parents:
        raise SystemExit(f"Refusing unsafe target directory: {target}")
    if target.exists():
        if not args.force:
            raise SystemExit(f"Target already exists; pass --force to replace: {target}")
        shutil.rmtree(target)

    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copytree(template, target)
    (target / "locals_common.tf").write_text(render_locals_common(args))
    update_advanced(target, args)
    update_provider(target, args)
    write_deployment_metadata(target, args)
    write_project_readme(target, args)

    print(f"Created Terraform project: {target}")
    print(f"Deployment path: {target}")
    print(f"Cluster name: {args.cluster_name}")
    print(f"TiDB version: {args.tidb_version}")
    print(f"TiCDC architecture: {args.ticdc_architecture}")
    print(f"AWS profile: {args.aws_profile}")
    print(f"Extra services: {json.dumps(args.extra_services, sort_keys=True)}")
    print("Next: cd to the project, run terraform init/validate, then plan/apply.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
