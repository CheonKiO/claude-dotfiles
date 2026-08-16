#!/usr/bin/env python3
"""Wire a project's Claude Code state to a cloud remote: a SessionEnd hook that pushes,
and nothing else.

Saving is automated; pulling never is. The previous version also installed a SessionStart
hook that injected an initialUserMessage when the remote looked newer, which was wrong in
two ways: it fired only on `startup`, so resuming a session never saw it, and when it did
fire it consumed the new session's first turn. The signal now lives in the status line
(see statusline.py), which is visible in every session and interrupts none of them.

Requires ~/.claude/claude-sync.py (deploy it by running this repo's sync.py) and rclone
configured with the remote you pass.

Usage:
  python3 setup.py --repo /path/to/project [--remote gdrive:claude-sync] [--project-name myproj]

Creates:
  <repo>/.claude/hooks/session-end-sync.py
  <repo>/.claude/settings.local.json   (merges the SessionEnd entry, drops the stale
                                        SessionStart one if a previous run left it)
"""
import argparse
import json
import os
import shutil
from pathlib import Path


def detect_python():
    """Interpreter invocation that exists on this OS: python3 -> python -> py -3.
    Baked into the hook command string (which Claude Code runs verbatim)."""
    for cand in (["python3"], ["python"], ["py", "-3"]):
        if shutil.which(cand[0]):
            return " ".join(cand)
    return "python3"


SESSION_END_TEMPLATE = '''#!/usr/bin/env python3
"""SessionEnd hook (this project only): push Claude state to the cloud remote on a real
end-of-work signal. claude-sync.py --detach returns immediately and records the outcome in
~/.claude/sync-state/, which the status line reads — so closing a session is never held up
by an upload, and a failed one is still visible afterwards."""
import json
import os
import subprocess
import sys
import time

REPO_ROOT = "__REPO_ROOT__"
PROJECT_NAME = "__PROJECT_NAME__"
REMOTE = "__REMOTE__"
SYNC_SCRIPT = os.path.expanduser("~/.claude/claude-sync.py")

THROTTLE_FILE = os.path.expanduser(f"~/.claude-sync-{PROJECT_NAME}-throttle")
THROTTLE_SECONDS = 10  # collapses a simultaneous multi-tab close burst, nothing longer

REAL_END_REASONS = {"prompt_input_exit", "logout", "other"}


def under_repo(cwd):
    a = os.path.normcase(os.path.normpath(cwd))
    b = os.path.normcase(os.path.normpath(REPO_ROOT))
    return a == b or a.startswith(b + os.sep)


def acquire_throttle():
    """Atomic check-and-set so concurrent SessionEnds (e.g. closing the IDE with several
    tabs open) do not all fire a push."""
    now = time.time()
    try:
        with open(THROTTLE_FILE) as f:
            if now - float(f.read().strip()) < THROTTLE_SECONDS:
                return False
    except (OSError, ValueError):
        pass
    try:
        fd = os.open(THROTTLE_FILE, os.O_CREAT | os.O_WRONLY | os.O_TRUNC)
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

    if not under_repo(payload.get("cwd", "")):
        return
    if payload.get("reason", "") not in REAL_END_REASONS:
        return
    if not os.path.isfile(SYNC_SCRIPT):
        return
    if not acquire_throttle():
        return

    subprocess.run(
        [sys.executable, SYNC_SCRIPT, "push", "--repo", REPO_ROOT,
         "--project-name", PROJECT_NAME, "--remote", REMOTE, "--detach"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
'''


def render(template, repo_root, project_name, remote):
    return (
        template
        .replace("__REPO_ROOT__", repo_root)
        .replace("__PROJECT_NAME__", project_name)
        .replace("__REMOTE__", remote)
    )


def merge_hooks(settings_path, end_script):
    data = {}
    if settings_path.exists():
        data = json.loads(settings_path.read_text())

    interp = detect_python()
    data.setdefault("hooks", {})
    data["hooks"]["SessionEnd"] = [
        {
            "matcher": "prompt_input_exit|logout|other",
            "hooks": [
                {"type": "command", "command": f"{interp} {end_script}", "async": True, "timeout": 5}
            ],
        }
    ]
    # Drop the import-nudge hook a previous version of this skill installed.
    stale = data["hooks"].get("SessionStart") or []
    kept = [e for e in stale
            if not any("session-start-check.py" in (h.get("command") or "")
                       for h in e.get("hooks", []))]
    if kept:
        data["hooks"]["SessionStart"] = kept
    else:
        data["hooks"].pop("SessionStart", None)

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return len(stale) - len(kept)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="Absolute path to the project repo root")
    ap.add_argument("--remote", default="gdrive:claude-sync",
                    help="rclone remote + base path (default: gdrive:claude-sync)")
    ap.add_argument("--project-name", default=None, help="Defaults to the repo directory's basename")
    args = ap.parse_args()

    repo_root = str(Path(args.repo).resolve())
    project_name = args.project_name or Path(repo_root).name

    hooks_dir = Path(repo_root) / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    end_script = hooks_dir / "session-end-sync.py"
    end_script.write_text(render(SESSION_END_TEMPLATE, repo_root, project_name, args.remote))

    old = hooks_dir / "session-start-check.py"
    if old.exists():
        old.unlink()

    settings_path = Path(repo_root) / ".claude" / "settings.local.json"
    removed = merge_hooks(settings_path, end_script)

    print(f"done — project: {project_name}")
    print(f"  repo:     {repo_root}")
    print(f"  remote:   {args.remote}/{project_name}")
    print(f"  hook:     {end_script}")
    print(f"  settings: {settings_path}")
    if removed or old.exists() is False and removed:
        print(f"  removed stale SessionStart hook ({removed} entry)")
    print()
    print("Pulling stays manual, on purpose:")
    print(f"  python3 ~/.claude/claude-sync.py status --repo {repo_root}")
    print(f"  python3 ~/.claude/claude-sync.py pull   --repo {repo_root}")
    print()
    print("Add .claude/ to the project's .git/info/exclude if not already covered.")


if __name__ == "__main__":
    main()
