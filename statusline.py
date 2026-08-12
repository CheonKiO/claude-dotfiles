#!/usr/bin/env python3
"""Claude Code statusLine — one line:
  model | dir(branch*) | ctx N% | $cost | 5h N% 7d N%
Reads the status JSON on stdin, prints the line on stdout. Cross-platform,
stdlib only. Every segment is optional (guarded) so it degrades on older
Claude Code payloads and never crashes the status bar.
"""
import json
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

    print("  |  ".join(parts))


if __name__ == "__main__":
    main()
