# skills-hub

Skills for AI agents. See `AGENTS.md` for contributor guidelines.

## Install Skills (via vercel-labs/skills)

Use the Skills CLI to install this repository's skills. Examples:

```bash
npx skills add tenfyzhong/skill-hub -s "*" -g
npx skills add tenfyzhong/skill-hub -s analyse-issue -g
```

## Install Local Skills

Install a skill into a local project by running the command from that project's directory. Example for Neovim:

```bash
cd ~/.config/nvim
npx skills add tenfyzhong/skill-hub -s install-nvim-plugin
```
