# skills-hub

Skills for AI agents. See `AGENTS.md` for contributor guidelines.

## Available Skills

- analyse-issue
- create-pr - automatically branch and commit current work before pushing and creating a pull request
- deploy-tidb-aws - scaffold TiDB AWS Terraform deployments under `$HOME/test` with a generated operation README
- implement-issue
- new-issue
- pr-review
- resume-agent-session - reconstruct compact working context from Codex, Pi, Oh My Pi, or Claude Code sessions
- resolve-git-conflicts

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
