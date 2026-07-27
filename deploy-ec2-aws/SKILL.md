---
name: deploy-ec2-aws
description: Deploy AWS EC2 nodes using Terraform.
---

# Deploy EC2 AWS

## Overview

Scaffold a self-contained Terraform project, then provision one or more named EC2 node groups on AWS. Create a dedicated VPC and public subnet, allow private communication among nodes, restrict SSH ingress, and assign a stable Elastic IP to every node.

Before running live AWS or Terraform commands, read [references/deployment.md](references/deployment.md).

## Inputs And Defaults

Require every node group to have a unique name and positive count. Ask for either value if missing.

Accept CPU and memory as optional minimum requirements. When omitted, use the small default:

- CPU: `2` vCPU
- Memory: `4` GiB
- Resolved type: `t3.medium`

Use repeated node specifications for differently named groups:

```text
api=2
worker=3:4:8
```

The format is `NAME=COUNT[:CPU:MEMORY_GIB]`. CPU and memory are minimums; the resolver may select a slightly larger x86_64 instance type when AWS has no exact match. Do not silently change an explicit count.

Defaults:

- Namespace: `ec2-nodes-<YYMMDDHHMM>` using local time
- Project path: `$HOME/test/ec2-aws-<namespace>`
- AWS profile: `default`
- Region: `us-west-2`
- Root volume: `20` GiB encrypted GP3
- SSH source: the detected operator public IPv4 address as `/32`
- AMI: latest Amazon Linux 2023 x86_64 image resolved through the regional AWS SSM public parameter

## Scaffold

Resolve this skill directory, then run:

```shell
python3 <skill-dir>/scripts/scaffold_project.py \
  --node api=2 \
  --node worker=3:4:8
```

Pass user-specified deployment settings explicitly:

```shell
python3 <skill-dir>/scripts/scaffold_project.py \
  --target "$HOME/test/ec2-aws-demo" \
  --namespace demo \
  --aws-profile default \
  --region us-west-2 \
  --ssh-cidr 203.0.113.10/32 \
  --public-key "$HOME/.ssh/id_ed25519.pub" \
  --node api=2:2:4 \
  --node worker=3:4:8
```

When `--target` is omitted, report the absolute path printed by the script. Continue all Terraform operations from that path and use its generated `README.md` as the local operation guide.

## Network Contract

Keep these defaults unless the user explicitly requests a change:

- Place every node in one dedicated VPC and public subnet.
- Add an internet gateway and default route for outbound and inbound internet connectivity.
- Allow all protocols only between nodes sharing the deployment security group.
- Allow public ingress only on TCP 22 and only from `ssh_cidr`.
- Allocate one Elastic IP per node and output public IPs, private IPs, instance IDs, instance types, and SSH commands grouped by node name.

For additional public ports, add the narrowest security-group rule that meets the request. Require an explicit source CIDR; do not default application ports to `0.0.0.0/0`.

## Safety

- Verify the configured AWS identity before `terraform init`, `plan`, `apply`, or `destroy`. Refresh AWS SSO login when needed.
- Do not run `terraform apply` or `terraform destroy` unless the user explicitly requested provisioning or cleanup.
- Prefer a saved Terraform plan and review it before apply.
- Warn that AWS charges for public IPv4 addresses, including attached Elastic IPs.
- Do not print Terraform state, credentials, or private SSH key material.
- Do not use `--force` on a deployment directory containing state unless the user explicitly asked to replace its local project.
- After apply, report the absolute deployment path, generated `README.md`, public/private IP outputs, resolved instance types, and SSH commands.
