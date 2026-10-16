---
name: gitea-tea
description: Manage Gitea resources with tea when the request explicitly mentions Gitea or the tea CLI.
---

# Gitea Tea

Use the installed `tea` CLI for Gitea repositories, issues, pull requests, releases, and Actions. Activate only for requests explicitly mentioning Gitea or its tea CLI, including a Gitea URL or an established Gitea/tea conversation. Generic Git, GitHub, `gh`, or registry requests alone do not trigger this skill; neither does the word “tea” in unrelated contexts.

Use the Gitea instance specified by the user or established repository context. Do not assume a particular host. Follow the user's or repository's language conventions for issues and pull requests.

## Resolve the target

1. Read `tea --help`, then the relevant command's local help. Detect available subcommands, aliases, flags, and output formats from that help and adapt the examples below automatically; do not require a particular tea version. Inspect only the command paths needed for the task and reuse the results within the session.
2. Inspect `git remote -v` when inside a checkout and `tea login list --output json` for available instances. Match the requested URL to its login, repository owner/name, and issue/PR index. Retain any server URL subpath.
3. Prefer explicit `--login work --repo owner/repo` on commands supporting them. `work` is a placeholder for the matched login name, not a presumed existing account. Use `--remote upstream` only when that remote resolves to the intended Gitea target. An owner/repo slug alone does not identify a server.
4. When `tea api` is available, verify the selected identity with `tea api --login work /user` and repository access with `tea api --login work /repos/owner/repo` as needed. Otherwise use supported identity and repository commands, checking how they select the login. If several accounts match and context cannot disambiguate, ask which one to use before writing.

Place command options before positional arguments. Prefer long options: `-R` means remote discovery in tea, unlike `gh -R`; some subcommands also reuse short flags. Options such as `--login`, `--repo`, and `--output` are command-specific, not universal global flags.

## Adapt to installed capabilities

Treat every example as a template, not a guaranteed command across releases. Resolve command names and flags through the installed help before execution, including login discovery and API fallback. Prefer a supported equivalent that preserves the requested behavior. If JSON output is unavailable, use a supported output format; if a native operation is missing, use `tea api` only when both that command and the required API features are available.

Never drop a target selector, filter, or safety condition merely to make a command run. If no supported equivalent preserves the operation, explain the specific missing capability rather than silently changing the task or upgrading tea. Detect compatibility with read-only help, not trial writes; after an uncertain write result, inspect remote state before considering another implementation.

## Authentication

Reuse an existing matching login. If authentication is missing, inspect `tea login add --help`; a typical interactive setup is `tea login add --name work --url https://git.example.com`. Use supported OAuth or a securely supplied token as appropriate. Use `GITEA_SERVER_TOKEN` for login creation only if local help lists it; do not print secrets or put literal secrets into generated commands or documents.

Configuration lives under `$XDG_CONFIG_HOME/tea` (normally `~/.config/tea`). Do not dump credential files. Tea API authentication and Git SSH/HTTPS authentication are separate: adding a tea login alone does not configure Git credentials. Change credential helpers only when needed for the authorized workflow. Keep TLS verification enabled.

## Common reads

Replace the login, repository, and numeric IDs with the resolved target:

```sh
tea issues --login work --repo owner/repo --state open --page 1 --limit 30 --output json
tea issues --login work --repo owner/repo --comments 42
tea pr --login work --repo owner/repo --state open --output json
tea pr --login work --repo owner/repo --comments 17
tea pr --login work --repo owner/repo --fields index,title,head,base,diff,ci 17
tea repos --login work --output json
tea actions runs list --login work --repo owner/repo --branch feature/topic --output json
tea actions runs view --login work --repo owner/repo --jobs 123
tea actions runs logs --login work --repo owner/repo 123
```

Unlike `gh pr view`, tea shows PR detail via `tea pr <index>`; issues work similarly. Use `--fields` only with fields listed by that command's help. For automation prefer JSON where supported and select required fields explicitly. Paginate list results with `--page` and `--limit` until the requested scope is covered; do not present one page as a complete inventory.

## Issues and pull requests

Prepare multiline descriptions in a UTF-8 file and use `--description-file` when supported. Otherwise pass the file contents as one literal argument to a supported `--description` flag through an argument-safe process invocation, or use an available API body-file option. Preserve line breaks and never interpolate Markdown into executable shell code. The examples below perform writes; run only the operation requested by the user.

```sh
tea issues create --login work --repo owner/repo --title 'Issue title' --description-file /absolute/path/issue.md
tea pr create --login work --repo owner/repo --base main --head feature/topic --title 'PR title' --description-file /absolute/path/pr.md
tea pr edit --login work --repo owner/repo --title 'Updated title' --description-file /absolute/path/pr.md 17
tea comment --login work --repo owner/repo 42 'Requested comment text'
```

Before PR creation, inspect the actual base branch, local diff, and remote head. Tea expects the relevant Git commits to have been published; it does not replace `git commit` or `git push`. Use `--head contributor:feature/topic` for a fork when appropriate. Do not assume the target branch is named `main` if repository instructions or metadata say otherwise.

For local review, `tea pr checkout --login work --repo owner/repo 17` changes the working checkout; preserve dirty work and follow the repository's worktree policy. For remote review, inspect `tea pr review --help`, `tea pr approve --help`, or `tea pr reject --help` first. A request to inspect a PR alone does not authorize posting comments or submitting a review.

Merge only when requested, after checking the current head, checks, and review state. Tea uses `tea pr merge --login work --repo owner/repo --style squash 17`, not `gh pr merge --squash`. If exact-head atomic enforcement is required, consult the instance API for a supported guard; a preflight read alone does not prevent a concurrent push. `tea pr clean` deletes local and remote branches and is not routine read-only cleanup.

After a write, read back the affected issue/PR and report its URL and verified state. If a write times out, inspect the remote state before retrying so that creation or commenting is not duplicated.

## API fallback

Prefer native subcommands. If local help exposes `tea api`, inspect its own help before using it for missing operations; API flags can also differ across tea versions. Consult the target server's API schema (`/swagger.v1.json` or `/api/swagger`) only when endpoint details are needed for the task. Match the server's capabilities and endpoint permissions, rather than assuming the newest public API applies. If `tea api` is absent, use an equivalent supported native command or report the capability gap.

```sh
tea api --login work --method GET '/repos/owner/repo/pulls/17'
tea api --login work --method GET '/repos/owner/repo/issues?state=open&page=1&limit=30'
tea api --login work --method PATCH --data @/absolute/path/update.json '/repos/owner/repo/issues/42'
```

Relative endpoints are prefixed with `/api/v1/`. Quote paths containing query strings or `{owner}`/`{repo}` placeholders. Prefer relative endpoints on the matched login so credentials are not directed to another host.

`-f` supplies string body fields; `-F` supplies typed fields and supports `@file` or `@-`. `--data @file` sends raw JSON and cannot be combined with `-f`/`-F`. Supplying body fields changes the default method to POST, so specify the method explicitly. Put GET filters in the query string. For `tea api`, `--output` is a destination filename, **not** a JSON format selector; the response body is already emitted directly. Use explicit page queries and the API's pagination headers as needed; do not assume `gh api --paginate` exists.

For 401/403 responses, inspect the selected login and required permissions. For 404 responses, verify host, owner/repo, visibility, and server API support. Do not silently switch accounts or broaden token privileges.

## Other resources

Discover the relevant subcommands through `tea releases --help`, `tea releases assets --help`, `tea labels --help`, `tea milestones --help`, `tea wiki --help`, or `tea actions workflows --help`. Release publication, workflow dispatch, secret changes, and administration require their own task authorization; listing resources does not imply permission to change them.

If “registry” specifically means Gitea package/container storage, identify the package type and check local help for package-management commands. If none are available, use supported package API operations through `tea api` where available and suitable, or the package-native client for uploads/downloads when required. Do not invent `tea packages` or treat Git repositories as package storage.

## Local reference

Use local `tea --help` and subcommand help as the authoritative syntax reference for the installed binary. Do not fetch remote documentation as a routine skill-loading step.
