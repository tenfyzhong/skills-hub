---
name: deploy-tidb-aws
description: Deploy, start, validate, or destroy TiDB clusters on AWS using Terraform and TiUP from a bundled terraform-up-tidb-aws template. Use when the user asks to deploy a TiDB cluster with Terraform, specifies PD/TiDB/TiKV/TiFlash/TiCDC node counts, requests extra service or helper nodes by name, selects new or old TiCDC architecture, or wants an agent to provision and start TiDB on AWS. If core node counts are omitted, default to 1 PD, 3 TiDB, 3 TiKV, 1 TiFlash, and 3 TiCDC. If the TiDB version is omitted, resolve and use the latest stable TiDB release, never nightly.
---

# Deploy TiDB AWS

## Overview

Use this skill to create a self-contained Terraform project from the bundled template, provision AWS VMs, and deploy/start TiDB with TiUP from the center VM.

Before running live infrastructure commands, read [references/deployment.md](references/deployment.md).

## Defaults

When the prompt omits a count, use:

- `n_pd = 1`
- `n_tidb = 3`
- `n_tikv = 3`
- `n_tiflash = 1`
- `n_ticdc = 3`

Honor explicit counts from the prompt, including `0` for optional roles. Keep `n_pd = 1`; the template assumes one PD/monitoring/Grafana host.

Treat named extra service nodes as standalone EC2 instances, not TiUP cluster components. Only add extra service nodes when the prompt explicitly requests them.

When the prompt omits a TiDB version, resolve the latest stable release before `tiup cluster deploy`. Do not deploy `nightly` by default.

Use the new TiCDC architecture by default. If the prompt explicitly asks for old or legacy TiCDC architecture, scaffold with `--ticdc-architecture old` so the generated topology does not set `server_configs.cdc.newarch`.

## Quick Start

Resolve the skill directory, then scaffold a Terraform project:

```shell
python3 <skill-dir>/scripts/scaffold_project.py --target ./tidb-aws-cluster
```

Pass explicit counts only when the user requested them:

```shell
python3 <skill-dir>/scripts/scaffold_project.py \
  --target ./tidb-aws-cluster \
  --namespace tidb-cluster \
  --n-pd 1 \
  --n-tidb 3 \
  --n-tikv 3 \
  --n-tiflash 1 \
  --n-ticdc 3 \
  --ticdc-architecture new \
  --extra-service service-name=1
```

Then follow [references/deployment.md](references/deployment.md) from the generated project directory.

## Safety

- Before any Terraform command, verify AWS identity for the configured AWS profile. If the identity check fails, run AWS SSO login for that profile and retry the identity check.
- Do not run `terraform apply`, `terraform destroy`, or remote TiUP commands unless the user explicitly asked for deployment, startup, or cleanup.
- Do not print private key material, Terraform state contents, or AWS credentials.
- Warn the user that the template exposes SSH, Grafana, and TiDB Dashboard ports publicly, matching the source repo.
- Use a saved Terraform plan before apply unless the user explicitly asks for non-interactive deployment.
- Start TiUP clusters with `tiup cluster start <cluster-name> --yes`; do not add `--init`.
- After deployment/startup, display and report node IPs for all core and extra service nodes.
