#!/usr/bin/env python3
"""PreToolUse hook (Bash): auto `git fetch` before any command referencing origin/,
so local origin/* refs aren't stale when reviewing branches/MRs."""
import json
import os
import subprocess
import sys
import time

THROTTLE_SECONDS = 30
STATE_DIR = "/tmp/claude-git-fetch-guard"


def main():
    try:
        payload = json.load(sys.stdin)
    except Exception:
        return

    tool_input = payload.get("tool_input", {})
    command = tool_input.get("command", "")
    if "origin/" not in command:
        return

    cwd = payload.get("cwd") or os.getcwd()

    try:
        top = subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True, text=True, timeout=5,
        )
    except Exception:
        return
    if top.returncode != 0:
        return
    repo_root = top.stdout.strip()

    os.makedirs(STATE_DIR, exist_ok=True)
    state_file = os.path.join(STATE_DIR, repo_root.replace("/", "_") + ".ts")
    now = time.time()
    if os.path.exists(state_file):
        try:
            last = float(open(state_file).read().strip())
            if now - last < THROTTLE_SECONDS:
                return
        except Exception:
            pass

    try:
        subprocess.run(
            ["git", "-C", repo_root, "fetch", "--quiet"],
            capture_output=True, text=True, timeout=30,
        )
    except Exception:
        return

    with open(state_file, "w") as f:
        f.write(str(now))

    print(f"origin/ 참조 감지 — git fetch 실행함 ({repo_root})")


if __name__ == "__main__":
    main()
