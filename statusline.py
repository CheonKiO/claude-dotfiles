#!/usr/bin/env python3
"""Claude Code statusLine — one line:
  model | dir(branch*) | ctx N% | $cost | 5h N% 7d N%
Reads the status JSON on stdin, prints the line on stdout. Cross-platform,
stdlib only. Every segment is optional (guarded) so it degrades on older
Claude Code payloads and never crashes the status bar.
"""
import datetime
import json
import os
import subprocess
import sys
from pathlib import Path


def git_branch(cwd):
    try:
        b = subprocess.run(["git", "-C", cwd, "rev-parse", "--abbrev-ref", "HEAD"],
                           capture_output=True, text=True, timeout=1)
        if b.returncode != 0:
            return None
        branch = b.stdout.strip()
        dirty = subprocess.run(["git", "-C", cwd, "status", "--porcelain"],
                               capture_output=True, text=True, timeout=1)
        return f"{branch}{'*' if dirty.stdout.strip() else ''}"
    except Exception:
        return None


STATE_DIR = Path.home() / ".claude" / "sync-state"
REFRESH_AFTER = 600          # seconds before we kick off a background remote re-check


def sync_badge(cwd):
    """Cloud-sync state for this project, read from a local file only — never a network
    call on the render path. A stale remote check is refreshed by a detached background
    run, so the status line itself stays instant."""
    state = STATE_DIR / f"{Path(cwd).name}.json"
    try:
        st = json.loads(state.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None                      # project isn't set up for sync

    push = st.get("push") or {}
    if push.get("state") == "running":
        return "☁ 올리는중"
    if push.get("state") == "failed":
        return "☁ 실패"

    checked = st.get("remote_checked")
    stale = True
    if checked:
        try:
            age = (datetime.datetime.now(datetime.timezone.utc)
                   - datetime.datetime.fromisoformat(checked)).total_seconds()
            stale = age > REFRESH_AFTER
        except ValueError:
            pass
    if stale and st.get("repo"):
        script = Path.home() / ".claude" / "claude-sync.py"
        if script.is_file():
            try:
                subprocess.Popen(
                    [sys.executable, str(script), "refresh", "--repo", st["repo"],
                     "--remote", st.get("remote", "gdrive:claude-sync")],
                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    stdin=subprocess.DEVNULL, start_new_session=(os.name != "nt"))
            except Exception:
                pass

    newest, seen = st.get("remote_newest") or "", st.get("seen") or ""
    if newest and newest > seen:
        return "☁ 새 기록"
    return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    parts = []

    parts.append((data.get("model") or {}).get("display_name") or "?")

    cwd = (data.get("workspace") or {}).get("current_dir") or data.get("cwd") or "."
    name = Path(cwd).name or cwd
    branch = git_branch(cwd)
    parts.append(f"{name}({branch})" if branch else name)

    ctx = (data.get("context_window") or {}).get("used_percentage")
    if ctx is not None:
        parts.append(f"ctx {ctx}%")

    cost = (data.get("cost") or {}).get("total_cost_usd")
    if cost is not None:
        parts.append(f"${cost:.2f}")

    rl = data.get("rate_limits") or {}
    limits = []
    for key, label in (("five_hour", "5h"), ("seven_day", "7d")):
        pct = (rl.get(key) or {}).get("used_percentage")
        if pct is not None:
            limits.append(f"{label} {pct}%")
    if limits:
        parts.append(" ".join(limits))

    try:
        badge = sync_badge(cwd)
    except Exception:
        badge = None
    if badge:
        parts.append(badge)

    print("  |  ".join(parts))


if __name__ == "__main__":
    main()
