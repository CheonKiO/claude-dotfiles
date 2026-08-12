#!/usr/bin/env python3
"""Claude Code statusLine — one line: model | dir(branch*) | style.
Reads the status JSON on stdin, prints the line on stdout. Cross-platform,
stdlib only. Must never crash (a failing statusLine is noise) -> broad guards,
plain-ASCII separators.
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
        star = "*" if dirty.stdout.strip() else ""
        return f"{branch}{star}"
    except Exception:
        return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        return

    model = (data.get("model") or {}).get("display_name") or "?"
    cwd = (data.get("workspace") or {}).get("current_dir") or data.get("cwd") or "."
    style = (data.get("output_style") or {}).get("name") or ""

    parts = [model]
    name = Path(cwd).name or cwd
    branch = git_branch(cwd)
    parts.append(f"{name}({branch})" if branch else name)
    if style and style != "default":
        parts.append(style)

    print("  |  ".join(parts))


if __name__ == "__main__":
    main()
