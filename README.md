# skills-hub

Skills for AI agents. See `AGENTS.md` for contributor guidelines.

## Available Skills

- analyse-issue - analyze a GitHub issue from an issue URL or number
- create-pr - automatically branch and commit current work before pushing and creating a pull request
- deploy-ec2-aws - deploy named EC2 node groups with Terraform, private networking, and stable public IPs
- deploy-tidb-aws - deploy or manage TiDB clusters on AWS with Terraform and TiUP
- implement-issue - implement a GitHub issue from an issue URL or number
- new-issue - create or file a GitHub issue, bug report, or feature request from the conversation context
- pr-review - review a GitHub or GitLab pull request from a PR URL or number
- resume-agent-session - reconstruct compact working context from Codex, Pi, Oh My Pi, or Claude Code sessions
- resolve-git-conflicts - resolve Git conflicts from merge, rebase, cherry-pick, or stash operations

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
