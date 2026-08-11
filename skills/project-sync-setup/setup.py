#!/usr/bin/env python3
"""Bootstrap the SessionEnd/SessionStart cloud-sync automation (built for ieumgil/S15P11A107)
into a NEW project. Generates project-local hook scripts + registers them in that project's
.claude/settings.local.json. Requires ~/claude-export.sh and ~/claude-import.sh to already
exist (project-agnostic already, driven by REPO_ROOT/PROJECT_NAME env vars).

Usage:
  python3 setup.py --repo /path/to/project --cloud-dir "/mnt/c/Users/<winuser>/iCloudDrive" [--project-name myproj]

Creates:
  <repo>/.claude/hooks/session-end-sync.py
  <repo>/.claude/hooks/session-start-check.py
  <repo>/.claude/settings.local.json  (merges SessionEnd/SessionStart hook entries)
  <cloud-dir>/claude-sync-<project-name>/   (dedicated subfolder, avoids colliding with other projects)
"""
import argparse
import json
import os
from pathlib import Path

SESSION_END_TEMPLATE = '''#!/usr/bin/env python3
"""SessionEnd hook (this project only): auto-export Claude state to the cloud in the
background on a real end-of-work signal. Never blocks session close, never deletes
anything except its own project's prior sync archives."""
import json
import os
import subprocess
import sys
import time

REPO_ROOT = "__REPO_ROOT__"
PROJECT_NAME = "__PROJECT_NAME__"
CLOUD_DIR = "__CLOUD_DIR__"
EXPORT_SCRIPT = os.path.expanduser("~/claude-export.sh")
LOG_FILE = os.path.expanduser(f"~/.claude-sync-{PROJECT_NAME}-export.log")
THROTTLE_FILE = os.path.expanduser(f"~/.claude-sync-{PROJECT_NAME}-throttle")
THROTTLE_SECONDS = 10  # only to collapse a simultaneous multi-tab close burst, not to skip real re-closes

REAL_END_REASONS = {"prompt_input_exit", "logout", "other"}


def acquire_throttle():
    """Atomic check-and-set so concurrent SessionEnds (e.g. closing the IDE with
    several tabs open) can\'t all pass the throttle at once."""
    now = time.time()
    try:
        fd = os.open(THROTTLE_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(now).encode())
        os.close(fd)
        return True
    except FileExistsError:
        pass

    try:
        last = float(open(THROTTLE_FILE).read().strip())
    except Exception:
        last = 0
    if now - last < THROTTLE_SECONDS:
        return False

    try:
        os.remove(THROTTLE_FILE)
    except FileNotFoundError:
        pass
    try:
        fd = os.open(THROTTLE_FILE, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        os.write(fd, str(now).encode())
        os.close(fd)
        return True
    except FileExistsError:
        return False


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    cwd = payload.get("cwd", "")
    reason = payload.get("reason", "")

    if not cwd.startswith(REPO_ROOT):
        return
    if reason not in REAL_END_REASONS:
        return
    if not os.path.isdir(CLOUD_DIR):
        return
    if not acquire_throttle():
        return

    with open(LOG_FILE, "a") as log:
        subprocess.Popen(
            ["bash", EXPORT_SCRIPT, CLOUD_DIR],
            env={**os.environ, "REPO_ROOT": REPO_ROOT, "PROJECT_NAME": PROJECT_NAME},
            stdout=log,
            stderr=log,
            start_new_session=True,
        )


if __name__ == "__main__":
    main()
'''

SESSION_START_TEMPLATE = '''#!/usr/bin/env python3
"""SessionStart hook (this project, fresh startup only): if the cloud folder has a sync
archive newer than what this machine last imported, force it into Claude\'s first turn via
initialUserMessage so it actually gets surfaced (additionalContext alone was too easy to
silently skip) — never auto-imports."""
import glob
import json
import os
import re
import sys

REPO_ROOT = "__REPO_ROOT__"
PROJECT_NAME = "__PROJECT_NAME__"
CLOUD_DIR = "__CLOUD_DIR__"
MARKER_FILE = os.path.expanduser(f"~/.claude-sync-{PROJECT_NAME}-imported")

STAMP_RE = re.compile(r"claude-" + re.escape(PROJECT_NAME) + r"-(\\d{8}-\\d{6})\\.tar\\.gz$")


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    cwd = payload.get("cwd", "")
    source = payload.get("source", "")
    if not cwd.startswith(REPO_ROOT) or source != "startup":
        return
    if not os.path.isdir(CLOUD_DIR):
        return

    archives = glob.glob(os.path.join(CLOUD_DIR, f"claude-{PROJECT_NAME}-*.tar.gz"))
    stamped = sorted(
        (m.group(1), path) for path in archives for m in [STAMP_RE.search(path)] if m
    )
    if not stamped:
        return
    latest_stamp, latest_path = stamped[-1]

    last_imported = ""
    if os.path.exists(MARKER_FILE):
        last_imported = open(MARKER_FILE).read().strip()

    if latest_stamp == last_imported:
        return

    archive_name = os.path.basename(latest_path)
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "initialUserMessage": (
                f"[claude-sync] 클라우드에 이 컴퓨터가 아직 안 가져온 동기화 아카이브가 있음: "
                f"{archive_name}. 지금 import할지 나한테 물어봐줘 — 절대 네가 자동으로 풀지 말고."
            ),
            "additionalContext": (
                f"[claude-sync] 최신 미반영 아카이브: {archive_name} (마커파일: {MARKER_FILE})"
            )
        }
    }))


if __name__ == "__main__":
    main()
'''


def render(template, repo_root, project_name, cloud_dir):
    return (
        template
        .replace("__REPO_ROOT__", repo_root)
        .replace("__PROJECT_NAME__", project_name)
        .replace("__CLOUD_DIR__", cloud_dir)
    )


def merge_hooks(settings_path, end_script, start_script):
    data = {}
    if settings_path.exists():
        data = json.loads(settings_path.read_text())

    data.setdefault("hooks", {})
    data["hooks"]["SessionEnd"] = [
        {
            "matcher": "prompt_input_exit|logout|other",
            "hooks": [
                {"type": "command", "command": f"python3 {end_script}", "async": True, "timeout": 5}
            ],
        }
    ]
    data["hooks"]["SessionStart"] = [
        {
            "matcher": "startup",
            "hooks": [
                {"type": "command", "command": f"python3 {start_script}", "timeout": 10}
            ],
        }
    ]

    settings_path.parent.mkdir(parents=True, exist_ok=True)
    settings_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="Absolute path to the project repo root")
    ap.add_argument("--cloud-dir", required=True, help="Base cloud-drive folder (e.g. iCloud Drive root)")
    ap.add_argument("--project-name", default=None, help="Defaults to the repo directory's basename")
    args = ap.parse_args()

    repo_root = str(Path(args.repo).resolve())
    project_name = args.project_name or Path(repo_root).name
    cloud_dir = str(Path(args.cloud_dir) / f"claude-sync-{project_name}")

    Path(cloud_dir).mkdir(parents=True, exist_ok=True)

    hooks_dir = Path(repo_root) / ".claude" / "hooks"
    hooks_dir.mkdir(parents=True, exist_ok=True)

    end_script = hooks_dir / "session-end-sync.py"
    start_script = hooks_dir / "session-start-check.py"
    end_script.write_text(render(SESSION_END_TEMPLATE, repo_root, project_name, cloud_dir))
    start_script.write_text(render(SESSION_START_TEMPLATE, repo_root, project_name, cloud_dir))

    settings_path = Path(repo_root) / ".claude" / "settings.local.json"
    merge_hooks(settings_path, end_script, start_script)

    print(f"done — project: {project_name}")
    print(f"  repo:      {repo_root}")
    print(f"  cloud dir: {cloud_dir}")
    print(f"  hooks:     {end_script}")
    print(f"             {start_script}")
    print(f"  settings:  {settings_path}")
    print()
    print("Add these paths to the project's .git/info/exclude if not already covered:")
    print("  .claude/")


if __name__ == "__main__":
    main()
