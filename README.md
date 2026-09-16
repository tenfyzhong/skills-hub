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

## Agent Prompt Example: MySQL to TiDB DDL Check

After installing the skill, paste this prompt into your agent. Replace the file path, source version, target plan, and report language with your own values:

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
