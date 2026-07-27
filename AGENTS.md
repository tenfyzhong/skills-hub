# Repository Guidelines

## Project Structure & Module Organization
- Skills live in top-level directories such as `analyse-issue/`, `create-pr/`, and `resolve-git-conflicts/`.
- Each skill is defined in a single `SKILL.md` file at `<skill-name>/SKILL.md` with YAML front matter.
- Repository docs are minimal; `README.md` is the landing page and should reference key contributor guidance.

## Build, Test, and Development Commands
- Most changes are documentation edits; use standard Git workflow commands (for example, `git status` and `git diff`) to review work.
- Run Python skill tests with `python3 -m unittest discover -s <skill-name>/tests -p 'test_*.py'`.

## Coding Style & Naming Conventions
- Avoid trailing whitespace on all lines.
- Indentation: use 2 spaces for YAML/JSON blocks in `SKILL.md` front matter; use 4 spaces (or existing file conventions) elsewhere.
- Keep text concise and instructional; prefer short paragraphs and bullet lists.
- Naming: skill directories use kebab-case (for example, `new-issue/`), and the skill definition file is always `SKILL.md`.

## Testing Guidelines
- Use Python's `unittest` framework for bundled Python scripts.
- Name Python tests `<skill-name>/tests/test_*.py`.

## Commit & Pull Request Guidelines
- Follow the existing commit style: `type(scope): summary` (for example, `feat(analyse-issue): improve issue analysis instructions`).
- All commits must be signed off: `git commit -s`.
- PRs should include a clear summary of changes, rationale, and any impacted skills or docs.

## Agent-Specific Instructions
- Skills are the core artifact; keep each `SKILL.md` self-contained and precise.
- When adding or updating a skill, update `README.md` to reflect the new capability.
- If you create worktrees, place them under `.git/wtm/` in this repository.
