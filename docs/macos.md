# GPD on macOS

GPD adds structured physics-research commands to Claude Code, Codex, Gemini CLI, or OpenCode.

In these docs, "runtime" means the AI terminal app you talk to.

Back to the onboarding hub: [GPD Onboarding Hub](./README.md).

## What you need first

- A Mac with internet access
- Permission to install software
- Node.js 20 or newer
- Python 3.11 or newer with `venv`
- One supported runtime that already starts from Terminal:
  Claude Code, Codex, Gemini CLI, or OpenCode

## Open Terminal

1. Press `Command` + `Space`.
2. Type `Terminal`.
3. Press `Return`.

You can also open `Applications > Utilities > Terminal`.

## Check Node and Python

Run:

```bash
node --version
npm --version
npx --version
python3 --version
python3 -m venv --help
```

You want:

- Node `v20` or newer
- Python `3.11` or newer
- `python3 -m venv --help` to print help text instead of an error

## Install or update missing tools

If Node or Python is missing, the simplest path for most beginners is to use the official installer pages linked below.

If you already use Homebrew, you can also install from Terminal:

```bash
brew install node
brew install python
```

After installing, close Terminal, open it again, and rerun the version checks.

## Make sure your runtime works

Before installing GPD, confirm that your runtime starts from Terminal:

- Claude Code: `claude --version`
- Codex: `codex --help`
- Gemini CLI: `gemini --help`
- OpenCode: `opencode --help`

Then use the matching runtime guide:

<!-- gpd-public-surface:runtime-doc-links:start -->
- [Claude Code quickstart](./claude-code.md)
- [Codex quickstart](./codex.md)
- [Gemini CLI quickstart](./gemini-cli.md)
- [OpenCode quickstart](./opencode.md)
<!-- gpd-public-surface:runtime-doc-links:end -->

## Install GPD

Most beginners should install GPD into one runtime at a time and use `--local`.

<!-- gpd-public-surface:os-install-matrix:start -->
| Runtime | Install command |
| --- | --- |
| Claude Code | `npx -y get-physics-done --claude --local` |
| Codex | `npx -y get-physics-done --codex --local` |
| Gemini CLI | `npx -y get-physics-done --gemini --local` |
| OpenCode | `npx -y get-physics-done --opencode --local` |
<!-- gpd-public-surface:os-install-matrix:end -->

## Confirm success

1. In Terminal, run:

```bash
gpd --help
```

2. Open your runtime and run the matching GPD help command from the generated table:

<!-- gpd-public-surface:supported-runtimes-table:start -->
| Runtime | `npx` flag | Help | Start | Tour | New work | Existing work | Return later |
| --- | --- | --- | --- | --- | --- | --- | --- |
| Claude Code | `--claude` | `/gpd:help` | `/gpd:start` | `/gpd:tour` | `/gpd:new-project --minimal` | `/gpd:map-research` | `/gpd:resume-work` |
| Codex | `--codex` | `$gpd-help` | `$gpd-start` | `$gpd-tour` | `$gpd-new-project --minimal` | `$gpd-map-research` | `$gpd-resume-work` |
| Gemini CLI | `--gemini` | `/gpd:help` | `/gpd:start` | `/gpd:tour` | `/gpd:new-project --minimal` | `/gpd:map-research` | `/gpd:resume-work` |
| OpenCode | `--opencode` | `/gpd-help` | `/gpd-start` | `/gpd-tour` | `/gpd-new-project --minimal` | `/gpd-map-research` | `/gpd-resume-work` |
<!-- gpd-public-surface:supported-runtimes-table:end -->

If that works, the install is in good shape. If you are not sure what fits this folder yet, use the runtime-specific `start` command below. If you want a guided overview first, use the runtime-specific `tour` command below.

## Where to go next

Use the exact command for your runtime:

<!-- gpd-public-surface:os-next-steps-table:start -->
| What you want to do | Claude Code / Gemini CLI | Codex | OpenCode |
| --- | --- | --- | --- |
| Not sure which path fits this folder | `/gpd:start` | `$gpd-start` | `/gpd-start` |
| Want a guided overview | `/gpd:tour` | `$gpd-tour` | `/gpd-tour` |
| Start a new project | `/gpd:new-project --minimal` | `$gpd-new-project --minimal` | `/gpd-new-project --minimal` |
| Map an existing folder | `/gpd:map-research` | `$gpd-map-research` | `/gpd-map-research` |
| Rediscover the workspace in your normal terminal | `gpd resume` | `gpd resume` | `gpd resume` |
| Continue in the reopened runtime | `/gpd:resume-work` | `$gpd-resume-work` | `/gpd-resume-work` |
<!-- gpd-public-surface:os-next-steps-table:end -->

Use `gpd resume` in your normal terminal first. Use `gpd resume --recent` when you need to jump to a different recent workspace before reopening the runtime. After the terminal points you to the right workspace, open your runtime there and use its `resume-work` command to continue inside the project.

## Official docs

- Apple: [Get started with Terminal on Mac](https://support.apple.com/guide/terminal/get-started-pht23b129fed/mac)
- Node.js: [Download Node.js](https://nodejs.org/en/download)
- Python: [Python downloads](https://www.python.org/downloads/)
