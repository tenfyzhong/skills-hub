# Deployment Reference

## Prompt Parsing

Parse natural language requests into Terraform counts:

- Core role counts map to `--n-pd`, `--n-tidb`, `--n-tikv`, `--n-tiflash`, and `--n-ticdc`.
- Extra service node requests map to repeated `--extra-service <service-name>=<count>` arguments.
- Use `--ticdc-architecture new` by default. Use `--ticdc-architecture old` only when the prompt explicitly asks for old or legacy TiCDC architecture.
- If any role count is missing, use the default from `SKILL.md`.
- If the user requests a Terraform TiDB deployment without counts, use all defaults.
- If the user gives a version, use it as the TiUP version. Otherwise resolve the latest stable TiDB release at deployment time.
- If the user gives a cluster name, use it. Otherwise use the Terraform `namespace`.
- If the user gives an AWS profile, use it for both AWS CLI login checks and the Terraform provider. Otherwise use `default`.
- If the user gives no target directory, use `$HOME/test/tidb-aws-<namespace>`.
- If the user gives a target directory, prefer a path under `$HOME/test` unless they explicitly require another location.
- Always report the absolute deployment path after scaffold and after deploy/start.

The template supports only one PD server in practice. Keep `n_pd = 1` even if the user omits it.

Extra service nodes create standalone EC2 instances in the same VPC and security group, but do not add those instances to `topology.yaml` or the TiUP cluster. Keep service names lowercase and use only letters, digits, and hyphens.

CDC nodes are deployed with `server_configs.cdc.newarch = true` by default. When old TiCDC architecture is explicitly requested, the generated topology must not set `newarch: true`.

## Scaffold

Run the scaffold script from the skill directory:

```shell
python3 <skill-dir>/scripts/scaffold_project.py \
  --namespace tidb-cluster \
  --aws-profile default \
  --n-tidb 3 \
  --n-tikv 3 \
  --n-tiflash 1 \
  --n-ticdc 3 \
  --ticdc-architecture new \
  --extra-service service-name=1
```

When `--target` is omitted, the generated project is created under `$HOME/test/tidb-aws-<namespace>`.
The generated project contains Terraform files, cloud-init templates, rendered defaults in `locals_common.tf`, `deployment.json` with the requested cluster metadata, and `README.md` with Terraform operation guidance.
The scaffold command prints the absolute deployment path; keep using that path for all local Terraform commands.

## Generated Project Shape

Important files:

- `locals_common.tf`: namespace, role counts, `username`.
- `locals_advanced.tf`: AWS region, AMI, EC2 instance types, SSH key paths.
- `main.tf`: AWS provider profile and region wiring.
- `deployment.json`: requested metadata, including `deployment_path`, `aws_profile`, and `ticdc_architecture`.
- `README.md`: local Terraform operation guide for the generated deployment.
- `files/topology.yaml.tftpl`: TiUP topology written to the center VM.
- `data_cloudinit.tf`: writes `topology.yaml`, HAProxy config, and SSH keys to the center VM.
- `outputs.tf`: exposes `ssh-center`, Grafana URL, TiDB Dashboard URL, core node private IPs, and generic extra service outputs.

Default AWS region is `us-west-2`, with the matching Ubuntu 22.04 AMI from the source template. If changing region, update the AMI through `--region` and optionally `--image`.

## AWS Login

Run the AWS identity check before any Terraform command in the generated project. Use the same AWS profile that the scaffold command wrote into `deployment.json`; the default is `default`.

```shell
aws sts get-caller-identity --profile <aws-profile>
```

If the identity check fails, log in with AWS SSO and retry the identity check:

```shell
aws sso login --profile <aws-profile>
aws sts get-caller-identity --profile <aws-profile>
```

Do not run Terraform until `aws sts get-caller-identity` succeeds for the configured profile.

## Preflight

Run from the generated project directory:

```shell
aws sts get-caller-identity --profile <aws-profile>
terraform version
test -f ~/.ssh/id_rsa.pub
test -f master_key
test -f master_key.pub
terraform init
terraform fmt -check
terraform validate
```

If `master_key` or `master_key.pub` is missing, create the pair before `terraform init`:

```shell
ssh-keygen -t rsa -b 4096 -f ./master_key -q -N ""
```

If formatting fails after intentional edits:

```shell
terraform fmt
terraform validate
```

## Provision AWS VMs

Prefer a saved plan:

```shell
terraform plan -out=tfplan
terraform apply tfplan
```

Use this only when the user explicitly requested non-interactive deployment:

```shell
terraform apply -auto-approve
```

Capture outputs:

```shell
terraform output
terraform output -raw ssh-center
terraform output -raw url-grafana
terraform output -raw url-tidb-dashboard
terraform output private-ip-extra-services
terraform output ssh-extra-services
```

## Deploy and Start TiDB

Print the SSH command:

```shell
terraform output -raw ssh-center
```

Use the printed `ssh <user>@<center-public-ip>` command to run center-VM checks:

```shell
cloud-init status --wait
test -f ~/topology.yaml
test -f ~/.ssh/id_rsa
tiup --version
```

Resolve the TiDB version before deploy:

- If the user specified a version, use that exact version.
- If `deployment.json` contains `latest-stable`, resolve the latest stable release on the center VM.
- Do not use `nightly` unless the user explicitly overrides this skill and requests it.

```shell
tidb_version="<user-requested-version>"
```

For the default latest stable release:

```shell
tidb_version="$(
  tiup list tidb --refresh 2>/dev/null \
    | awk '{print $1}' \
    | grep -E '^v[0-9]+\.[0-9]+\.[0-9]+$' \
    | sort -V \
    | tail -n 1
)"
test -n "$tidb_version"
```

Deploy and start from the center VM:

```shell
tiup cluster deploy <cluster-name> "$tidb_version" ./topology.yaml --user <username> -i ~/.ssh/id_rsa --yes
tiup cluster start <cluster-name> --yes
tiup cluster display <cluster-name>
```

Do not add `--init` to `tiup cluster start`.

For the default request, use the resolved stable version:

```shell
tiup cluster deploy tidb-cluster "$tidb_version" ./topology.yaml --user ubuntu -i ~/.ssh/id_rsa --yes
tiup cluster start tidb-cluster --yes
tiup cluster display tidb-cluster
```

If a TiUP cluster already exists:

```shell
tiup cluster list
tiup cluster display <cluster-name>
tiup cluster start <cluster-name> --yes
```

Do not scale an existing TiUP cluster just because Terraform counts changed. Use TiUP scale-out/scale-in only when the user asks to modify an already deployed cluster.

## Validate Access

From the center VM:

```shell
mysql -u root --host 127.0.0.1 --port 4000 -e "select tidb_version();"
```

After deploy/start, display node IPs from the local generated project directory:

```shell
pwd -P
test -f README.md
terraform output private-ip-pd
terraform output private-ip-tidb
terraform output private-ip-tikv
terraform output private-ip-tiflash
terraform output private-ip-ticdc
terraform output private-ip-extra-services
terraform output ssh-center
terraform output ssh-extra-services
```

Report these local outputs:

- absolute deployment path
- generated `README.md` path
- `ssh-center`
- `url-grafana`
- `url-tidb-dashboard`
- private IP outputs for TiDB, TiKV, TiFlash, and TiCDC
- `private-ip-extra-services` and `ssh-extra-services` when extra service nodes were requested

## Destroy

Only destroy when explicitly requested:

```shell
terraform destroy -auto-approve
```

Leave ignored generated files such as `master_key`, `master_key.pub`, `.tfstate`, and `tfplan` alone unless the user asks to remove local artifacts.
