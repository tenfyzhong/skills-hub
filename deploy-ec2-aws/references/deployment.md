# Deployment Reference

## Contents

- [Parse The Request](#parse-the-request)
- [Scaffold The Project](#scaffold-the-project)
- [Authenticate To AWS](#authenticate-to-aws)
- [Initialize And Validate](#initialize-and-validate)
- [Provision](#provision)
- [Validate And Report](#validate-and-report)
- [Update Or Destroy](#update-or-destroy)

## Parse The Request

Translate each requested group into one `--node NAME=COUNT[:CPU:MEMORY_GIB]` argument.

- Require a unique lowercase name and a positive count for every group.
- Use `2` vCPU and `4` GiB when CPU or memory is omitted.
- Treat CPU and memory as minimums; report the resolved EC2 instance type.
- Preserve explicit counts and specifications.
- Use the requested namespace, target, profile, region, availability zone, SSH CIDR, public key, VPC CIDR, subnet CIDR, and root volume size when present.
- If the user omits the SSH CIDR, let the script detect the current public IPv4 address. If detection fails, request a CIDR instead of opening SSH globally.
- If the user omits a public key, use `~/.ssh/id_ed25519.pub`, then `~/.ssh/id_rsa.pub`. If neither exists, request a public key path.

The bundled catalog contains small burstable and current-generation compute-, general-, and memory-optimized x86_64 types. A requested type can be unavailable in a specific region or availability zone; treat a Terraform planning error as a signal to select another catalog type that satisfies the same minimum CPU and memory.

## Scaffold The Project

Run from the skill directory:

```shell
python3 <skill-dir>/scripts/scaffold_project.py \
  --namespace demo \
  --aws-profile default \
  --region us-west-2 \
  --node api=2:2:4 \
  --node worker=3:4:8
```

The generated project contains:

- `terraform.tfvars.json`: Terraform inputs, including resolved instance types
- `deployment.json`: deployment path and requested metadata
- `README.md`: local operation and cleanup guide
- `network.tf`: VPC, public subnet, internet gateway, route, and security group
- `main.tf`: regional AMI lookup, EC2 instances, encrypted root volumes, and Elastic IPs
- `outputs.tf`: addresses, instance IDs/types, and SSH commands grouped by node name

Always report the generated absolute path and keep using it for local commands.

## Authenticate To AWS

Read `aws_profile` and `region` from `deployment.json`, then verify identity:

```shell
aws sts get-caller-identity --profile <aws-profile>
```

If an SSO profile has expired, refresh it and retry:

```shell
aws sso login --profile <aws-profile>
aws sts get-caller-identity --profile <aws-profile>
```

Do not run Terraform until the identity check succeeds and the account is the intended deployment target.

## Initialize And Validate

Run from the generated project directory:

```shell
pwd -P
test -f deployment.json
test -f terraform.tfvars.json
terraform init
terraform fmt -check
terraform validate
terraform plan -out=tfplan
```

Review the plan for the expected node count, instance types, VPC resources, security-group rules, and one Elastic IP per node. If an instance type is not offered in the selected region or availability zone, choose another type from the scaffold catalog that meets the same requested minimums, update both JSON files, and plan again.

## Provision

Apply the reviewed saved plan only when provisioning was requested:

```shell
terraform apply tfplan
```

Do not use `-auto-approve` unless the user explicitly requests a non-interactive apply.

## Validate And Report

Capture all generated connection data:

```shell
pwd -P
test -f README.md
terraform output -json public_ips
terraform output -json private_ips
terraform output -json instance_ids
terraform output -json instance_types
terraform output -json ssh_commands
```

Verify the number of public and private IPs for every group equals its requested count. When network access permits, test one SSH command per group using non-destructive commands such as `hostname` and `ip -brief address`.

Report:

- Absolute deployment path and generated `README.md` path
- AWS account/profile and region
- Resolved instance type for each requested CPU/memory specification
- Public and private IPs grouped by node name
- SSH commands grouped by node name
- Any SSH or regional instance-availability checks that could not be completed

## Update Or Destroy

For an existing deployment, edit `terraform.tfvars.json`, then run `terraform plan` and apply a reviewed plan. Do not re-scaffold with `--force`, because that can remove local state and sever Terraform's ownership record.

Destroy only when explicitly requested:

```shell
terraform plan -destroy -out=destroy.tfplan
terraform apply destroy.tfplan
```

Confirm that Elastic IPs and other resources were removed. Preserve local state and metadata unless the user separately asks to remove the local project.
