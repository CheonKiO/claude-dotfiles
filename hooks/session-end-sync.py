#!/usr/bin/env python3
"""SessionEnd hook (global, one for every project): push this repo's Claude state to the
cloud remote on a real end-of-work signal — but only for projects named in the allowlist
~/.claude/sync-projects.json. The project root is the nearest ancestor of the session's cwd
whose basename is an allowlisted name, so a new project opts in by adding one line to the
allowlist, not by copying this file and hardcoding paths into a per-project settings.json.

Deriving the root from the allowlist (not git top-level) is deliberate: a sync root like
/home/kio/omok is a container holding several independent git repos (omok-back, omok-front),
so git rev-parse would wrongly pick the subrepo. The allowlisted ancestor is the sync unit.

claude-sync.py --detach returns immediately and records the outcome in ~/.claude/sync-state/,
which the status line reads — closing a session is never held up by an upload, and a failed
one is still visible afterwards.

Test without pushing: CLAUDE_SYNC_DRYRUN=1 prints the resolved decision and exits.
"""
import json
import os
import subprocess
import sys
import time

REMOTE = "gdrive:claude-sync"
SYNC_SCRIPT = os.path.expanduser("~/.claude/claude-sync.py")
ALLOWLIST = os.path.expanduser("~/.claude/sync-projects.json")
THROTTLE_SECONDS = 10  # collapses a simultaneous multi-tab close burst, nothing longer
REAL_END_REASONS = {"prompt_input_exit", "logout", "other"}


def load_allowlist():
    try:
        with open(ALLOWLIST) as f:
            return set(json.load(f))
    except (OSError, json.JSONDecodeError):
        return set()


def resolve_project(cwd, names):
    """Nearest ancestor of cwd (inclusive) whose basename is an allowlisted project. Returns
    (repo_root, project_name) or None — which both derives the sync root and gates in one step."""
    if not cwd or not names:
        return None
    p = os.path.abspath(cwd)
    while True:
        name = os.path.basename(p)
        if name in names:
            return p, name
        parent = os.path.dirname(p)
        if parent == p:
            return None
        p = parent


def acquire_throttle(project):
    """Atomic check-and-set so concurrent SessionEnds (e.g. closing the IDE with several tabs
    open) do not all fire a push. Keyed by project name, so it also dedupes against any stale
    per-project hook still registered during the migration to this global one."""
    path = os.path.expanduser(f"~/.claude-sync-{project}-throttle")
    now = time.time()
    try:
        with open(path) as f:
            if now - float(f.read().strip()) < THROTTLE_SECONDS:
                return False
    except (OSError, ValueError):
        pass
    try:
        fd = os.open(path, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
        with os.fdopen(fd, "w") as f:
            f.write(str(now))
        return True
    except OSError:
        return False


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    dry = os.environ.get("CLAUDE_SYNC_DRYRUN")

    if payload.get("reason", "") not in REAL_END_REASONS:
        if dry:
            print(f"[dryrun] reason={payload.get('reason', '')!r} not a real end — skip")
        return

    resolved = resolve_project(payload.get("cwd", ""), load_allowlist())
    if dry:
        print(f"[dryrun] cwd={payload.get('cwd', '')!r} -> {resolved}")
        return
    if not resolved:
        return
    repo_root, project = resolved
    if not os.path.isfile(SYNC_SCRIPT):
        return
    if not acquire_throttle(project):
        return

    subprocess.run(
        [sys.executable, SYNC_SCRIPT, "push", "--repo", repo_root,
         "--project-name", project, "--remote", REMOTE, "--detach"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
