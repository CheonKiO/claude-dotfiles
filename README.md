# claude-dotfiles

Personal Claude Code config (CLAUDE.md, skills, hooks), synced across machines — Mac, Windows, WSL.

## What's here

- `CLAUDE.md`, `RTK.md` — behavioral guidelines, always-loaded at session start
- `skills/` — `full-review`, `live-contract-check`, `worktree-cleanup`
- `hooks/` — `file-size-guard.py` (warn on >500-line files), `git-fetch-guard.py` (auto `git fetch` before any command referencing `origin/`)
- `hooks.settings.json` — just the hook registrations, merged into `~/.claude/settings.json` by `sync.py`

**Not here on purpose:** `memory/`, `projects/` (session transcripts), `settings.local.json`, `.credentials.json`, `plugins/cache/` — all machine-local or containing live auth/session state, never synced.

## Usage

On any machine with `python3` on PATH:

```bash
git clone https://github.com/CheonKiO/claude-dotfiles.git
cd claude-dotfiles
python3 sync.py
```

Re-run any time after `git pull` to pick up changes. It's idempotent — copies files as-is and merges hook registrations without duplicating entries or touching other `settings.json` keys.

## Workflow

Edit on any machine (directly under `~/.claude/`, or in this repo — same files) → commit + push here → on other machines, `git pull && python3 sync.py`.
