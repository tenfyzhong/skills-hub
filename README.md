# skills-hub

Skills for AI agents. See `AGENTS.md` for contributor guidelines.

## Available Skills

- analyse-issue - analyze a GitHub issue from an issue URL or number
- create-pr - automatically branch and commit current work before pushing and creating a pull request
- deploy-ec2-aws - deploy and validate named EC2 nodes with Terraform, drift-safe updates, private networking, and stable public IPs
- deploy-tidb-aws - deploy or manage TiDB clusters on AWS with Terraform and TiUP
- implement-issue - implement a GitHub issue from an issue URL or number
- mysql-to-tidb-ddl-check - assess exported MySQL DDL for TiDB 8.5 and TiDB Cloud using minimum capabilities across providers and regions by default (neither provider nor region required), with English, Chinese, or Japanese reports containing located findings, coverage gaps, and remediation advice
- new-issue - create or file a GitHub issue, bug report, or feature request from the conversation context
- natural-writing - polish Chinese and English articles to sound less templated while preserving the author's voice and meaning
- pr-review - review a GitHub or GitLab pull request from a PR URL or number
- resume-agent-session - reconstruct compact working context from Codex, Pi, Oh My Pi, or Claude Code sessions
- resolve-git-conflicts - resolve Git conflicts from merge, rebase, cherry-pick, or stash operations

## Agent Prompt Examples

After installing a skill, paste its example prompt into your agent. Replace repository URLs, issue or PR numbers, file paths, session IDs, and deployment settings with your own values. Run repository-related prompts from the target repository.

### analyse-issue

[Skill instructions](analyse-issue/SKILL.md)

```text
Use $analyse-issue to analyze https://github.com/owner/repo/issues/123.
Trace the relevant code, identify the root cause, and propose a fix with
the tests needed to verify it. Do not implement changes yet.
```

### create-pr

[Skill instructions](create-pr/SKILL.md)

```text
Use $create-pr to turn the current repository changes into a pull request
targeting main. Review the diff, run the relevant checks, create a branch
if needed, commit with a sign-off, push it, and create the PR with an
English title and description explaining the change and validation.
```

### deploy-ec2-aws

[Skill instructions](deploy-ec2-aws/SKILL.md)

```text
Use $deploy-ec2-aws to provision a deployment named demo in us-west-2
using AWS profile default and my public key ~/.ssh/id_ed25519.pub.
Create api=2:2:4 and worker=3:4:8 node groups. Restrict SSH ingress to
my current public IPv4 address. Review the Terraform plan, apply it,
verify SSH on every node, and report the deployment directory, node IPs,
instance types, and SSH commands.
```

### deploy-tidb-aws

[Skill instructions](deploy-tidb-aws/SKILL.md)

```text
Use $deploy-tidb-aws to deploy and start a TiDB test cluster on AWS with
namespace tidb-demo. Use the latest stable TiDB release, 1 PD, 3 TiDB,
3 TiKV, 0 TiFlash, and 0 TiCDC nodes. Review the Terraform plan before
applying it, validate the running cluster, and report the deployment
directory, generated README, and all node IPs.
```

### implement-issue

[Skill instructions](implement-issue/SKILL.md)

```text
Use $implement-issue to implement https://github.com/owner/repo/issues/123
in the current repository. Follow its acceptance criteria, add regression
tests for the reported behavior, run the relevant checks, and summarize
the changes and validation results.
```

### mysql-to-tidb-ddl-check

[Skill instructions](mysql-to-tidb-ddl-check/SKILL.md)

```text
Use $mysql-to-tidb-ddl-check to assess /path/to/schema.sql exported from
MySQL 8.0.36 for migration to TiDB Cloud Starter. Write the report in English.

Use the minimum capability set across cloud providers and regions; do not
ask me for a provider or region. I have not confirmed whether routines,
events, and triggers were fully exported, so retain that coverage gap.

Include blockers, items requiring action or confirmation, file and line
locations, remediation suggestions, and coverage limitations. Do not
connect to a database, execute SQL, or modify the input file.
```

You can also supply a directory of `.sql` files, choose self-managed TiDB 8.5 as the target, or request a Chinese or Japanese report. See the [skill instructions](mysql-to-tidb-ddl-check/SKILL.md) for supported inputs and assessment boundaries.

### natural-writing

[Skill instructions](natural-writing/SKILL.md)

```text
Use $natural-writing to polish /path/to/draft.md for a technical blog.
Keep the original language, facts, links, technical terms, and author's
viewpoint. Remove generic phrasing and repetition while preserving the
author's voice. Return the complete revised article.
```

### new-issue

[Skill instructions](new-issue/SKILL.md)

```text
Use $new-issue to file a bug in owner/repo: the settings page shows a
success message after I save a new display name, but refreshing the page
restores the old name. Expected behavior: the new name survives a refresh.
Include reproduction steps, expected and actual behavior, and note any
missing environment details without inventing them. Return the issue URL.
```

### pr-review

[Skill instructions](pr-review/SKILL.md)

```text
Use $pr-review to review https://github.com/owner/repo/pull/456.
Check correctness, regressions, security, and test coverage. Prioritize
actionable findings with file and line references and explain their impact.
```

### resolve-git-conflicts

[Skill instructions](resolve-git-conflicts/SKILL.md)

```text
Use $resolve-git-conflicts to resolve the current rebase conflicts.
Inspect the base and both sides, preserve the intended behavior, stage
the resolved files, and run the relevant checks. Summarize the decisions
and stop for review before committing or continuing the rebase.
```

### resume-agent-session

[Skill instructions](resume-agent-session/SKILL.md)

```text
Use $resume-agent-session to reconstruct Codex session <full-session-id>
from local logs. Summarize its goal, decisions, completed work, and remaining
steps, then reconcile those findings with the current repository state.
Continue unfinished local implementation and tests; stop before committing,
pushing, or deploying.
```

## Skill Designs

- [MySQL to TiDB DDL checks](docs/mysql-to-tidb-ddl-check-design.md) - design rationale, rule catalog, and acceptance scenarios; see the [skill](mysql-to-tidb-ddl-check/SKILL.md) for usage and implemented coverage

## Install Skills (via vercel-labs/skills)

Use the Skills CLI to install this repository's skills. Examples:

```bash
npx skills add tenfyzhong/skills-hub -s "*" -g
npx skills add tenfyzhong/skills-hub -s analyse-issue -g
```

## Install Local Skills

Install a skill into a local project by running the command from that project's directory.

```bash
cd ~/your-project
npx skills add tenfyzhong/skills-hub -s analyse-issue
```
